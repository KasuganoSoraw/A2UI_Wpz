from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from chat_ui_builder.planning.models import A2UIFrame, AddRegionDelta, AddSectionDelta, AddTextDelta

EmitLowLevel = Callable[[object], list[A2UIFrame]]


@dataclass(frozen=True)
class ArrangementSemantics:
  body_layout: Literal['column', 'row', 'none'] = 'column'
  facts_layout: Literal['row', 'column'] = 'row'


@dataclass
class RegionBuildContext:
  slot_parent: str
  delta: AddRegionDelta
  arrangement: ArrangementSemantics
  presentation_variant: str = 'standard'


@dataclass
class RegionBuildResult:
  archetype: str
  frames: list[A2UIFrame] = field(default_factory=list)
  slot_parents: dict[str, str] = field(default_factory=dict)


class RegionArchetypeBuilder:
  archetype_name = 'details_group'

  def build(self, context: RegionBuildContext, emit: EmitLowLevel) -> RegionBuildResult:
    raise NotImplementedError

  def _create_region_root(self, context: RegionBuildContext, emit: EmitLowLevel, *, layout: str = 'Column', appearance='region_in_root') -> list[A2UIFrame]:
    return emit(
        AddSectionDelta(
            event='add_section',
            id=context.delta.id,
            parent_id=context.slot_parent,
            layout=layout,
            appearance=appearance,
        )
    )

  def _create_header_and_body(
      self,
      context: RegionBuildContext,
      emit: EmitLowLevel,
      *,
      include_body_slot: bool,
  ) -> tuple[list[A2UIFrame], str]:
    region_id = context.delta.id
    frames: list[A2UIFrame] = []
    content_parent = region_id

    if context.delta.title or context.delta.description:
      header_id = f'{region_id}_header'
      frames.extend(
          emit(
              AddSectionDelta(
                  event='add_section',
                  id=header_id,
                  parent_id=region_id,
                  layout='Column',
                  order=10,
              )
          )
      )

      if context.delta.title:
        frames.extend(
          emit(
              AddTextDelta(
                  event='add_text',
                  id=f'{header_id}_title',
                  parent_id=header_id,
                  text=context.delta.title,
                  usage_hint='h2',
              )
          )
        )

      if context.delta.description:
        frames.extend(
          emit(
              AddTextDelta(
                  event='add_text',
                  id=f'{header_id}_description',
                  parent_id=header_id,
                  text=context.delta.description,
                  usage_hint='body',
              )
          )
        )

    if include_body_slot:
      body_layout = 'Column' if context.arrangement.body_layout == 'column' else 'Row'
      body_id = f'{region_id}_body'
      frames.extend(
          emit(
              AddSectionDelta(
                  event='add_section',
                  id=body_id,
                  parent_id=region_id,
                  layout=body_layout,
                  order=20,
              )
          )
      )
      content_parent = body_id

    return frames, content_parent

  def _create_section(
      self,
      emit: EmitLowLevel,
      *,
      section_id: str,
      parent_id: str,
      layout: str,
      order: int,
      appearance: str | None = None,
  ) -> list[A2UIFrame]:
    return emit(
        AddSectionDelta(
            event='add_section',
            id=section_id,
            parent_id=parent_id,
            layout=layout,
            order=order,
            appearance=appearance,
        )
    )

  def _default_slot_parents(self, region_id: str, content_parent: str) -> dict[str, str]:
    # 统一默认路由：多数内容落在正文内容父容器；其余 slot 默认落 region 根节点
    return {
        'text': content_parent,
        'image': content_parent,
        'divider': content_parent,
        'fact': region_id,
        'list_item': content_parent,
        'flow': content_parent,
    }


class HeroArchetypeBuilder(RegionArchetypeBuilder):
  archetype_name = 'hero_header'

  def build(self, context: RegionBuildContext, emit: EmitLowLevel) -> RegionBuildResult:
    region_id = context.delta.id
    frames = self._create_region_root(context, emit)
    header_body_frames, content_parent = self._create_header_and_body(
        context,
        emit,
        include_body_slot=context.arrangement.body_layout != 'none',
    )
    frames.extend(header_body_frames)

    facts_id = f'{region_id}_facts'
    frames.extend(
        self._create_section(
            emit,
            section_id=facts_id,
            parent_id=region_id,
            layout='Row' if context.arrangement.facts_layout == 'row' else 'Column',
            order=30,
            appearance='hero_fact',
        )
    )
    slot_parents = self._default_slot_parents(region_id, content_parent)
    slot_parents['fact'] = facts_id
    return RegionBuildResult(archetype=self.archetype_name, frames=frames, slot_parents=slot_parents)


class SummaryArchetypeBuilder(RegionArchetypeBuilder):
  archetype_name = 'summary_strip'

  def build(self, context: RegionBuildContext, emit: EmitLowLevel) -> RegionBuildResult:
    region_id = context.delta.id
    frames = self._create_region_root(context, emit)

    # Summary 的正文直接落在 facts 容器，保持紧凑结构。
    facts_id = f'{region_id}_facts'
    frames.extend(
        self._create_section(
            emit,
            section_id=facts_id,
            parent_id=region_id,
            layout='Row' if context.arrangement.facts_layout == 'row' else 'Column',
            order=20,
        )
    )

    slot_parents = self._default_slot_parents(region_id, facts_id)
    slot_parents['fact'] = facts_id
    return RegionBuildResult(archetype=self.archetype_name, frames=frames, slot_parents=slot_parents)


class DetailsArchetypeBuilder(RegionArchetypeBuilder):
  archetype_name = 'details_group'

  def build(self, context: RegionBuildContext, emit: EmitLowLevel) -> RegionBuildResult:
    region_id = context.delta.id
    frames = self._create_region_root(context, emit)
    header_body_frames, content_parent = self._create_header_and_body(context, emit, include_body_slot=True)
    frames.extend(header_body_frames)

    facts_id = f'{region_id}_facts'
    frames.extend(
        self._create_section(
            emit,
            section_id=facts_id,
            parent_id=region_id,
            layout='Row' if context.arrangement.facts_layout == 'row' else 'Column',
            order=30,
            appearance='detail_fact',
        )
    )
    slot_parents = self._default_slot_parents(region_id, content_parent)
    slot_parents['fact'] = facts_id
    return RegionBuildResult(archetype=self.archetype_name, frames=frames, slot_parents=slot_parents)


class WorkflowArchetypeBuilder(RegionArchetypeBuilder):
  archetype_name = 'workflow_panel'

  def build(self, context: RegionBuildContext, emit: EmitLowLevel) -> RegionBuildResult:
    region_id = context.delta.id
    frames = self._create_region_root(context, emit)
    header_body_frames, content_parent = self._create_header_and_body(context, emit, include_body_slot=True)
    frames.extend(header_body_frames)

    flow_id = f'{region_id}_flow'
    frames.extend(self._create_section(emit, section_id=flow_id, parent_id=region_id, layout='Column', order=30))
    slot_parents = self._default_slot_parents(region_id, content_parent)
    slot_parents['flow'] = flow_id
    return RegionBuildResult(archetype=self.archetype_name, frames=frames, slot_parents=slot_parents)


class SupportingArchetypeBuilder(RegionArchetypeBuilder):
  archetype_name = 'supporting_block'

  def build(self, context: RegionBuildContext, emit: EmitLowLevel) -> RegionBuildResult:
    region_id = context.delta.id
    frames = self._create_region_root(context, emit)
    header_body_frames, content_parent = self._create_header_and_body(context, emit, include_body_slot=True)
    frames.extend(header_body_frames)

    code_id = f'{region_id}_code'
    frames.extend(
        self._create_section(
            emit,
            section_id=code_id,
            parent_id=region_id,
            layout='Column',
            order=40,
            appearance='code_block',
        )
    )

    slot_parents = self._default_slot_parents(region_id, content_parent)
    slot_parents['code'] = code_id
    return RegionBuildResult(archetype=self.archetype_name, frames=frames, slot_parents=slot_parents)


class ListArchetypeBuilder(RegionArchetypeBuilder):
  archetype_name = 'list_panel'

  def build(self, context: RegionBuildContext, emit: EmitLowLevel) -> RegionBuildResult:
    region_id = context.delta.id
    frames = self._create_region_root(context, emit)
    header_body_frames, content_parent = self._create_header_and_body(context, emit, include_body_slot=False)
    frames.extend(header_body_frames)

    list_items_id = f'{region_id}_list_items'
    list_layout = 'Timeline' if context.presentation_variant == 'timeline' else 'List'
    frames.extend(
        self._create_section(
            emit,
            section_id=list_items_id,
            parent_id=region_id,
            layout=list_layout,
            order=30,
        )
    )
    slot_parents = self._default_slot_parents(region_id, content_parent)
    slot_parents['list_item'] = list_items_id
    return RegionBuildResult(archetype=self.archetype_name, frames=frames, slot_parents=slot_parents)


class RegionArchetypeRegistry:
  def __init__(self) -> None:
    details = DetailsArchetypeBuilder()
    self._builders: dict[str, RegionArchetypeBuilder] = {
        'hero': HeroArchetypeBuilder(),
        'summary': SummaryArchetypeBuilder(),
        'details': details,
        'workflow': WorkflowArchetypeBuilder(),
        'list': ListArchetypeBuilder(),
        'supporting': SupportingArchetypeBuilder(),
    }
    self._default_builder = details

  def builder_for(self, role: str) -> RegionArchetypeBuilder:
    return self._builders.get(role, self._default_builder)
