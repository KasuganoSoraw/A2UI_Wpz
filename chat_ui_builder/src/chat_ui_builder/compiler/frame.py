from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from chat_ui_builder.planning.models import (
    A2UIFrame,
    AddDividerDelta,
    AddImageDelta,
    AddKeyValueDelta,
    AddLineChartDelta,
    AddMermaidDelta,
    AddPieChartDelta,
    AddSectionDelta,
    AddTableDelta,
    AddTopologyDelta,
    AddTextDelta,
    UpdateTableSpecDelta,
    AddListItemDelta,
    ComponentNode,
    DataMapEntry,
    InitSurfaceDelta,
)

logger = logging.getLogger(__name__)


@dataclass
class ContainerState:
  component_id: str
  container_type: str
  child_ids: list[str] = field(default_factory=list)
  appearance: str | None = None


class FrameCompiler:
  def __init__(self) -> None:
    self.surface_id = 'main'
    self.root_id = 'root'
    self.initialized = False
    self.containers: dict[str, ContainerState] = {}
    self.list_item_counts: dict[str, int] = {}
    self.used_ids: set[str] = set()
    self.aliases: dict[str, str] = {}
    self.page_parent_id = self.root_id
    self.local_child_order: dict[tuple[str, str], int] = {}
    self.handlers: dict[type, Callable[[Any], list[A2UIFrame]]] = {
        InitSurfaceDelta: self._init_surface,
        AddSectionDelta: self._add_section,
        AddTextDelta: self._add_text,
        AddKeyValueDelta: self._add_key_value,
        AddImageDelta: self._add_image,
        AddDividerDelta: self._add_divider,
        AddTableDelta: self._add_table,
        UpdateTableSpecDelta: self._update_table_spec,
        AddLineChartDelta: self._add_line_chart,
        AddPieChartDelta: self._add_pie_chart,
        AddMermaidDelta: self._add_mermaid,
        AddTopologyDelta: self._add_topology,
        AddListItemDelta: self._add_list_item,
    }

  def apply(self, delta: Any) -> list[A2UIFrame]:
    logger.info('Compiling delta type=%s payload=%s', type(delta).__name__, delta.model_dump())
    handler = self.handlers.get(type(delta))
    if handler is None:
      return []
    return handler(delta)

  def _resolve_parent_id(self, parent_id: str) -> str:
    return self.aliases.get(parent_id, parent_id)

  def _ensure_container(self, parent_id: str) -> ContainerState:
    canonical_parent_id = self._resolve_parent_id(parent_id)
    if canonical_parent_id not in self.containers:
      raise ValueError(f'Unknown parent/container id: {parent_id}')
    return self.containers[canonical_parent_id]

  def _register_id(self, requested_id: str) -> str:
    base = requested_id.strip() or 'node'
    if base not in self.used_ids:
      self.used_ids.add(base)
      self.aliases.setdefault(requested_id, base)
      return base

    suffix = 2
    while f'{base}_{suffix}' in self.used_ids:
      suffix += 1
    canonical = f'{base}_{suffix}'
    logger.warning('Duplicate component id detected: %s -> %s', requested_id, canonical)
    self.used_ids.add(canonical)
    return canonical

  def _helper_id(self, base: str, suffix: str) -> str:
    candidate = f'{base}__{suffix}'
    if candidate not in self.used_ids:
      self.used_ids.add(candidate)
      return candidate
    counter = 2
    while f'{candidate}_{counter}' in self.used_ids:
      counter += 1
    resolved = f'{candidate}_{counter}'
    self.used_ids.add(resolved)
    return resolved

  def _append_child(self, parent_id: str, child_id: str, order: int | None = None) -> None:
    parent = self._ensure_container(parent_id)
    if parent.component_id == child_id:
      raise ValueError(f'Child id {child_id} cannot equal parent id {parent.component_id}')
    canonical_parent_id = self._resolve_parent_id(parent_id)
    if child_id not in parent.child_ids:
      parent.child_ids.append(child_id)
    if order is None:
      return
    if canonical_parent_id == self.page_parent_id:
      return
    self.local_child_order[(canonical_parent_id, child_id)] = order
    parent.child_ids.sort(
        key=lambda existing_id: self.local_child_order.get((canonical_parent_id, existing_id), 10_000)
    )

  def _surface_update(self, components: list[ComponentNode]) -> A2UIFrame:
    frame = A2UIFrame(surfaceUpdate={'surfaceId': self.surface_id, 'components': components})
    logger.debug('Compiled surfaceUpdate frame=%s', frame.model_dump(exclude_none=True))
    return frame

  def _data_update(self, path: str, contents: list[DataMapEntry]) -> A2UIFrame:
    frame = A2UIFrame(dataModelUpdate={'surfaceId': self.surface_id, 'path': path, 'contents': contents})
    logger.debug('Compiled dataModelUpdate frame=%s', frame.model_dump(exclude_none=True))
    return frame

  def _container_component(self, container: ContainerState) -> ComponentNode:
    explicit_children = list(container.child_ids)
    if container.container_type == 'Row':
      row_payload: dict[str, Any] = {
          'children': {'explicitList': explicit_children},
          'alignment': 'center',
          'distribution': 'start',
      }
      if container.appearance:
        row_payload['appearance'] = container.appearance
      component = {'Row': row_payload}
    elif container.container_type == 'List':
      component = {
          'List': {
              'children': {'explicitList': explicit_children},
              'direction': 'vertical',
              'alignment': 'stretch',
          }
      }
    elif container.container_type == 'Timeline':
      component = {
          'Timeline': {
              'children': {'explicitList': explicit_children},
          }
      }
    else:
      column_payload: dict[str, Any] = {
          'children': {'explicitList': explicit_children},
          'alignment': 'stretch',
          'distribution': 'start',
      }
      if container.appearance:
        column_payload['appearance'] = container.appearance
      component = {'Column': column_payload}
    return ComponentNode(id=container.component_id, component=component)

  def _init_surface(self, delta: InitSurfaceDelta) -> list[A2UIFrame]:
    self.surface_id = delta.surface_id
    self.initialized = True
    self.containers = {
        self.root_id: ContainerState(component_id=self.root_id, container_type='Row')
    }
    self.used_ids = {self.root_id}
    self.aliases = {self.root_id: self.root_id}
    self.local_child_order = {}
    self.page_parent_id = self.root_id

    root_component = ComponentNode(
        id=self.root_id,
        component={
            'Row': {
                'children': {'explicitList': []},
                'alignment': 'stretch',
                'distribution': 'start',
            }
        },
    )

    begin = A2UIFrame(
        beginRendering={
            'surfaceId': self.surface_id,
            'root': self.root_id,
            'styles': delta.theme.model_dump(exclude_none=True) if delta.theme else None,
        }
    )
    logger.debug('Compiled beginRendering frame=%s', begin.model_dump(exclude_none=True))
    return [begin, self._surface_update([root_component])]

  def _add_section(self, delta: AddSectionDelta) -> list[A2UIFrame]:
    actual_parent_id = self.page_parent_id if delta.parent_id == self.root_id else delta.parent_id
    parent = self._ensure_container(actual_parent_id)
    section_id = self._register_id(delta.id)
    if section_id == parent.component_id:
      raise ValueError(f'Section id {section_id} cannot equal parent id {parent.component_id}')

    self._append_child(actual_parent_id, section_id, delta.order)
    self.containers[section_id] = ContainerState(
        component_id=section_id,
        container_type=delta.layout,
        appearance=delta.appearance,
    )

    parent_component = self._container_component(parent)
    section_component = self._container_component(self.containers[section_id])
    return [self._surface_update([parent_component, section_component])]

  def _add_text(self, delta: AddTextDelta) -> list[A2UIFrame]:
    parent_id = delta.parent_id
    parent = self._ensure_container(parent_id)
    text_id = self._register_id(delta.id)
    if text_id == parent.component_id:
      raise ValueError(f'Text id {text_id} cannot equal parent id {parent.component_id}')
    self._append_child(parent_id, text_id)
    parent_update = self._container_component(parent)
    text_component = ComponentNode(
        id=text_id,
        component={'Text': {'text': {'path': f'/content/{text_id}/text'}, 'usageHint': delta.usage_hint}},
    )
    return [
        self._surface_update([parent_update, text_component]),
        self._data_update(f'/content/{text_id}', [DataMapEntry(key='text', valueString=delta.text)]),
    ]

  def _add_key_value(self, delta: AddKeyValueDelta) -> list[A2UIFrame]:
    parent_id = delta.parent_id
    parent = self._ensure_container(parent_id)
    group_id = self._register_id(delta.id)
    if group_id == parent.component_id:
      raise ValueError(f'Key/value id {group_id} cannot equal parent id {parent.component_id}')
    label_id = self._helper_id(group_id, 'label')
    value_id = self._helper_id(group_id, 'value')
    self._append_child(parent_id, group_id)
    parent_update = self._container_component(parent)
    group = ComponentNode(
        id=group_id,
        component={
            'Column': {
                'children': {'explicitList': [label_id, value_id]},
                'alignment': 'stretch',
                'distribution': 'start',
            }
        },
    )
    label = ComponentNode(id=label_id, component={'Text': {'text': {'path': f'/content/{group_id}/label'}, 'usageHint': 'caption'}})
    value = ComponentNode(id=value_id, component={'Text': {'text': {'path': f'/content/{group_id}/value'}, 'usageHint': 'body'}})
    return [
        self._surface_update([parent_update, group, label, value]),
        self._data_update(
            f'/content/{group_id}',
            [
                DataMapEntry(key='label', valueString=delta.label),
                DataMapEntry(key='value', valueString=delta.value),
            ],
        ),
    ]

  def _add_image(self, delta: AddImageDelta) -> list[A2UIFrame]:
    parent_id = delta.parent_id
    parent = self._ensure_container(parent_id)
    image_id = self._register_id(delta.id)
    if image_id == parent.component_id:
      raise ValueError(f'Image id {image_id} cannot equal parent id {parent.component_id}')
    self._append_child(parent_id, image_id)
    parent_update = self._container_component(parent)
    image_props: dict[str, Any] = {'url': {'path': f'/content/{image_id}/url'}}
    if delta.usage_hint:
      image_props['usageHint'] = delta.usage_hint
    image = ComponentNode(id=image_id, component={'Image': image_props})
    return [
        self._surface_update([parent_update, image]),
        self._data_update(f'/content/{image_id}', [DataMapEntry(key='url', valueString=delta.url)]),
    ]

  def _add_spec_component(
      self,
      *,
      requested_id: str,
      parent_id: str,
      component_name: str,
      spec_json: str,
  ) -> list[A2UIFrame]:
    parent = self._ensure_container(parent_id)
    component_id = self._register_id(requested_id)
    if component_id == parent.component_id:
      raise ValueError(f'{component_name} id {component_id} cannot equal parent id {parent.component_id}')

    self._append_child(parent_id, component_id)

    parent_update = self._container_component(parent)
    spec_component = ComponentNode(
        id=component_id,
        component={component_name: {'spec': {'path': f'/content/{component_id}/spec'}}},
    )

    return [
        self._surface_update([parent_update, spec_component]),
        self._data_update(f'/content/{component_id}', [DataMapEntry(key='spec', valueString=spec_json)]),
    ]

  def _add_table(self, delta: AddTableDelta) -> list[A2UIFrame]:
    return self._add_spec_component(
        requested_id=delta.id,
        parent_id=delta.parent_id,
        component_name='Table',
        spec_json=delta.spec_json,
    )

  def _update_table_spec(self, delta: UpdateTableSpecDelta) -> list[A2UIFrame]:
    # 该路径只做“更新已有 table 的数据模型”，不创建新组件、不改父容器 children。
    # streaming append_table_rows 若继续复用 AddTableDelta 会触发 _register_id + _append_child，
    # 导致页面上出现重复 table。这里补一个最小能力专门做数据刷新。
    table_id = self.aliases.get(delta.id, delta.id)
    if table_id not in self.used_ids:
      raise ValueError(f'Unknown table id for update_table_spec: {delta.id}')
    return [
        self._data_update(f'/content/{table_id}', [DataMapEntry(key='spec', valueString=delta.spec_json)]),
    ]

  def _add_line_chart(self, delta: AddLineChartDelta) -> list[A2UIFrame]:
    return self._add_spec_component(
        requested_id=delta.id,
        parent_id=delta.parent_id,
        component_name='LineChart',
        spec_json=delta.spec_json,
    )

  def _add_pie_chart(self, delta: AddPieChartDelta) -> list[A2UIFrame]:
    return self._add_spec_component(
        requested_id=delta.id,
        parent_id=delta.parent_id,
        component_name='PieChart',
        spec_json=delta.spec_json,
    )

  def _add_mermaid(self, delta: AddMermaidDelta) -> list[A2UIFrame]:
    return self._add_spec_component(
        requested_id=delta.id,
        parent_id=delta.parent_id,
        component_name='Mermaid',
        spec_json=delta.spec_json,
    )

  def _add_topology(self, delta: AddTopologyDelta) -> list[A2UIFrame]:
    return self._add_spec_component(
        requested_id=delta.id,
        parent_id=delta.parent_id,
        component_name='TopologyGraph',
        spec_json=delta.spec_json,
    )

  def _add_divider(self, delta: AddDividerDelta) -> list[A2UIFrame]:
    parent_id = delta.parent_id
    parent = self._ensure_container(parent_id)
    divider_id = self._register_id(delta.id)
    if divider_id == parent.component_id:
      raise ValueError(f'Divider id {divider_id} cannot equal parent id {parent.component_id}')
    self._append_child(parent_id, divider_id)
    parent_update = self._container_component(parent)
    divider = ComponentNode(id=divider_id, component={'Divider': {'axis': 'horizontal'}})
    return [self._surface_update([parent_update, divider])]

  def _add_list_item(self, delta: AddListItemDelta) -> list[A2UIFrame]:
    parent_id = delta.parent_id
    parent = self._ensure_container(parent_id)
    item_index = self.list_item_counts.get(parent.component_id, 0) + 1
    self.list_item_counts[parent.component_id] = item_index
    item_prefix = self._register_id(f'{delta.id}_{item_index}')
    wrapper_id = self._helper_id(item_prefix, 'wrapper')
    title_id = self._helper_id(item_prefix, 'title')
    detail_id = self._helper_id(item_prefix, 'detail')

    if wrapper_id == parent.component_id:
      raise ValueError(f'List item wrapper id {wrapper_id} cannot equal parent id {parent.component_id}')

    self._append_child(parent_id, wrapper_id)
    parent_update = self._container_component(parent)
    wrapper_children = [title_id] + ([detail_id] if delta.detail else [])
    content_id = self._helper_id(item_prefix, 'content')
    timeline_card_id = self._helper_id(item_prefix, 'card') if parent.container_type == 'Timeline' else None
    if parent.container_type == 'Timeline':
      wrapper = ComponentNode(
          id=wrapper_id,
          component={
              'TimelineItem': {
                  'child': timeline_card_id,
              }
          },
      )
    else:
      wrapper = ComponentNode(
          id=wrapper_id,
          component={
              'Card': {
                  'child': content_id
              }
          },
      )

    item_surface_components = [parent_update, wrapper]
    if timeline_card_id:
      item_surface_components.append(ComponentNode(id=timeline_card_id, component={'Card': {'child': content_id}}))

    content = ComponentNode(
        id=content_id,
        component={
            'Column': {
                'children': {'explicitList': wrapper_children},
                'alignment': 'stretch',
                'distribution': 'start',
            }
        },
    )
    title = ComponentNode(
        id=title_id,
        component={
            'Text': {
                'text': {'path': f'/lists/{parent.component_id}/{item_prefix}/title'},
                'usageHint': delta.title_usage_hint or 'body',
            }
        },
    )
    components = item_surface_components + [content, title]
    contents = [DataMapEntry(key='title', valueString=delta.title)]
    if delta.detail:
      components.append(
          ComponentNode(
              id=detail_id,
              component={
                  'Text': {
                      'text': {'path': f'/lists/{parent.component_id}/{item_prefix}/detail'},
                      'usageHint': delta.detail_usage_hint or 'caption',
                  }
              },
          )
      )
      contents.append(DataMapEntry(key='detail', valueString=delta.detail))
    return [
        self._surface_update(components),
        self._data_update(f'/lists/{parent.component_id}/{item_prefix}', contents),
    ]
