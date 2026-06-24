from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from chat_ui_builder.planning.models import TableColumnSpec


class TextLine(BaseModel):
  """流式文本行。

  streaming 第一版采用 append-only，文本按事件顺序持续追加，
  通过 usage_hint 保留基础层级与语义。
  """

  text: str
  usage_hint: Literal['h1', 'h2', 'h3', 'body', 'caption', 'warning'] = 'body'


class FactItem(BaseModel):
  """流式事实条目。"""

  fact_id: str
  label: str
  value: str


class ListItem(BaseModel):
  """流式列表条目。"""

  item_id: str
  title: str
  detail: str | None = None
  title_usage_hint: Literal['h1', 'h2', 'h3', 'body', 'caption', 'warning'] | None = None
  detail_usage_hint: Literal['h1', 'h2', 'h3', 'body', 'caption', 'warning'] | None = None


class InitStreamSurfaceEvent(BaseModel):
  event: Literal['init_stream_surface']
  surface_id: str = 'main'
  title: str | None = None
  summary: str | None = None


class CreateTextBlockEvent(BaseModel):
  event: Literal['create_text_block']
  block_id: str
  dataset_id: str
  title: str | None = None
  lines: list[TextLine]


class AppendTextLinesEvent(BaseModel):
  event: Literal['append_text_lines']
  block_id: str
  lines: list[TextLine]


class CreateFactsBlockEvent(BaseModel):
  event: Literal['create_facts_block']
  block_id: str
  dataset_id: str
  title: str | None = None
  facts: list[FactItem]


class AppendFactsEvent(BaseModel):
  event: Literal['append_facts']
  block_id: str
  facts: list[FactItem]


class CreateListBlockEvent(BaseModel):
  event: Literal['create_list_block']
  block_id: str
  dataset_id: str
  title: str | None = None
  items: list[ListItem] = Field(default_factory=list)


class AddListItemsEvent(BaseModel):
  event: Literal['add_list_items']
  block_id: str
  items: list[ListItem]


class CreateTableBlockEvent(BaseModel):
  event: Literal['create_table_block']
  block_id: str
  dataset_id: str
  title: str | None = None
  columns: list[TableColumnSpec]
  rows: list[dict[str, object]]


class AppendTableRowsEvent(BaseModel):
  event: Literal['append_table_rows']
  block_id: str
  rows: list[dict[str, object]]


class SetFinalSummaryTextEvent(BaseModel):
  event: Literal['set_final_summary_text']
  block_id: str = 'final_summary_text'
  title: str | None = None
  lines: list[TextLine]


class SetFinalSummaryFactsEvent(BaseModel):
  event: Literal['set_final_summary_facts']
  block_id: str = 'final_summary_facts'
  title: str | None = None
  facts: list[FactItem]


StreamEvent = Annotated[
    InitStreamSurfaceEvent
    | CreateTextBlockEvent
    | AppendTextLinesEvent
    | CreateFactsBlockEvent
    | AppendFactsEvent
    | CreateListBlockEvent
    | AddListItemsEvent
    | CreateTableBlockEvent
    | AppendTableRowsEvent
    | SetFinalSummaryTextEvent
    | SetFinalSummaryFactsEvent,
    Field(discriminator='event'),
]

STREAM_EVENT_ADAPTER = TypeAdapter(StreamEvent)
