from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, RootModel, TypeAdapter, ConfigDict


class Theme(BaseModel):
  primaryColor: str | None = None
  font: str | None = None


class RegionPresentationConfig(BaseModel):
  variant: Literal["standard", "timeline"] = "standard"


class InitPlanDelta(BaseModel):
  event: Literal["init_plan"]
  surface_id: str = "main"
  title: str
  summary: str | None = None
  theme: Theme | None = None


class AddRegionDelta(BaseModel):
  event: Literal["add_region"]
  id: str
  role: Literal["hero", "summary", "details", "workflow", "list", "supporting"]
  title: str | None = None
  description: str | None = None
  presentation: RegionPresentationConfig | None = None


class AddRegionTextDelta(BaseModel):
  event: Literal["add_region_text"]
  id: str
  region_id: str
  text: str
  usage_hint: Literal["h1", "h2", "h3", "body", "caption", "warning", "code_echo"] = "body"


class AddRegionFactDelta(BaseModel):
  event: Literal["add_region_fact"]
  id: str
  region_id: str
  label: str
  value: str


class AddRegionImageDelta(BaseModel):
  event: Literal["add_region_image"]
  id: str
  region_id: str
  url: str
  usage_hint: Literal["icon", "avatar", "smallFeature", "mediumFeature", "largeFeature", "header"] | None = None


class AddRegionDividerDelta(BaseModel):
  event: Literal["add_region_divider"]
  id: str
  region_id: str


class AddRegionListItemDelta(BaseModel):
  event: Literal["add_region_list_item"]
  id: str
  region_id: str
  title: str
  detail: str | None = None
  title_usage_hint: Literal["h1", "h2", "h3", "body", "caption", "warning"] | None = None
  detail_usage_hint: Literal["h1", "h2", "h3", "body", "caption", "warning"] | None = None


class TableColumnSpec(BaseModel):
  key: str
  label: str
  width: str | None = None
  align: Literal["left", "center", "right"] | None = None
  ellipsis: bool | None = None


class AddRegionTableDelta(BaseModel):
  event: Literal["add_region_table"]
  id: str
  region_id: str
  columns: list[TableColumnSpec]
  rows: list[dict[str, object]]
  title: str | None = None
  row_key: str | None = None
  striped: bool | None = None
  bordered: bool | None = None


class LineChartSettings(BaseModel):
  dimension: str
  xTitle: str | None = None
  yTitle: str | None = None
  metrics: list[str]
  markPoint: bool | None = None


class AddRegionLineChartDelta(BaseModel):
  event: Literal["add_region_line_chart"]
  id: str
  region_id: str
  title: str | None = None
  width: str | None = None
  settings: LineChartSettings
  chart_data: list[dict[str, str | int | float | bool | None]]


class PieChartSliceSpec(BaseModel):
  value: int | float
  name: str
  selected: bool | None = None


class PieChartSeriesSpec(BaseModel):
  data: list[PieChartSliceSpec]
  radius: str | None = None


class AddRegionPieChartDelta(BaseModel):
  event: Literal["add_region_pie_chart"]
  id: str
  region_id: str
  title: str | None = None
  width: str | None = None
  settings: dict[str, object] | None = None
  chart_data: list[PieChartSeriesSpec]


class AddRegionMermaidDelta(BaseModel):
  event: Literal["add_region_mermaid"]
  id: str
  region_id: str
  title: str | None = None
  diagram_type: Literal["flowchart", "sequenceDiagram", "stateDiagram-v2", "erDiagram", "classDiagram"]
  definition: str


class AddRegionTopologyDelta(BaseModel):
  event: Literal["add_region_topology"]
  id: str
  region_id: str
  title: str | None = None
  objects: list[dict[str, str]]
  edges: list[dict[str, object]]


class InitSurfaceDelta(BaseModel):
  event: Literal["init_surface"]
  surface_id: str = "main"
  title: str
  summary: str | None = None
  theme: Theme | None = None


class AddSectionDelta(BaseModel):
  event: Literal["add_section"]
  id: str
  parent_id: str
  layout: Literal["Column", "Row", "List", "Timeline"]
  order: int | None = None
  appearance: str | None = None


class AddTextDelta(BaseModel):
  event: Literal["add_text"]
  id: str
  parent_id: str
  text: str
  usage_hint: Literal["h1", "h2", "h3", "body", "caption", "warning", "code_echo"] = "body"


class AddKeyValueDelta(BaseModel):
  event: Literal["add_key_value"]
  id: str
  parent_id: str
  label: str
  value: str


class AddImageDelta(BaseModel):
  event: Literal["add_image"]
  id: str
  parent_id: str
  url: str
  usage_hint: Literal["icon", "avatar", "smallFeature", "mediumFeature", "largeFeature", "header"] | None = None


class AddTableDelta(BaseModel):
  event: Literal["add_table"]
  id: str
  parent_id: str
  spec_json: str


class UpdateTableSpecDelta(BaseModel):
  event: Literal["update_table_spec"]
  id: str
  spec_json: str


class AddLineChartDelta(BaseModel):
  event: Literal["add_line_chart"]
  id: str
  parent_id: str
  spec_json: str


class AddPieChartDelta(BaseModel):
  event: Literal["add_pie_chart"]
  id: str
  parent_id: str
  spec_json: str


class AddMermaidDelta(BaseModel):
  event: Literal["add_mermaid"]
  id: str
  parent_id: str
  spec_json: str


class AddTopologyDelta(BaseModel):
  event: Literal["add_topology"]
  id: str
  parent_id: str
  spec_json: str


class AddDividerDelta(BaseModel):
  event: Literal["add_divider"]
  id: str
  parent_id: str


class AddListItemDelta(BaseModel):
  event: Literal["add_list_item"]
  id: str
  parent_id: str
  title: str
  detail: str | None = None
  title_usage_hint: Literal["h1", "h2", "h3", "body", "caption", "warning"] | None = None
  detail_usage_hint: Literal["h1", "h2", "h3", "body", "caption", "warning"] | None = None


class FinalizeDelta(BaseModel):
  event: Literal["finalize", "finalize_plan"]


SkeletonDelta = Annotated[
    InitPlanDelta
    | AddRegionDelta
    | AddRegionTextDelta
    | AddRegionFactDelta
    | AddRegionImageDelta
    | AddRegionDividerDelta
    | AddRegionListItemDelta
    | AddRegionTableDelta
    | AddRegionLineChartDelta
    | AddRegionPieChartDelta
    | AddRegionMermaidDelta
    | AddRegionTopologyDelta
    | FinalizeDelta,
    Field(discriminator="event"),
]

SKELETON_DELTA_ADAPTER = TypeAdapter(SkeletonDelta)


Delta = Annotated[
    InitSurfaceDelta
    | AddSectionDelta
    | AddTextDelta
    | AddKeyValueDelta
    | AddImageDelta
    | AddTableDelta
    | UpdateTableSpecDelta
    | AddLineChartDelta
    | AddPieChartDelta
    | AddMermaidDelta
    | AddTopologyDelta
    | AddDividerDelta
    | AddListItemDelta
    | FinalizeDelta,
    Field(discriminator="event"),
]

DELTA_ADAPTER = TypeAdapter(Delta)


class LiteralString(BaseModel):
  literalString: str


class PathValue(BaseModel):
  path: str


class LiteralBoolean(BaseModel):
  literalBoolean: bool


class LiteralNumber(BaseModel):
  literalNumber: float


class LiteralArray(BaseModel):
  literalArray: list[str]


class ContextEntry(BaseModel):
  key: str
  value: PathValue | LiteralString


class ComponentNode(BaseModel):
  id: str
  weight: float | None = None
  component: dict[str, Any]


class BeginRenderingPayload(BaseModel):
  surfaceId: str
  root: str
  styles: Theme | None = None


class SurfaceUpdatePayload(BaseModel):
  surfaceId: str
  components: list[ComponentNode]


class DataMapEntry(BaseModel):
  key: str
  valueString: str | None = None
  valueNumber: float | None = None
  valueBoolean: bool | None = None
  valueMap: list["DataMapEntry"] | None = None


DataMapEntry.model_rebuild()


class DataModelUpdatePayload(BaseModel):
  surfaceId: str
  path: str
  contents: list[DataMapEntry]


class DeleteSurfacePayload(BaseModel):
  surfaceId: str


class A2UIFrame(BaseModel):
  model_config = ConfigDict(extra="forbid")

  beginRendering: BeginRenderingPayload | None = None
  surfaceUpdate: SurfaceUpdatePayload | None = None
  dataModelUpdate: DataModelUpdatePayload | None = None
  deleteSurface: DeleteSurfacePayload | None = None

  def model_post_init(self, __context: Any) -> None:
    populated = [
        self.beginRendering is not None,
        self.surfaceUpdate is not None,
        self.dataModelUpdate is not None,
        self.deleteSurface is not None,
    ]
    if sum(populated) != 1:
      raise ValueError(
          "A2UI frame must contain exactly one of beginRendering, surfaceUpdate, dataModelUpdate, deleteSurface"
      )
