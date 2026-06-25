from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

from litellm import acompletion
from pydantic import BaseModel, Field

from chat_ui_builder.core.settings import settings
from chat_ui_builder.streaming.compiler import StreamCompiler
from chat_ui_builder.streaming.models import (
    STREAM_EVENT_ADAPTER,
    CreateFactsBlockEvent,
    CreateListBlockEvent,
    CreateTableBlockEvent,
    CreateTextBlockEvent,
    InitStreamSurfaceEvent,
    SetFinalSummaryFactsEvent,
    SetFinalSummaryTextEvent,
    StreamEvent,
)
from chat_ui_builder.streaming.prompting import build_stream_event_messages

logger = logging.getLogger(__name__)


class BindingRecord(BaseModel):
    dataset_id: str
    block_id: str
    block_type: Literal["text", "facts", "list", "table"]


class BindingStateSummary(BaseModel):
    bindings: list[BindingRecord] = Field(default_factory=list)


class PageBlockSummary(BaseModel):
    block_id: str
    block_type: Literal["text", "facts", "list", "table"]


class PageStateSummary(BaseModel):
    surface_initialized: bool = False
    blocks: list[PageBlockSummary] = Field(default_factory=list)


class ChangesPayload(BaseModel):
    new_paths: list[str] = Field(default_factory=list)
    new_array_items: dict[str, int] = Field(default_factory=dict)
    is_stream_end: bool = False


class StreamingProjectionInput(BaseModel):
    segment_id: str
    visible_snapshot: dict[str, Any]
    changes: ChangesPayload = Field(default_factory=ChangesPayload)
    binding_state_summary: BindingStateSummary = Field(
        default_factory=BindingStateSummary
    )
    page_state_summary: PageStateSummary = Field(default_factory=PageStateSummary)


class StreamEventLineParser:
    """单阶段 NDJSON 行解析器。"""

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, chunk_text: str) -> list[StreamEvent]:
        if not chunk_text:
            return []

        self._buffer += chunk_text
        events: list[StreamEvent] = []
        while "\n" in self._buffer:
            raw_line, self._buffer = self._buffer.split("\n", 1)
            parsed = self._parse_line(raw_line)
            if parsed is not None:
                events.append(parsed)
        return events

    def finish(self) -> list[StreamEvent]:
        if not self._buffer.strip():
            self._buffer = ""
            return []
        raw_line = self._buffer
        self._buffer = ""
        parsed = self._parse_line(raw_line)
        return [parsed] if parsed is not None else []

    def _parse_line(self, raw_line: str) -> StreamEvent | None:
        line = raw_line.strip()
        if not line:
            return None

        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning(
                "single stage skip invalid NDJSON line: %s line=%s", exc, line
            )
            return None

        try:
            return STREAM_EVENT_ADAPTER.validate_python(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "single stage skip invalid stream event: %s payload=%s", exc, payload
            )
            return None


class StreamingPromptService:
    """单阶段 streaming prompt 服务：一次调用直接输出 StreamEvent。"""

    async def stream_project_segment(
        self,
        payload: StreamingProjectionInput | dict[str, Any],
        *,
        stream_compiler: StreamCompiler,
    ) -> AsyncIterator[dict[str, Any]]:
        projection_input = (
            payload
            if isinstance(payload, StreamingProjectionInput)
            else StreamingProjectionInput.model_validate(payload)
        )

        prompt_payload = {
            "segment_id": projection_input.segment_id,
            "visible_snapshot": projection_input.visible_snapshot,
            "changes": projection_input.changes.model_dump(),
            "binding_state_summary": projection_input.binding_state_summary.model_dump(),
            "page_state_summary": projection_input.page_state_summary.model_dump(),
        }
        logger.info(
            "single stage input payload=%s",
            json.dumps(prompt_payload, ensure_ascii=False),
        )

        parser = StreamEventLineParser()
        events: list[StreamEvent] = []
        frame_count = 0
        messages = build_stream_event_messages(prompt_payload)

        async for chunk_text in self._stream_event_chunks(messages):
            parsed_events = parser.feed(chunk_text)
            for event in parsed_events:
                events.append(event)
                event_frames = stream_compiler.apply(event)
                logger.info(
                    "single stage event apply event=%s frame_count=%s",
                    event.model_dump(exclude_none=True),
                    len(event_frames),
                )
                for frame in event_frames:
                    frame_count += 1
                    yield {"type": "frame", "frame": frame}

        tail_events = parser.finish()
        for event in tail_events:
            events.append(event)
            event_frames = stream_compiler.apply(event)
            logger.info(
                "single stage event apply event=%s frame_count=%s",
                event.model_dump(exclude_none=True),
                len(event_frames),
            )
            for frame in event_frames:
                frame_count += 1
                yield {"type": "frame", "frame": frame}

        self._apply_events_to_binding_state(
            events=events,
            binding_state=projection_input.binding_state_summary,
        )
        self._apply_events_to_page_state(
            events=events,
            page_state=projection_input.page_state_summary,
        )
        logger.info(
            "single stage final summary total_events=%s total_frames=%s page_state_summary=%s",
            len(events),
            frame_count,
            projection_input.page_state_summary.model_dump(),
        )

        yield {
            "type": "final",
            "segment_id": projection_input.segment_id,
            "events": [event.model_dump(exclude_none=True) for event in events],
            "binding_state_summary": projection_input.binding_state_summary.model_dump(),
            "page_state_summary": projection_input.page_state_summary.model_dump(),
        }

    async def _stream_event_chunks(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        response = await acompletion(
            model=settings.litellm_model,
            messages=messages,
            api_base=settings.openai_api_base,
            api_key=settings.openai_api_key,
            stream=True,
            temperature=settings.temperature,
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": False,
                }
            },
        )

        async for chunk in response:
            content = self._extract_chunk_content(chunk)
            if content:
                yield content

    def _extract_chunk_content(self, chunk: Any) -> str:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return ""
        delta = getattr(choices[0], "delta", None)
        if delta is None:
            return ""

        content = getattr(delta, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    texts.append(part)
                    continue
                if isinstance(part, dict):
                    text_value = part.get("text")
                    if isinstance(text_value, str):
                        texts.append(text_value)
            return "".join(texts)
        return ""

    def _apply_events_to_binding_state(
        self,
        *,
        events: list[StreamEvent],
        binding_state: BindingStateSummary,
    ) -> None:
        existing_pairs = {
            (record.dataset_id, record.block_id) for record in binding_state.bindings
        }
        for event in events:
            dataset_id: str | None = None
            block_id: str | None = None
            block_type: Literal["text", "facts", "list", "table"] | None = None

            if isinstance(event, CreateTextBlockEvent):
                dataset_id = event.dataset_id
                block_id = event.block_id
                block_type = "text"
            elif isinstance(event, CreateFactsBlockEvent):
                dataset_id = event.dataset_id
                block_id = event.block_id
                block_type = "facts"
            elif isinstance(event, CreateListBlockEvent):
                dataset_id = event.dataset_id
                block_id = event.block_id
                block_type = "list"
            elif isinstance(event, CreateTableBlockEvent):
                dataset_id = event.dataset_id
                block_id = event.block_id
                block_type = "table"

            if not dataset_id or not block_id or not block_type:
                continue

            pair = (dataset_id, block_id)
            if pair in existing_pairs:
                continue

            binding_state.bindings.append(
                BindingRecord(
                    dataset_id=dataset_id,
                    block_id=block_id,
                    block_type=block_type,
                )
            )
            existing_pairs.add(pair)

    def _apply_events_to_page_state(
        self,
        *,
        events: list[StreamEvent],
        page_state: PageStateSummary,
    ) -> None:
        existing_by_block_id = {block.block_id: block for block in page_state.blocks}

        for event in events:
            if isinstance(event, InitStreamSurfaceEvent):
                page_state.surface_initialized = True
                continue

            block_id: str | None = None
            block_type: Literal["text", "facts", "list", "table"] | None = None
            if isinstance(event, CreateTextBlockEvent):
                block_id = event.block_id
                block_type = "text"
            elif isinstance(event, CreateFactsBlockEvent):
                block_id = event.block_id
                block_type = "facts"
            elif isinstance(event, CreateListBlockEvent):
                block_id = event.block_id
                block_type = "list"
            elif isinstance(event, CreateTableBlockEvent):
                block_id = event.block_id
                block_type = "table"
            elif isinstance(event, SetFinalSummaryTextEvent):
                block_id = event.block_id
                block_type = "text"
            elif isinstance(event, SetFinalSummaryFactsEvent):
                block_id = event.block_id
                block_type = "facts"

            if not block_id or not block_type:
                continue
            if block_id in existing_by_block_id:
                continue

            block_summary = PageBlockSummary(block_id=block_id, block_type=block_type)
            page_state.blocks.append(block_summary)
            existing_by_block_id[block_id] = block_summary
