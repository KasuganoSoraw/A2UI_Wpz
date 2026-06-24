from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from chat_ui_builder.compiler.frame import FrameCompiler
from chat_ui_builder.planning.models import (
    A2UIFrame,
    AddKeyValueDelta,
    AddSectionDelta,
    AddTableDelta,
    AddTextDelta,
    AddListItemDelta,
    InitSurfaceDelta,
    TableColumnSpec,
    UpdateTableSpecDelta,
)
from chat_ui_builder.streaming.models import (
    AppendFactsEvent,
    AddListItemsEvent,
    AppendTableRowsEvent,
    AppendTextLinesEvent,
    CreateFactsBlockEvent,
    CreateListBlockEvent,
    CreateTableBlockEvent,
    CreateTextBlockEvent,
    FactItem,
    InitStreamSurfaceEvent,
    ListItem,
    SetFinalSummaryFactsEvent,
    SetFinalSummaryTextEvent,
    StreamEvent,
    TextLine,
)


@dataclass
class StreamBlockState:
  """流式 block 状态。

  streaming 第一版以 block 为唯一编排单位，不引入 region/archetype。
  """

  block_id: str
  dataset_id: str | None
  block_type: Literal['text', 'facts', 'list', 'table', 'summary_text', 'summary_facts']
  title: str | None = None
  text_line_count: int = 0
  list_host_id: str | None = None


@dataclass
class TableBlockCache:
  """表格 block 缓存。

  因第一版没有 append_table_rows 对应的 low-level delta，
  这里缓存 columns/rows，并在追加时重建完整 spec_json。
  """

  columns: list[TableColumnSpec]
  rows: list[dict[str, object]]
  title: str | None
  table_component_id: str


class StreamCompiler:
  """流式页面骨架编译器。

  该实现独立于 non-streaming SkeletonCompiler，采用 block-first 模型：
  - 页面固定竖排增长
  - block 按首次创建顺序挂载
  - text/facts/list/table 采用 append-only
  """

  def __init__(self) -> None:
    self.frame_compiler = FrameCompiler()
    # 只允许初始化一次，避免流式中途重置页面导致抖动。
    self.surface_initialized = False
    self.surface_id = 'main'

    # block 运行态：用于类型检查与 parent 路由。
    self.blocks: dict[str, StreamBlockState] = {}
    # 数据集到主 block 的绑定，保证“同一批数据只能绑定一个主组件”。
    self.dataset_to_block: dict[str, str] = {}
    # 记录 block 首次创建顺序，便于调试与后续扩展排序策略。
    self.block_order: list[str] = []
    # 表格增量缓存：append rows 时执行“全量 spec 刷新”。
    self.table_data_cache: dict[str, TableBlockCache] = {}

  def apply(self, event: StreamEvent) -> list[A2UIFrame]:
    if isinstance(event, InitStreamSurfaceEvent):
      return self._handle_init_stream_surface(event)
    if isinstance(event, CreateTextBlockEvent):
      return self._handle_create_text_block(event)
    if isinstance(event, AppendTextLinesEvent):
      return self._handle_append_text_lines(event)
    if isinstance(event, CreateFactsBlockEvent):
      return self._handle_create_facts_block(event)
    if isinstance(event, AppendFactsEvent):
      return self._handle_append_facts(event)
    if isinstance(event, CreateListBlockEvent):
      return self._handle_create_list_block(event)
    if isinstance(event, AddListItemsEvent):
      return self._handle_add_list_items(event)
    if isinstance(event, CreateTableBlockEvent):
      return self._handle_create_table_block(event)
    if isinstance(event, AppendTableRowsEvent):
      return self._handle_append_table_rows(event)
    if isinstance(event, SetFinalSummaryTextEvent):
      return self._handle_set_final_summary_text(event)
    if isinstance(event, SetFinalSummaryFactsEvent):
      return self._handle_set_final_summary_facts(event)
    return []

  def _compile(self, delta: object) -> list[A2UIFrame]:
    return self.frame_compiler.apply(delta)

  def _ensure_surface_initialized(self) -> None:
    if not self.surface_initialized:
      raise ValueError('Stream surface 尚未初始化，请先发送 init_stream_surface 事件。')

  def _register_dataset_binding(self, dataset_id: str, block_id: str) -> None:
    existing = self.dataset_to_block.get(dataset_id)
    if existing and existing != block_id:
      raise ValueError(f'dataset_id={dataset_id} 已绑定到 block={existing}，不能再绑定到 {block_id}。')
    self.dataset_to_block[dataset_id] = block_id

  def _register_block(self, state: StreamBlockState) -> None:
    if state.block_id in self.blocks:
      raise ValueError(f'block_id={state.block_id} 已存在，不允许重复 create。')
    self.blocks[state.block_id] = state
    self.block_order.append(state.block_id)

  def _require_block(self, block_id: str, expected_type: str | None = None) -> StreamBlockState:
    state = self.blocks.get(block_id)
    if state is None:
      raise ValueError(f'block_id={block_id} 不存在，无法执行 append。')
    if expected_type and state.block_type != expected_type:
      raise ValueError(f'block_id={block_id} 类型是 {state.block_type}，与期望 {expected_type} 不匹配。')
    return state

  def _emit_block_title(self, block_id: str, title: str | None) -> list[A2UIFrame]:
    if not title:
      return []
    return self._compile(
        AddTextDelta(
            event='add_text',
            id=f'{block_id}__title',
            parent_id=block_id,
            text=title,
            usage_hint='h2',
        )
    )

  def _emit_text_lines(self, block_id: str, lines: list[TextLine], start_index: int = 0) -> list[A2UIFrame]:
    frames: list[A2UIFrame] = []
    for index, line in enumerate(lines, start=start_index):
      frames.extend(
          self._compile(
              AddTextDelta(
                  event='add_text',
                  id=f'{block_id}__line_{index}',
                  parent_id=block_id,
                  text=line.text,
                  usage_hint=line.usage_hint,
              )
          )
      )
    return frames

  def _emit_facts(self, block_id: str, facts: list[FactItem]) -> list[A2UIFrame]:
    frames: list[A2UIFrame] = []
    for fact in facts:
      frames.extend(
          self._compile(
              AddKeyValueDelta(
                  event='add_key_value',
                  id=f'{block_id}__fact_{fact.fact_id}',
                  parent_id=block_id,
                  label=fact.label,
                  value=fact.value,
              )
          )
      )
    return frames

  def _emit_list_items(self, block_id: str, items: list[ListItem]) -> list[A2UIFrame]:
    frames: list[A2UIFrame] = []
    for item in items:
      frames.extend(
          self._compile(
              AddListItemDelta(
                  event='add_list_item',
                  id=f'{block_id}__item_{item.item_id}',
                  parent_id=block_id,
                  title=item.title,
                  detail=item.detail,
                  title_usage_hint=item.title_usage_hint,
                  detail_usage_hint=item.detail_usage_hint,
              )
          )
      )
    return frames

  def _build_table_spec_json(
      self,
      *,
      title: str | None,
      columns: list[TableColumnSpec],
      rows: list[dict[str, object]],
  ) -> str:
    table_spec = {
        'title': title,
        'columns': [column.model_dump(exclude_none=True) for column in columns],
        'rows': rows,
    }
    return json.dumps(table_spec, ensure_ascii=False)

  def _emit_table_component(
      self,
      *,
      block_id: str,
      table_component_id: str,
      title: str | None,
      columns: list[TableColumnSpec],
      rows: list[dict[str, object]],
  ) -> list[A2UIFrame]:
    spec_json = self._build_table_spec_json(title=title, columns=columns, rows=rows)
    return self._compile(
        AddTableDelta(
            event='add_table',
            id=table_component_id,
            parent_id=block_id,
            spec_json=spec_json,
        )
    )

  def _handle_init_stream_surface(self, event: InitStreamSurfaceEvent) -> list[A2UIFrame]:
    if self.surface_initialized:
      # 流式链路只初始化一次；重复 init 直接忽略，避免中途重置。
      return []

    self.surface_initialized = True
    self.surface_id = event.surface_id
    # streaming 页面初始化阶段不注入过程型说明，避免系统提示混入最终用户可见内容。
    # 若调用方确实需要 summary，可在事件中显式传入。
    return self._compile(
        InitSurfaceDelta(
            event='init_surface',
            surface_id=event.surface_id,
            title=event.title or 'Streaming 页面',
            summary=event.summary,
        )
    )

  def _handle_create_text_block(self, event: CreateTextBlockEvent) -> list[A2UIFrame]:
    self._ensure_surface_initialized()
    self._register_dataset_binding(event.dataset_id, event.block_id)
    state = StreamBlockState(
        block_id=event.block_id,
        dataset_id=event.dataset_id,
        block_type='text',
        title=event.title,
    )
    self._register_block(state)

    frames = self._compile(
        AddSectionDelta(
            event='add_section',
            id=event.block_id,
            parent_id='root',
            layout='Column',
        )
    )
    frames.extend(self._emit_block_title(event.block_id, event.title))
    frames.extend(self._emit_text_lines(event.block_id, event.lines, start_index=state.text_line_count))
    state.text_line_count += len(event.lines)
    return frames

  def _handle_append_text_lines(self, event: AppendTextLinesEvent) -> list[A2UIFrame]:
    self._ensure_surface_initialized()
    state = self._require_block(event.block_id, expected_type='text')
    # text block 需要维护稳定递增编号，保证 id 语义可预测，
    # 避免依赖 FrameCompiler 的自动重命名导致 line 序号漂移。
    frames = self._emit_text_lines(event.block_id, event.lines, start_index=state.text_line_count)
    state.text_line_count += len(event.lines)
    return frames

  def _handle_create_facts_block(self, event: CreateFactsBlockEvent) -> list[A2UIFrame]:
    self._ensure_surface_initialized()
    self._register_dataset_binding(event.dataset_id, event.block_id)
    self._register_block(
        StreamBlockState(
            block_id=event.block_id,
            dataset_id=event.dataset_id,
            block_type='facts',
            title=event.title,
        )
    )

    frames = self._compile(
        AddSectionDelta(
            event='add_section',
            id=event.block_id,
            parent_id='root',
            layout='Column',
        )
    )
    frames.extend(self._emit_block_title(event.block_id, event.title))
    frames.extend(self._emit_facts(event.block_id, event.facts))
    return frames

  def _handle_append_facts(self, event: AppendFactsEvent) -> list[A2UIFrame]:
    self._ensure_surface_initialized()
    self._require_block(event.block_id, expected_type='facts')
    return self._emit_facts(event.block_id, event.facts)

  def _handle_create_list_block(self, event: CreateListBlockEvent) -> list[A2UIFrame]:
    self._ensure_surface_initialized()
    self._register_dataset_binding(event.dataset_id, event.block_id)
    list_host_id = f'{event.block_id}__list_host'
    state = StreamBlockState(
        block_id=event.block_id,
        dataset_id=event.dataset_id,
        block_type='list',
        title=event.title,
        list_host_id=list_host_id,
    )
    self._register_block(state)

    frames = self._compile(
        AddSectionDelta(
            event='add_section',
            id=event.block_id,
            parent_id='root',
            layout='Column',
        )
    )
    frames.extend(self._emit_block_title(event.block_id, event.title))
    # list block 拆成“外层 block + 内层 list host”，
    # 让标题留在外层容器，List 容器只承载真实条目，结构更稳定。
    frames.extend(
        self._compile(
            AddSectionDelta(
                event='add_section',
                id=list_host_id,
                parent_id=event.block_id,
                layout='List',
            )
        )
    )
    frames.extend(self._emit_list_items(list_host_id, event.items))
    return frames

  def _handle_add_list_items(self, event: AddListItemsEvent) -> list[A2UIFrame]:
    self._ensure_surface_initialized()
    state = self._require_block(event.block_id, expected_type='list')
    if not state.list_host_id:
      raise ValueError(f'block_id={event.block_id} 缺少 list_host_id，无法 add_list_items。')
    return self._emit_list_items(state.list_host_id, event.items)

  def _handle_create_table_block(self, event: CreateTableBlockEvent) -> list[A2UIFrame]:
    self._ensure_surface_initialized()
    self._register_dataset_binding(event.dataset_id, event.block_id)
    self._register_block(
        StreamBlockState(
            block_id=event.block_id,
            dataset_id=event.dataset_id,
            block_type='table',
            title=event.title,
        )
    )

    table_component_id = f'{event.block_id}__table'
    self.table_data_cache[event.block_id] = TableBlockCache(
        columns=list(event.columns),
        rows=list(event.rows),
        title=event.title,
        table_component_id=table_component_id,
    )

    frames = self._compile(
        AddSectionDelta(
            event='add_section',
            id=event.block_id,
            parent_id='root',
            layout='Column',
        )
    )
    frames.extend(self._emit_block_title(event.block_id, event.title))
    frames.extend(
        self._emit_table_component(
            block_id=event.block_id,
            table_component_id=table_component_id,
            title=event.title,
            columns=event.columns,
            rows=event.rows,
        )
    )
    return frames

  def _handle_append_table_rows(self, event: AppendTableRowsEvent) -> list[A2UIFrame]:
    self._ensure_surface_initialized()
    self._require_block(event.block_id, expected_type='table')
    cache = self.table_data_cache.get(event.block_id)
    if cache is None:
      raise ValueError(f'block_id={event.block_id} 缺少 table cache，无法 append_table_rows。')

    # 不能继续复用 AddTableDelta：FrameCompiler 会把它当成“新建 table 组件”，
    # 触发 _register_id + parent append child，最终出现重复 table。
    # 这里改为 update_table_spec，只刷新既有 table 的 spec 数据模型。
    cache.rows.extend(event.rows)
    spec_json = self._build_table_spec_json(
        title=cache.title,
        columns=cache.columns,
        rows=cache.rows,
    )
    return self._compile(
        UpdateTableSpecDelta(
            event='update_table_spec',
            id=cache.table_component_id,
            spec_json=spec_json,
        )
    )

  def _handle_set_final_summary_text(self, event: SetFinalSummaryTextEvent) -> list[A2UIFrame]:
    self._ensure_surface_initialized()

    state = self.blocks.get(event.block_id)
    if state is None:
      state = StreamBlockState(
          block_id=event.block_id,
          dataset_id=None,
          block_type='summary_text',
          title=event.title,
      )
      self._register_block(state)
      frames = self._compile(
          AddSectionDelta(
              event='add_section',
              id=event.block_id,
              parent_id='root',
              layout='Column',
          )
      )
      frames.extend(self._emit_block_title(event.block_id, event.title))
      frames.extend(self._emit_text_lines(event.block_id, event.lines, start_index=state.text_line_count))
      state.text_line_count += len(event.lines)
      return frames

    if state.block_type != 'summary_text':
      raise ValueError(f'block_id={event.block_id} 已存在且类型为 {state.block_type}，不能设置 final summary text。')

    # 第一版选择 append-only：若 final summary 已存在，则继续追加最终版文本。
    # 该策略实现简单稳定，后续可升级为 replace 语义。
    frames = self._emit_text_lines(event.block_id, event.lines, start_index=state.text_line_count)
    state.text_line_count += len(event.lines)
    return frames

  def _handle_set_final_summary_facts(self, event: SetFinalSummaryFactsEvent) -> list[A2UIFrame]:
    self._ensure_surface_initialized()

    state = self.blocks.get(event.block_id)
    if state is None:
      self._register_block(
          StreamBlockState(
              block_id=event.block_id,
              dataset_id=None,
              block_type='summary_facts',
              title=event.title,
          )
      )
      frames = self._compile(
          AddSectionDelta(
              event='add_section',
              id=event.block_id,
              parent_id='root',
              layout='Column',
          )
      )
      frames.extend(self._emit_block_title(event.block_id, event.title))
      frames.extend(self._emit_facts(event.block_id, event.facts))
      return frames

    if state.block_type != 'summary_facts':
      raise ValueError(f'block_id={event.block_id} 已存在且类型为 {state.block_type}，不能设置 final summary facts。')

    # 第一版选择 append-only：final summary facts 已存在时继续追加。
    return self._emit_facts(event.block_id, event.facts)
