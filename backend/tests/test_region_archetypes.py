from __future__ import annotations

import json
from chat_ui_builder.planning.models import (
    AddRegionDelta,
    AddRegionFactDelta,
    AddRegionLineChartDelta,
    AddRegionMermaidDelta,
    AddRegionPieChartDelta,
    AddRegionTableDelta,
    InitPlanDelta,
    AddRegionTextDelta,
    AddRegionListItemDelta,
    SKELETON_DELTA_ADAPTER,
)
from chat_ui_builder.compiler.skeleton import SkeletonCompiler


def _slot_component_ids(frames: list[object]) -> set[str]:
    component_ids: set[str] = set()
    for frame in frames:
        surface_update = getattr(frame, "surfaceUpdate", None)
        if not surface_update:
            continue
        for component in surface_update.components:
            component_ids.add(component.id)
    return component_ids


def test_summary_region_uses_compact_fact_strip_slots() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Summary page"))
    frames = compiler.apply(
        AddRegionDelta(
            event="add_region",
            id="summary_region",
            role="summary",
            title="Summary",
            description="Daily KPI snapshot",
        )
    )

    binding = compiler.regions["summary_region"]
    component_ids = _slot_component_ids(frames)

    assert binding.parent_for("fact") == "summary_region_facts"
    assert binding.parent_for("text") == "summary_region_facts"
    assert "summary_region_header" not in component_ids
    assert "summary_region_facts" in component_ids


def test_pending_region_deltas_flush_through_semantic_slot_mapping() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Detail page"))

    compiler.apply(
        AddRegionFactDelta(
            event="add_region_fact",
            id="details_fact",
            region_id="details_region",
            label="Owner",
            value="Ops",
        )
    )

    frames = compiler.apply(
        AddRegionDelta(
            event="add_region", id="details_region", role="details", title="Details"
        )
    )
    component_ids = _slot_component_ids(frames)

    assert "details_region_header" in component_ids
    assert "details_region_body" in component_ids
    assert "details_region_facts" in component_ids
    assert "details_fact" in component_ids


def test_supporting_code_echo_routes_to_code_container_with_code_block_appearance() -> (
    None
):
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Supporting code page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region",
            id="supporting_region",
            role="supporting",
            title="补充信息",
        )
    )

    first_frames = compiler.apply(
        AddRegionTextDelta(
            event="add_region_text",
            id="code_line_1",
            region_id="supporting_region",
            text="kubectl get pods -A",
            usage_hint="code_echo",
        )
    )
    second_frames = compiler.apply(
        AddRegionTextDelta(
            event="add_region_text",
            id="code_line_2",
            region_id="supporting_region",
            text="NAME READY STATUS",
            usage_hint="code_echo",
        )
    )

    binding = compiler.regions["supporting_region"]
    assert binding.parent_for("code") == "supporting_region_code"

    code_container_components = []
    for frame in first_frames:
        if not frame.surfaceUpdate:
            continue
        for component in frame.surfaceUpdate.components:
            if component.id == "supporting_region_code":
                code_container_components.append(component)

    assert code_container_components
    assert (
        code_container_components[0].component["Column"]["appearance"] == "code_block"
    )

    first_data_paths = [
        frame.dataModelUpdate.path for frame in first_frames if frame.dataModelUpdate
    ]
    second_data_paths = [
        frame.dataModelUpdate.path for frame in second_frames if frame.dataModelUpdate
    ]
    assert "/content/code_line_1" in first_data_paths
    assert "/content/code_line_2" in second_data_paths


def test_non_supporting_code_echo_falls_back_to_default_text_slot() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Details code page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region", id="details_region", role="details", title="详情"
        )
    )

    compiler.apply(
        AddRegionTextDelta(
            event="add_region_text",
            id="details_code_line",
            region_id="details_region",
            text="echo hello",
            usage_hint="code_echo",
        )
    )

    binding = compiler.regions["details_region"]
    assert binding.parent_for("code") == "details_region_body"


def test_warning_usage_hint_is_preserved_in_compiled_text_component() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Warning page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region", id="summary_region", role="summary", title="Summary"
        )
    )
    frames = compiler.apply(
        AddRegionTextDelta(
            event="add_region_text",
            id="warning_text",
            region_id="summary_region",
            text="高风险变更窗口，请谨慎操作。",
            usage_hint="warning",
        )
    )

    warning_components = []
    for frame in frames:
        if not frame.surfaceUpdate:
            continue
        for component in frame.surfaceUpdate.components:
            if component.id == "warning_text":
                warning_components.append(component)

    assert warning_components
    assert warning_components[0].component["Text"]["usageHint"] == "warning"


def test_list_item_usage_hint_prefers_model_values_with_default_fallback() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="List page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region", id="list_region", role="list", title="Records"
        )
    )

    hinted_frames = compiler.apply(
        AddRegionListItemDelta(
            event="add_region_list_item",
            id="item_with_hint",
            region_id="list_region",
            title="高优先级记录",
            detail="需要重点关注",
            title_usage_hint="warning",
            detail_usage_hint="caption",
        )
    )
    default_frames = compiler.apply(
        AddRegionListItemDelta(
            event="add_region_list_item",
            id="item_default_hint",
            region_id="list_region",
            title="普通记录",
            detail="常规补充信息",
        )
    )

    hinted_usage_hints: set[str] = set()
    default_usage_hints: set[str] = set()

    for frame in hinted_frames:
        if not frame.surfaceUpdate:
            continue
        for component in frame.surfaceUpdate.components:
            text = (
                component.component.get("Text")
                if isinstance(component.component, dict)
                else None
            )
            if text and isinstance(text, dict) and "usageHint" in text:
                hinted_usage_hints.add(str(text["usageHint"]))

    for frame in default_frames:
        if not frame.surfaceUpdate:
            continue
        for component in frame.surfaceUpdate.components:
            text = (
                component.component.get("Text")
                if isinstance(component.component, dict)
                else None
            )
            if text and isinstance(text, dict) and "usageHint" in text:
                default_usage_hints.add(str(text["usageHint"]))

    assert "warning" in hinted_usage_hints
    assert "caption" in hinted_usage_hints
    assert "body" in default_usage_hints
    assert "caption" in default_usage_hints


def test_list_timeline_variant_compiles_to_timeline_and_timeline_item() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Timeline page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region",
            id="timeline_region",
            role="list",
            title="时间线事件",
            presentation={"variant": "timeline"},
        )
    )

    frames = compiler.apply(
        AddRegionListItemDelta(
            event="add_region_list_item",
            id="timeline_item",
            region_id="timeline_region",
            title="10:32 服务告警",
            detail="错误率升高至 3.2%",
        )
    )

    component_type_by_id: dict[str, set[str]] = {}
    for frame in frames:
        if not frame.surfaceUpdate:
            continue
        for component in frame.surfaceUpdate.components:
            component_type_by_id.setdefault(component.id, set()).update(
                component.component.keys()
            )

    assert "timeline_region_list_items" in component_type_by_id
    assert "Timeline" in component_type_by_id["timeline_region_list_items"]
    assert any(
        "TimelineItem" in component_types
        for component_types in component_type_by_id.values()
    )
    assert any(
        "Card" in component_types for component_types in component_type_by_id.values()
    )


def test_hero_h1_text_is_no_longer_backend_filtered() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="系统健康概览"))
    compiler.apply(
        AddRegionDelta(
            event="add_region", id="hero_region", role="hero", title="核心状态"
        )
    )

    duplicate_frames = compiler.apply(
        AddRegionTextDelta(
            event="add_region_text",
            id="hero_duplicate_h1",
            region_id="hero_region",
            text="系统健康概览",
            usage_hint="h1",
        )
    )
    duplicate_ids = _slot_component_ids(duplicate_frames)
    assert "hero_duplicate_h1" in duplicate_ids

    preserved_frames = compiler.apply(
        AddRegionTextDelta(
            event="add_region_text",
            id="hero_distinct_h1",
            region_id="hero_region",
            text="关键风险与趋势",
            usage_hint="h1",
        )
    )

    preserved_component = None
    for frame in preserved_frames:
        if not frame.surfaceUpdate:
            continue
        for component in frame.surfaceUpdate.components:
            if component.id == "hero_distinct_h1":
                preserved_component = component

    assert preserved_component is not None
    assert preserved_component.component["Text"]["usageHint"] == "h1"


def test_add_region_table_schema_can_be_parsed() -> None:
    parsed = SKELETON_DELTA_ADAPTER.validate_python(
        {
            "event": "add_region_table",
            "id": "users_table",
            "region_id": "details_region",
            "columns": [
                {"key": "date", "label": "日期"},
                {"key": "name", "label": "姓名", "align": "center"},
            ],
            "rows": [
                {"date": "2016/05/02", "name": "王小虎"},
            ],
        }
    )

    assert isinstance(parsed, AddRegionTableDelta)
    assert parsed.columns[0].key == "date"
    assert parsed.rows[0]["name"] == "王小虎"


def test_add_region_table_schema_accepts_object_cell_with_visual_weight() -> None:
    parsed = SKELETON_DELTA_ADAPTER.validate_python(
        {
            "event": "add_region_table",
            "id": "risk_table",
            "region_id": "details_region",
            "columns": [
                {"key": "alarmLevel", "label": "告警等级"},
            ],
            "rows": [
                {
                    "alarmLevel": {
                        "value": "3",
                        "visual_weight": 4,
                    }
                },
            ],
        }
    )

    assert isinstance(parsed, AddRegionTableDelta)
    alarm_cell = parsed.rows[0]["alarmLevel"]
    assert isinstance(alarm_cell, dict)
    assert alarm_cell == {"value": "3", "visual_weight": 4}


def test_add_region_table_schema_preserves_object_cell_without_value() -> None:
    parsed = SKELETON_DELTA_ADAPTER.validate_python(
        {
            "event": "add_region_table",
            "id": "risk_table",
            "region_id": "details_region",
            "columns": [
                {"key": "alarmLevel", "label": "告警等级"},
            ],
            "rows": [
                {
                    "alarmLevel": {
                        "visual_weight": 4,
                    }
                },
            ],
        }
    )

    assert isinstance(parsed, AddRegionTableDelta)
    assert parsed.rows[0]["alarmLevel"] == {"visual_weight": 4}


def test_add_region_table_schema_preserves_visual_weight_out_of_range() -> None:
    parsed = SKELETON_DELTA_ADAPTER.validate_python(
        {
            "event": "add_region_table",
            "id": "risk_table",
            "region_id": "details_region",
            "columns": [
                {"key": "alarmLevel", "label": "告警等级"},
            ],
            "rows": [
                {
                    "alarmLevel": {
                        "value": "3",
                        "visual_weight": 8,
                    }
                },
            ],
        }
    )

    assert isinstance(parsed, AddRegionTableDelta)
    assert parsed.rows[0]["alarmLevel"] == {"value": "3", "visual_weight": 8}


def test_add_region_table_routes_to_default_text_slot_and_emits_table_component() -> (
    None
):
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Table page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region", id="details_region", role="details", title="详情"
        )
    )

    frames = compiler.apply(
        AddRegionTableDelta(
            event="add_region_table",
            id="user_table",
            region_id="details_region",
            columns=[
                {"key": "date", "label": "日期"},
                {"key": "name", "label": "姓名"},
            ],
            rows=[
                {"date": "2016/05/02", "name": "王小虎"},
                {"date": "2016/05/04", "name": "王小虎"},
            ],
            title="用户表",
            row_key="date",
            striped=True,
            bordered=True,
        )
    )

    component_by_id: dict[str, object] = {}
    table_spec_string = None
    for frame in frames:
        if frame.surfaceUpdate:
            for component in frame.surfaceUpdate.components:
                component_by_id[component.id] = component.component
        if (
            frame.dataModelUpdate
            and frame.dataModelUpdate.path == "/content/user_table"
        ):
            for entry in frame.dataModelUpdate.contents:
                if entry.key == "spec":
                    table_spec_string = entry.valueString

    assert "user_table" in component_by_id
    assert (
        component_by_id["user_table"]["Table"]["spec"]["path"]
        == "/content/user_table/spec"
    )
    assert table_spec_string is not None
    assert '"columns"' in table_spec_string
    assert '"rows"' in table_spec_string


def test_add_region_table_preserves_object_cell_in_spec_json() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Table page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region", id="details_region", role="details", title="详情"
        )
    )

    frames = compiler.apply(
        AddRegionTableDelta(
            event="add_region_table",
            id="risk_table",
            region_id="details_region",
            columns=[
                {"key": "alarmLevel", "label": "告警等级"},
            ],
            rows=[
                {
                    "alarmLevel": {
                        "value": "3",
                        "visual_weight": 4,
                    }
                },
            ],
        )
    )

    table_spec_string = None
    for frame in frames:
        if (
            frame.dataModelUpdate
            and frame.dataModelUpdate.path == "/content/risk_table"
        ):
            for entry in frame.dataModelUpdate.contents:
                if entry.key == "spec":
                    table_spec_string = entry.valueString

    assert table_spec_string is not None
    json.loads(table_spec_string)
    spec = json.loads(table_spec_string)
    assert isinstance(spec["rows"][0]["alarmLevel"], dict)
    assert spec["rows"][0]["alarmLevel"] == {"value": "3", "visual_weight": 4}


def test_add_region_table_can_coexist_with_text_and_fact_in_same_region() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Mixed details page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region", id="details_region", role="details", title="详情"
        )
    )

    frames = []
    frames.extend(
        compiler.apply(
            AddRegionTextDelta(
                event="add_region_text",
                id="details_text",
                region_id="details_region",
                text="本周明细如下",
                usage_hint="body",
            )
        )
    )
    frames.extend(
        compiler.apply(
            AddRegionFactDelta(
                event="add_region_fact",
                id="details_fact",
                region_id="details_region",
                label="总条数",
                value="2",
            )
        )
    )
    frames.extend(
        compiler.apply(
            AddRegionTableDelta(
                event="add_region_table",
                id="details_table",
                region_id="details_region",
                columns=[{"key": "name", "label": "姓名"}],
                rows=[{"name": "王小虎"}],
            )
        )
    )

    component_ids = _slot_component_ids(frames)
    assert "details_text" in component_ids
    assert "details_fact" in component_ids
    assert "details_table" in component_ids


def test_add_region_line_chart_schema_can_be_parsed() -> None:
    parsed = SKELETON_DELTA_ADAPTER.validate_python(
        {
            "event": "add_region_line_chart",
            "id": "weekly_trend",
            "region_id": "summary_region",
            "title": "周趋势",
            "width": "100%",
            "settings": {
                "dimension": "day",
                "metrics": ["Email", "Union Ads"],
                "xTitle": "日期",
                "yTitle": "数量",
                "markPoint": True,
            },
            "chart_data": [
                {"day": "Mon", "Email": 10, "Union Ads": 5},
                {"day": "Tue", "Email": 20, "Union Ads": 15},
            ],
        }
    )

    assert isinstance(parsed, AddRegionLineChartDelta)
    assert parsed.settings.dimension == "day"
    assert parsed.chart_data[0]["Email"] == 10


def test_add_region_line_chart_routes_and_emits_line_chart_component() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Line chart page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region", id="summary_region", role="summary", title="趋势摘要"
        )
    )

    frames = compiler.apply(
        AddRegionLineChartDelta(
            event="add_region_line_chart",
            id="weekly_trend",
            region_id="summary_region",
            title="周趋势",
            width="100%",
            settings={
                "dimension": "day",
                "metrics": ["Email", "Union Ads"],
                "xTitle": "日期",
                "yTitle": "数量",
                "markPoint": True,
            },
            chart_data=[
                {"day": "Mon", "Email": 10, "Union Ads": 5},
                {"day": "Tue", "Email": 20, "Union Ads": 15},
            ],
        )
    )

    component_by_id: dict[str, object] = {}
    chart_spec_string = None
    for frame in frames:
        if frame.surfaceUpdate:
            for component in frame.surfaceUpdate.components:
                component_by_id[component.id] = component.component
        if (
            frame.dataModelUpdate
            and frame.dataModelUpdate.path == "/content/weekly_trend"
        ):
            for entry in frame.dataModelUpdate.contents:
                if entry.key == "spec":
                    chart_spec_string = entry.valueString

    assert "weekly_trend" in component_by_id
    assert (
        component_by_id["weekly_trend"]["LineChart"]["spec"]["path"]
        == "/content/weekly_trend/spec"
    )
    assert chart_spec_string is not None
    assert '"title": "周趋势"' in chart_spec_string
    assert '"width": "100%"' in chart_spec_string
    assert '"settings"' in chart_spec_string
    assert '"chartData"' in chart_spec_string


def test_add_region_pie_chart_schema_can_be_parsed() -> None:
    parsed = SKELETON_DELTA_ADAPTER.validate_python(
        {
            "event": "add_region_pie_chart",
            "id": "traffic_share",
            "region_id": "summary_chart_region",
            "title": "渠道占比",
            "width": "100%",
            "settings": {"legend": "bottom"},
            "chart_data": [
                {
                    "radius": "50%",
                    "data": [
                        {"value": 1548, "name": "Search Engine"},
                        {"value": 679, "name": "Marketing", "selected": True},
                    ],
                }
            ],
        }
    )

    assert isinstance(parsed, AddRegionPieChartDelta)
    assert parsed.chart_data[0].data[1].selected is True


def test_add_region_pie_chart_routes_and_emits_pie_chart_component() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Pie chart page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region",
            id="summary_chart_region",
            role="summary",
            title="占比摘要",
        )
    )

    frames = compiler.apply(
        AddRegionPieChartDelta(
            event="add_region_pie_chart",
            id="traffic_share",
            region_id="summary_chart_region",
            title="流量来源占比",
            width="100%",
            settings={"legend": "bottom"},
            chart_data=[
                {
                    "radius": "50%",
                    "data": [
                        {"value": 1048, "name": "Search Engine"},
                        {"value": 735, "name": "Direct"},
                        {"value": 580, "name": "Email", "selected": True},
                    ],
                }
            ],
        )
    )

    component_by_id: dict[str, object] = {}
    chart_spec_string = None
    for frame in frames:
        if frame.surfaceUpdate:
            for component in frame.surfaceUpdate.components:
                component_by_id[component.id] = component.component
        if (
            frame.dataModelUpdate
            and frame.dataModelUpdate.path == "/content/traffic_share"
        ):
            for entry in frame.dataModelUpdate.contents:
                if entry.key == "spec":
                    chart_spec_string = entry.valueString

    assert "traffic_share" in component_by_id
    assert (
        component_by_id["traffic_share"]["PieChart"]["spec"]["path"]
        == "/content/traffic_share/spec"
    )
    assert chart_spec_string is not None
    assert '"title": "流量来源占比"' in chart_spec_string
    assert '"width": "100%"' in chart_spec_string
    assert '"settings"' in chart_spec_string
    assert '"chartData"' in chart_spec_string


def test_hero_facts_container_emits_appearance_hero_fact() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Hero appearance page"))

    frames = compiler.apply(
        AddRegionDelta(event="add_region", id="hero_region", role="hero", title="概览")
    )

    hero_facts_payload = None
    for frame in frames:
        if not frame.surfaceUpdate:
            continue
        for component in frame.surfaceUpdate.components:
            if component.id == "hero_region_facts":
                hero_facts_payload = component.component.get("Row")

    assert hero_facts_payload is not None
    assert hero_facts_payload["appearance"] == "hero_fact"


def test_hero_fact_items_mount_under_facts_container_and_keep_text_usage_hints() -> (
    None
):
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Hero facts page"))
    compiler.apply(
        AddRegionDelta(event="add_region", id="hero_region", role="hero", title="概览")
    )

    frames = compiler.apply(
        AddRegionFactDelta(
            event="add_region_fact",
            id="fact_total",
            region_id="hero_region",
            label="总访问量",
            value="1200",
        )
    )

    hero_facts_children = None
    label_hint = None
    value_hint = None
    for frame in frames:
        if not frame.surfaceUpdate:
            continue
        for component in frame.surfaceUpdate.components:
            if component.id == "hero_region_facts":
                hero_facts_children = component.component["Row"]["children"][
                    "explicitList"
                ]
            if component.id == "fact_total__label":
                label_hint = component.component["Text"]["usageHint"]
            if component.id == "fact_total__value":
                value_hint = component.component["Text"]["usageHint"]

    assert hero_facts_children is not None
    assert "fact_total" in hero_facts_children
    assert label_hint == "caption"
    assert value_hint == "body"


def test_add_region_mermaid_schema_can_be_parsed() -> None:
    parsed = SKELETON_DELTA_ADAPTER.validate_python(
        {
            "event": "add_region_mermaid",
            "id": "sequence_a",
            "region_id": "workflow_region",
            "title": "时序图",
            "diagram_type": "sequenceDiagram",
            "definition": "sequenceDiagram\\nA->>B: hello",
        }
    )

    assert isinstance(parsed, AddRegionMermaidDelta)
    assert parsed.diagram_type == "sequenceDiagram"
    assert parsed.definition.startswith("sequenceDiagram")


def test_add_region_mermaid_routes_sequence_diagram_to_flow_slot() -> None:
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Mermaid routing page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region", id="workflow_region", role="workflow", title="流程"
        )
    )

    frames = compiler.apply(
        AddRegionMermaidDelta(
            event="add_region_mermaid",
            id="sequence_a",
            region_id="workflow_region",
            title="时序图",
            diagram_type="sequenceDiagram",
            definition="sequenceDiagram\\nA->>B: hello",
        )
    )

    flow_children = None
    for frame in frames:
        if not frame.surfaceUpdate:
            continue
        for component in frame.surfaceUpdate.components:
            if component.id == "workflow_region_flow":
                flow_children = component.component["Column"]["children"][
                    "explicitList"
                ]

    assert flow_children is not None
    assert "sequence_a" in flow_children


def test_add_region_mermaid_routes_er_diagram_to_text_slot_and_emits_spec_without_style_fields() -> (
    None
):
    compiler = SkeletonCompiler()
    compiler.apply(InitPlanDelta(event="init_plan", title="Mermaid details page"))
    compiler.apply(
        AddRegionDelta(
            event="add_region", id="details_region", role="details", title="结构详情"
        )
    )

    frames = compiler.apply(
        AddRegionMermaidDelta(
            event="add_region_mermaid",
            id="er_schema",
            region_id="details_region",
            title="ER 结构图",
            diagram_type="erDiagram",
            definition="erDiagram\\nUSER ||--o{ ORDER : places",
        )
    )

    details_body_children = None
    mermaid_spec_string = None
    component_by_id: dict[str, object] = {}
    for frame in frames:
        if frame.surfaceUpdate:
            for component in frame.surfaceUpdate.components:
                component_by_id[component.id] = component.component
                if component.id == "details_region_body":
                    details_body_children = component.component["Column"]["children"][
                        "explicitList"
                    ]
        if frame.dataModelUpdate and frame.dataModelUpdate.path == "/content/er_schema":
            for entry in frame.dataModelUpdate.contents:
                if entry.key == "spec":
                    mermaid_spec_string = entry.valueString

    assert details_body_children is not None
    assert "er_schema" in details_body_children
    assert (
        component_by_id["er_schema"]["Mermaid"]["spec"]["path"]
        == "/content/er_schema/spec"
    )
    assert mermaid_spec_string is not None
    assert '"title": "ER 结构图"' in mermaid_spec_string
    assert '"diagramType": "erDiagram"' in mermaid_spec_string
    assert '"definition": "erDiagram' in mermaid_spec_string
    assert '"width"' not in mermaid_spec_string
    assert '"height"' not in mermaid_spec_string
