from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field

from chat_ui_builder.streaming.compiler import StreamCompiler
from chat_ui_builder.streaming.json_extractor import JsonExtractionResult, JsonExtractor
from chat_ui_builder.streaming.service import StreamingPromptService

logger = logging.getLogger(__name__)


class StreamingSessionState(BaseModel):
  """单个 streaming session 的最小运行态。"""

  session_id: str
  latest_raw_text: str = ''
  last_visible_snapshot: dict[str, Any] = Field(default_factory=dict)
  binding_state_summary: dict[str, Any] = Field(default_factory=lambda: {'bindings': []})
  page_state_summary: dict[str, Any] = Field(
      default_factory=lambda: {'surface_initialized': False, 'blocks': []}
  )
  is_processing: bool = False
  has_pending_update: bool = False
  is_stream_end: bool = False
  next_segment_index: int = 1
  first_render_done: bool = False


class StreamingRuntime:
  """session 级流式调度层。

  职责：
  - 同 session 强串行
  - latest raw_text 覆盖
  - 触发时机控制
  - 调用 service 的流式入口并把 frame 继续向上透传
  """

  def __init__(
      self,
      *,
      json_extractor: JsonExtractor | None = None,
      prompt_service: StreamingPromptService | None = None,
  ) -> None:
    self._json_extractor = json_extractor or JsonExtractor()
    self._prompt_service = prompt_service or StreamingPromptService()
    self._sessions: dict[str, StreamingSessionState] = {}
    self._session_locks: dict[str, asyncio.Lock] = {}
    self._session_compilers: dict[str, StreamCompiler] = {}

  async def stream_submit_snapshot(
      self,
      *,
      session_id: str,
      raw_text: str,
      is_stream_end: bool,
  ) -> AsyncIterator[dict[str, Any]]:
    """流式提交累计快照文本。"""

    state = self._get_or_create_session(session_id)
    lock = self._get_session_lock(session_id)
    logger.info(
        'runtime receive snapshot session_id=%s raw_len=%s is_stream_end=%s',
        session_id,
        len(raw_text),
        is_stream_end,
    )

    async with lock:
      state.latest_raw_text = raw_text
      state.is_stream_end = is_stream_end
      state.has_pending_update = True

      if state.is_processing:
        logger.info('runtime skip start: session is processing session_id=%s', session_id)
        yield {
            'type': 'status',
            'session_id': session_id,
            'processed': False,
            'reason': 'processing',
            'final': is_stream_end,
        }
        return

      state.is_processing = True
      logger.info('runtime enter processing session_id=%s', session_id)

    try:
      async for item in self._drain_session(state):
        yield item
    finally:
      async with lock:
        state.is_processing = False
      logger.info('runtime leave processing session_id=%s', session_id)

  async def _drain_session(self, state: StreamingSessionState) -> AsyncIterator[dict[str, Any]]:
    lock = self._get_session_lock(state.session_id)

    while True:
      async with lock:
        if not state.has_pending_update:
          break

        state.has_pending_update = False
        current_raw_text = state.latest_raw_text
        current_is_stream_end = state.is_stream_end
        previous_snapshot = state.last_visible_snapshot

      extraction = self._json_extractor.extract(
          raw_text=current_raw_text,
          previous_snapshot=previous_snapshot,
          is_stream_end=current_is_stream_end,
      )

      if not self._should_trigger_processing(
          state=state,
          extraction=extraction,
          previous_snapshot=previous_snapshot,
      ):
        logger.info(
            'runtime skip trigger session_id=%s is_stream_end=%s changes=%s',
            state.session_id,
            current_is_stream_end,
            extraction.changes,
        )
        yield {
            'type': 'status',
            'session_id': state.session_id,
            'processed': False,
            'reason': 'not_triggered',
            'final': current_is_stream_end,
        }
        continue

      segment_id = f'seg_{state.next_segment_index:04d}'
      logger.info('runtime trigger segment session_id=%s segment_id=%s', state.session_id, segment_id)

      payload = {
          'segment_id': segment_id,
          'visible_snapshot': extraction.visible_snapshot,
          'changes': extraction.changes,
          'binding_state_summary': state.binding_state_summary,
          'page_state_summary': state.page_state_summary,
      }
      session_compiler = self._get_or_create_session_compiler(state.session_id)
      logger.info(
          'runtime use session compiler session_id=%s segment_id=%s',
          state.session_id,
          segment_id,
      )

      final_item: dict[str, Any] | None = None
      async for item in self._prompt_service.stream_project_segment(
          payload,
          stream_compiler=session_compiler,
      ):
        item_type = item.get('type')
        if item_type == 'frame':
          yield {
              'type': 'frame',
              'session_id': state.session_id,
              'segment_id': segment_id,
              'frame': item.get('frame'),
          }
          continue
        if item_type == 'final':
          final_item = item

      if final_item is None:
        logger.warning('runtime missing final item session_id=%s segment_id=%s', state.session_id, segment_id)
        continue

      async with lock:
        state.last_visible_snapshot = extraction.visible_snapshot
        state.binding_state_summary = final_item.get('binding_state_summary', state.binding_state_summary)
        state.page_state_summary = final_item.get('page_state_summary', state.page_state_summary)

        events = final_item.get('events') or []
        if events:
          state.first_render_done = True

        state.next_segment_index += 1

      logger.info(
          'runtime commit state session_id=%s segment_id=%s event_count=%s next_segment_index=%s',
          state.session_id,
          segment_id,
          len(final_item.get('events') or []),
          state.next_segment_index,
      )
      yield {
          'type': 'final',
          'session_id': state.session_id,
          'segment_id': segment_id,
          'processed': True,
          'final': current_is_stream_end,
      }

  def _should_trigger_processing(
      self,
      *,
      state: StreamingSessionState,
      extraction: JsonExtractionResult,
      previous_snapshot: dict[str, Any],
  ) -> bool:
    if not self._has_meaningful_changes(
        extraction=extraction,
        previous_snapshot=previous_snapshot,
    ):
      return False

    if not state.first_render_done:
      return self._should_trigger_first_render(extraction=extraction)

    return self._should_trigger_incremental_render(extraction=extraction)

  def _should_trigger_first_render(self, *, extraction: JsonExtractionResult) -> bool:
    if self._has_array_growth(extraction.changes, threshold=2):
      return True

    is_stream_end = bool(extraction.changes.get('is_stream_end'))
    if is_stream_end and bool(extraction.visible_snapshot):
      return True

    return False

  def _should_trigger_incremental_render(self, *, extraction: JsonExtractionResult) -> bool:
    if self._has_array_growth(extraction.changes, threshold=2):
      return True

    is_stream_end = bool(extraction.changes.get('is_stream_end'))
    if is_stream_end and self._changes_has_delta(extraction.changes):
      return True

    return False

  def _has_meaningful_changes(
      self,
      *,
      extraction: JsonExtractionResult,
      previous_snapshot: dict[str, Any],
  ) -> bool:
    snapshot_changed = extraction.visible_snapshot != (previous_snapshot or {})
    has_changes_delta = self._changes_has_delta(extraction.changes)
    is_stream_end = bool(extraction.changes.get('is_stream_end'))
    return bool(snapshot_changed or has_changes_delta or is_stream_end)

  def _changes_has_delta(self, changes: dict[str, Any]) -> bool:
    new_paths = changes.get('new_paths') or []
    new_array_items = changes.get('new_array_items') or {}
    return bool(new_paths or new_array_items)

  def _has_array_growth(self, changes: dict[str, Any], *, threshold: int) -> bool:
    new_array_items = changes.get('new_array_items') or {}
    return any(int(count) >= threshold for count in new_array_items.values())

  def _get_or_create_session(self, session_id: str) -> StreamingSessionState:
    state = self._sessions.get(session_id)
    if state is None:
      state = StreamingSessionState(session_id=session_id)
      self._sessions[session_id] = state
    return state

  def _get_session_lock(self, session_id: str) -> asyncio.Lock:
    lock = self._session_locks.get(session_id)
    if lock is None:
      lock = asyncio.Lock()
      self._session_locks[session_id] = lock
    return lock

  def _get_or_create_session_compiler(self, session_id: str) -> StreamCompiler:
    compiler = self._session_compilers.get(session_id)
    if compiler is None:
      compiler = StreamCompiler()
      self._session_compilers[session_id] = compiler
      logger.info('runtime create session compiler session_id=%s', session_id)
    return compiler
