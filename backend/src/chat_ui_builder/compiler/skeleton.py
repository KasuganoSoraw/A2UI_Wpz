from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable

from chat_ui_builder.compiler.frame import FrameCompiler
from chat_ui_builder.compiler.region_archetypes import (
    ArrangementSemantics,
    RegionArchetypeRegistry,
    RegionBuildContext,
)
from chat_ui_builder.planning.models import (
    A2UIFrame,
    AddDividerDelta,
    AddImageDelta,
    AddKeyValueDelta,
    AddRegionDelta,
    AddRegionDividerDelta,
    AddRegionFactDelta,
    AddRegionImageDelta,
    AddRegionLineChartDelta,
    AddRegionMermaidDelta,
    AddRegionTopologyDelta,
    AddRegionPieChartDelta,
    AddRegionTableDelta,
    AddRegionTextDelta,
    AddLineChartDelta,
    AddMermaidDelta,
    AddPieChartDelta,
    AddTopologyDelta,
    AddTableDelta,
    AddTextDelta,
    AddListItemDelta,
    AddRegionListItemDelta,
    FinalizeDelta,
    InitPlanDelta,
    InitSurfaceDelta,
)

logger = logging.getLogger(__name__)


@dataclass
class PendingRegionDelta:
    slot_name: str
    delta_builder: Callable[[str], object]


@dataclass
class RegionBinding:
    region_id: str
    role: str
    section_id: str
    archetype: str
    slot_parents: dict[str, str] = field(default_factory=dict)

    def parent_for(self, slot_name: str) -> str:
        return self.slot_parents.get(
            slot_name, self.slot_parents.get("text", self.section_id)
        )


@dataclass
class SkeletonRuntime:
    frame_compiler: FrameCompiler = field(default_factory=FrameCompiler)
    archetypes: RegionArchetypeRegistry = field(default_factory=RegionArchetypeRegistry)
    initialized: bool = False
    regions: dict[str, RegionBinding] = field(default_factory=dict)
    pending_region_deltas: dict[str, list[PendingRegionDelta]] = field(
        default_factory=dict
    )
    page_title: str = ""


class RegionRouter:
    def __init__(self, runtime: SkeletonRuntime) -> None:
        self.runtime = runtime

    def apply_to_region(
        self,
        region_id: str,
        slot_name: str,
        delta_builder: Callable[[str], object],
    ) -> list[A2UIFrame]:
        if region_id not in self.runtime.regions:
            logger.info("Region %s not ready; queueing %s", region_id, slot_name)
            self.runtime.pending_region_deltas.setdefault(region_id, []).append(
                PendingRegionDelta(slot_name=slot_name, delta_builder=delta_builder)
            )
            return []

        binding = self.runtime.regions[region_id]
        low_level_delta = delta_builder(binding.parent_for(slot_name))
        return self.runtime.frame_compiler.apply(low_level_delta)

    def flush_pending(self, region_id: str) -> list[A2UIFrame]:
        binding = self.runtime.regions[region_id]
        queued = self.runtime.pending_region_deltas.pop(region_id, [])
        frames: list[A2UIFrame] = []
        for item in queued:
            low_level_delta = item.delta_builder(binding.parent_for(item.slot_name))
            frames.extend(self.runtime.frame_compiler.apply(low_level_delta))
        return frames


class RegionHandler:
    def __init__(self, runtime: SkeletonRuntime, router: RegionRouter) -> None:
        self.runtime = runtime
        self.router = router

    def handle(self, delta: AddRegionDelta) -> list[A2UIFrame]:
        if not self.runtime.initialized:
            raise ValueError("init_plan must be emitted before add_region")
        if delta.id in self.runtime.regions:
            raise ValueError(f"Duplicate region id: {delta.id}")

        builder = self.runtime.archetypes.builder_for(delta.role)
        context = RegionBuildContext(
            slot_parent="root",
            delta=delta,
            arrangement=self._arrangement_for(delta),
            presentation_variant=delta.presentation.variant
            if delta.presentation
            else "standard",
        )
        result = builder.build(context, self.runtime.frame_compiler.apply)
        self.runtime.regions[delta.id] = RegionBinding(
            region_id=delta.id,
            role=delta.role,
            section_id=delta.id,
            archetype=result.archetype,
            slot_parents=result.slot_parents,
        )
        frames = list(result.frames)
        frames.extend(self.router.flush_pending(delta.id))
        return frames

    def _arrangement_for(self, delta: AddRegionDelta) -> ArrangementSemantics:
        role_defaults: dict[str, ArrangementSemantics] = {
            "hero": ArrangementSemantics(body_layout="column", facts_layout="row"),
            "summary": ArrangementSemantics(body_layout="none", facts_layout="row"),
            "details": ArrangementSemantics(body_layout="column", facts_layout="row"),
            "workflow": ArrangementSemantics(body_layout="column", facts_layout="row"),
            "supporting": ArrangementSemantics(
                body_layout="column", facts_layout="row"
            ),
            "list": ArrangementSemantics(body_layout="none", facts_layout="row"),
        }
        return role_defaults.get(delta.role, ArrangementSemantics())


class PlanHandler:
    def __init__(self, runtime: SkeletonRuntime, region_handler: RegionHandler) -> None:
        self.runtime = runtime
        self.region_handler = region_handler

    def handle_init(self, delta: InitPlanDelta) -> list[A2UIFrame]:
        self.runtime.initialized = True
        self.runtime.regions = {}
        self.runtime.pending_region_deltas = {}
        self.runtime.page_title = delta.title

        frames = self.runtime.frame_compiler.apply(
            InitSurfaceDelta(
                event="init_surface",
                surface_id=delta.surface_id,
                title=delta.title,
                summary=delta.summary,
                theme=delta.theme,
            )
        )
        logger.info("Initialized display surface")
        return frames

    def handle_finalize(self, _: FinalizeDelta) -> list[A2UIFrame]:
        frames: list[A2UIFrame] = []
        orphan_region_ids = list(self.runtime.pending_region_deltas.keys())
        for region_id in orphan_region_ids:
            frames.extend(
                self.region_handler.handle(
                    AddRegionDelta(
                        event="add_region",
                        id=region_id,
                        role="details",
                        title="补建内容区",
                        description="模型在 region 声明前先发送了条目，后端已自动兜底创建。",
                    )
                )
            )
        return frames


class ContentHandler:
    def __init__(
        self,
        runtime: SkeletonRuntime,
        router: RegionRouter,
        region_handler: RegionHandler,
    ) -> None:
        self.runtime = runtime
        self.router = router
        self.region_handler = region_handler

    def handle_text(self, delta: AddRegionTextDelta) -> list[A2UIFrame]:
        resolved = AddTextDelta(
            event="add_text",
            id=delta.id,
            parent_id="",
            text=delta.text,
            usage_hint=delta.usage_hint,
        )

        def build(parent_id: str) -> object:
            return resolved.model_copy(update={"parent_id": parent_id})

        slot_name = "text"
        region_binding = self.runtime.regions.get(delta.region_id)
        if (
            delta.usage_hint == "code_echo"
            and region_binding
            and region_binding.role == "supporting"
        ):
            slot_name = "code"

        return self.router.apply_to_region(delta.region_id, slot_name, build)

    def handle_table(self, delta: AddRegionTableDelta) -> list[A2UIFrame]:
        table_spec = {
            "title": delta.title,
            "columns": [
                column.model_dump(exclude_none=True) for column in delta.columns
            ],
            "rows": delta.rows,
            "row_key": delta.row_key,
            "striped": delta.striped,
            "bordered": delta.bordered,
        }
        table_spec_json = json.dumps(table_spec, ensure_ascii=False)

        def build(parent_id: str) -> object:
            return AddTableDelta(
                event="add_table",
                id=delta.id,
                parent_id=parent_id,
                spec_json=table_spec_json,
            )

        return self.router.apply_to_region(delta.region_id, "text", build)

    def handle_line_chart(self, delta: AddRegionLineChartDelta) -> list[A2UIFrame]:
        chart_spec = {
            "title": delta.title,
            "width": delta.width,
            "settings": delta.settings.model_dump(exclude_none=True),
            "chartData": delta.chart_data,
        }
        chart_spec_json = json.dumps(chart_spec, ensure_ascii=False)

        def build(parent_id: str) -> object:
            return AddLineChartDelta(
                event="add_line_chart",
                id=delta.id,
                parent_id=parent_id,
                spec_json=chart_spec_json,
            )

        return self.router.apply_to_region(delta.region_id, "text", build)

    def handle_pie_chart(self, delta: AddRegionPieChartDelta) -> list[A2UIFrame]:
        chart_spec = {
            "title": delta.title,
            "width": delta.width,
            "settings": delta.settings or {},
            "chartData": [
                series.model_dump(exclude_none=True) for series in delta.chart_data
            ],
        }
        chart_spec_json = json.dumps(chart_spec, ensure_ascii=False)

        def build(parent_id: str) -> object:
            return AddPieChartDelta(
                event="add_pie_chart",
                id=delta.id,
                parent_id=parent_id,
                spec_json=chart_spec_json,
            )

        return self.router.apply_to_region(delta.region_id, "text", build)

    def handle_mermaid(self, delta: AddRegionMermaidDelta) -> list[A2UIFrame]:
        mermaid_spec = {
            "title": delta.title,
            "diagramType": delta.diagram_type,
            "definition": delta.definition,
        }
        mermaid_spec_json = json.dumps(mermaid_spec, ensure_ascii=False)
        diagram_slot = (
            "flow"
            if delta.diagram_type in {"flowchart", "sequenceDiagram", "stateDiagram-v2"}
            else "text"
        )

        def build(parent_id: str) -> object:
            return AddMermaidDelta(
                event="add_mermaid",
                id=delta.id,
                parent_id=parent_id,
                spec_json=mermaid_spec_json,
            )

        return self.router.apply_to_region(delta.region_id, diagram_slot, build)

    def handle_topology(self, delta: AddRegionTopologyDelta) -> list[A2UIFrame]:
        topology_spec = {
            "title": delta.title,
            "objects": delta.objects,
            "edges": delta.edges,
        }
        topology_spec_json = json.dumps(topology_spec, ensure_ascii=False)

        def build(parent_id: str) -> object:
            return AddTopologyDelta(
                event="add_topology",
                id=delta.id,
                parent_id=parent_id,
                spec_json=topology_spec_json,
            )

        return self.router.apply_to_region(delta.region_id, "flow", build)

    def handle_fact(self, delta: AddRegionFactDelta) -> list[A2UIFrame]:
        def build(parent_id: str) -> object:
            return AddKeyValueDelta(
                event="add_key_value",
                id=delta.id,
                parent_id=parent_id,
                label=delta.label,
                value=delta.value,
            )

        return self.router.apply_to_region(delta.region_id, "fact", build)

    def handle_image(self, delta: AddRegionImageDelta) -> list[A2UIFrame]:
        def build(parent_id: str) -> object:
            return AddImageDelta(
                event="add_image",
                id=delta.id,
                parent_id=parent_id,
                url=delta.url,
                usage_hint=delta.usage_hint,
            )

        return self.router.apply_to_region(delta.region_id, "image", build)

    def handle_divider(self, delta: AddRegionDividerDelta) -> list[A2UIFrame]:
        def build(parent_id: str) -> object:
            return AddDividerDelta(
                event="add_divider",
                id=delta.id,
                parent_id=parent_id,
            )

        return self.router.apply_to_region(delta.region_id, "divider", build)

    def handle_list_item(self, delta: AddRegionListItemDelta) -> list[A2UIFrame]:
        def build(parent_id: str) -> object:
            return AddListItemDelta(
                event="add_list_item",
                id=delta.id,
                parent_id=parent_id,
                title=delta.title,
                detail=delta.detail,
                title_usage_hint=delta.title_usage_hint,
                detail_usage_hint=delta.detail_usage_hint,
            )

        return self.router.apply_to_region(delta.region_id, "list_item", build)


class SkeletonCompiler:
    def __init__(self) -> None:
        self.runtime = SkeletonRuntime()
        self.router = RegionRouter(self.runtime)
        self.region_handler = RegionHandler(self.runtime, self.router)
        self.plan_handler = PlanHandler(self.runtime, self.region_handler)
        self.content_handler = ContentHandler(
            self.runtime, self.router, self.region_handler
        )

        self.handlers: dict[type[object], Callable[[object], list[A2UIFrame]]] = {
            InitPlanDelta: lambda delta: self.plan_handler.handle_init(delta),
            FinalizeDelta: lambda delta: self.plan_handler.handle_finalize(delta),
            AddRegionDelta: lambda delta: self.region_handler.handle(delta),
            AddRegionTextDelta: lambda delta: self.content_handler.handle_text(delta),
            AddRegionTableDelta: lambda delta: self.content_handler.handle_table(delta),
            AddRegionLineChartDelta: lambda delta: (
                self.content_handler.handle_line_chart(delta)
            ),
            AddRegionPieChartDelta: lambda delta: self.content_handler.handle_pie_chart(
                delta
            ),
            AddRegionMermaidDelta: lambda delta: self.content_handler.handle_mermaid(
                delta
            ),
            AddRegionTopologyDelta: lambda delta: self.content_handler.handle_topology(
                delta
            ),
            AddRegionFactDelta: lambda delta: self.content_handler.handle_fact(delta),
            AddRegionImageDelta: lambda delta: self.content_handler.handle_image(delta),
            AddRegionDividerDelta: lambda delta: self.content_handler.handle_divider(
                delta
            ),
            AddRegionListItemDelta: lambda delta: self.content_handler.handle_list_item(
                delta
            ),
        }

    @property
    def regions(self) -> dict[str, RegionBinding]:
        return self.runtime.regions

    @property
    def pending_region_deltas(self) -> dict[str, list[PendingRegionDelta]]:
        return self.runtime.pending_region_deltas

    def apply(self, delta: object) -> list[A2UIFrame]:
        payload = delta.model_dump() if hasattr(delta, "model_dump") else delta
        logger.info(
            "Compiling skeleton delta type=%s payload=%s", type(delta).__name__, payload
        )
        handler = self.handlers.get(type(delta))
        if handler is None:
            return []
        return handler(delta)
