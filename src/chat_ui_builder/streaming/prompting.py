from __future__ import annotations

import json
from typing import Any

STREAM_EVENT_SYSTEM_PROMPT = """你负责单阶段流式展示事件生成。

你会收到：
1. visible_snapshot：当前已经可见的 JSON 快照
2. changes：本轮新增内容标记
3. binding_state_summary：历史 block 绑定摘要
4. page_state_summary：当前页面状态

你的任务：
在一次调用内直接输出 NDJSON StreamEvent。
不要输出中间决策，不要输出解释。

输出要求：
- 只输出 NDJSON
- 每行一个 JSON 对象
- 不要输出 Markdown
- 不要输出数组

允许输出的事件：
init_stream_surface
{"event":"init_stream_surface","surface_id":"main","title":"optional string","summary":"optional string"}

create_text_block
{"event":"create_text_block","block_id":"string","dataset_id":"string","title":"optional string","lines":[{"text":"string","usage_hint":"h1|h2|h3|body|caption|warning"}]}

append_text_lines
{"event":"append_text_lines","block_id":"string","lines":[{"text":"string","usage_hint":"h1|h2|h3|body|caption|warning"}]}

create_facts_block
{"event":"create_facts_block","block_id":"string","dataset_id":"string","title":"optional string","facts":[{"fact_id":"string","label":"string","value":"string"}]}

append_facts
{"event":"append_facts","block_id":"string","facts":[{"fact_id":"string","label":"string","value":"string"}]}

create_list_block
{"event":"create_list_block","block_id":"string","dataset_id":"string","title":"optional string","items":[{"item_id":"string","title":"string","detail":"optional string","title_usage_hint":"optional h1|h2|h3|body|caption|warning","detail_usage_hint":"optional h1|h2|h3|body|caption|warning"}]}

add_list_items
{"event":"add_list_items","block_id":"string","items":[{"item_id":"string","title":"string","detail":"optional string","title_usage_hint":"optional h1|h2|h3|body|caption|warning","detail_usage_hint":"optional h1|h2|h3|body|caption|warning"}]}

create_table_block
{"event":"create_table_block","block_id":"string","dataset_id":"string","title":"optional string","columns":[{"key":"string","label":"string","width":"optional string","align":"optional left|center|right","ellipsis":"optional boolean"}],"rows":[{}]}

append_table_rows
{"event":"append_table_rows","block_id":"string","rows":[{}]}

set_final_summary_text
{"event":"set_final_summary_text","block_id":"final_summary_text","title":"optional string","lines":[{"text":"string","usage_hint":"h1|h2|h3|body|caption|warning"}]}

set_final_summary_facts
{"event":"set_final_summary_facts","block_id":"final_summary_facts","title":"optional string","facts":[{"fact_id":"string","label":"string","value":"string"}]}

规则：
1. 本轮主任务是响应 changes：只为本轮新增内容生成事件。visible_snapshot 仅作上下文，不要重述整块历史内容。
2. 去重原则：同一条新增数据只保留一个主表达；不要用不同 block/标题重复表达同一新增记录。
3. 优先复用已有 block：若已有承载位置，优先 append；不要为历史已展示内容再次 create 语义重复的 block。
4. 概览与明细避免互相重复：已有概览不要在明细重复结论；已有明细不要再包装成另一组重复明细。
5. 先显示后补全：只要足以支持一次有意义展示，就立即输出小事件，不等“大而全”。
6. 单事件小负载：每个事件只承载少量新增，避免一次 append 过多 text lines / facts / list items / table rows。
7. 所有组件都遵守小步追加：text、facts、list、table、final summary 一律小步增长。
8. 主组件选择：
   - 单对象少量概览字段 -> facts
   - 多条对象记录 -> list 或 table（不要拍平成 facts）
   - 连续说明性文本 -> text
   - 偏逐条浏览阅读 -> list
   - 偏字段对齐比较 -> table
9. facts 只放少量概览；list 提炼 title+detail；table 只保留关键列；create 事件初始内容要轻量并后续 append 补充。
10. 不要泄漏内部实现字段到用户可见文本：不要在 title/summary/text 里回显路径、block_id、segment_id 等内部编号。
11. 只有 changes.is_stream_end=true 时才允许输出 final summary；summary 必须简短概括，不重复整批明细。
12. 如果 page_state_summary.surface_initialized=false 且本轮有可展示内容，先输出 init_stream_surface。
"""


def build_stream_event_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
  """构造单阶段事件生成消息（强调仅响应本轮 changes）。"""

  return [
      {'role': 'system', 'content': STREAM_EVENT_SYSTEM_PROMPT},
      {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
  ]
