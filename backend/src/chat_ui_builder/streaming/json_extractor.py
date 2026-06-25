from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


class JsonExtractionResult(BaseModel):
  visible_snapshot: dict[str, Any]
  changes: dict[str, Any]


@dataclass
class _ParseResult:
  value: Any
  pos: int
  complete: bool


class JsonExtractor:
  """用于第一阶段输入准备的 JSON 提取器。

  只做两件事：
  1) 从可能断裂的累计 JSON 文本提取当前可见快照
  2) 相对上一轮快照计算 changes
  """

  def extract(
      self,
      *,
      raw_text: str,
      previous_snapshot: dict[str, Any] | None,
      is_stream_end: bool,
  ) -> JsonExtractionResult:
    current_snapshot = self._build_visible_snapshot(raw_text)
    changes = self._build_changes(
        previous_snapshot=previous_snapshot,
        current_snapshot=current_snapshot,
        is_stream_end=is_stream_end,
    )
    return JsonExtractionResult(visible_snapshot=current_snapshot, changes=changes)

  def _build_visible_snapshot(self, raw_text: str) -> dict[str, Any]:
    """提取当前已经完整可见的对象快照。

    规则：
    - 未闭合尾巴不能进入 snapshot（保守策略）
    - 数组允许“前若干完整元素可见”
    """

    if not raw_text:
      return {}

    text = raw_text.lstrip()
    if not text.startswith('{'):
      return {}

    parsed = self._parse_object(text, 0)
    if isinstance(parsed.value, dict):
      return parsed.value
    return {}

  def _build_changes(
      self,
      *,
      previous_snapshot: dict[str, Any] | None,
      current_snapshot: dict[str, Any],
      is_stream_end: bool,
  ) -> dict[str, Any]:
    """相对上一轮已提交 snapshot 计算 changes。"""

    previous = previous_snapshot or {}

    previous_paths = self._collect_paths(previous, '/')
    current_paths = self._collect_paths(current_snapshot, '/')
    new_paths = sorted(path for path in current_paths if path not in previous_paths)

    previous_array_items = self._count_array_items_by_path(previous, '/')
    current_array_items = self._count_array_items_by_path(current_snapshot, '/')
    new_array_items: dict[str, int] = {}
    for path, current_count in current_array_items.items():
      previous_count = previous_array_items.get(path, 0)
      if current_count > previous_count:
        new_array_items[path] = current_count - previous_count

    return {
        'new_paths': new_paths,
        'new_array_items': new_array_items,
        'is_stream_end': is_stream_end,
    }

  def _collect_paths(self, value: Any, base_path: str) -> set[str]:
    paths: set[str] = {base_path}
    if isinstance(value, dict):
      for key, child in value.items():
        child_path = f'{base_path.rstrip("/")}/{key}' if base_path != '/' else f'/{key}'
        paths.update(self._collect_paths(child, child_path))
    elif isinstance(value, list):
      for item in value:
        paths.update(self._collect_paths(item, base_path))
    return paths

  def _count_array_items_by_path(self, value: Any, base_path: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if isinstance(value, dict):
      for key, child in value.items():
        child_path = f'{base_path.rstrip("/")}/{key}' if base_path != '/' else f'/{key}'
        child_counts = self._count_array_items_by_path(child, child_path)
        for path, count in child_counts.items():
          counts[path] = max(counts.get(path, 0), count)
    elif isinstance(value, list):
      counts[base_path] = len(value)
      for item in value:
        child_counts = self._count_array_items_by_path(item, base_path)
        for path, count in child_counts.items():
          counts[path] = max(counts.get(path, 0), count)
    return counts

  def _skip_ws(self, text: str, pos: int) -> int:
    while pos < len(text) and text[pos] in {' ', '\n', '\r', '\t'}:
      pos += 1
    return pos

  def _parse_value(self, text: str, pos: int) -> _ParseResult:
    pos = self._skip_ws(text, pos)
    if pos >= len(text):
      return _ParseResult(None, pos, False)

    ch = text[pos]
    if ch == '{':
      return self._parse_object(text, pos)
    if ch == '[':
      return self._parse_array(text, pos)
    if ch == '"':
      return self._parse_string(text, pos)
    if ch in {'-', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'}:
      return self._parse_number(text, pos)
    if text.startswith('true', pos):
      return _ParseResult(True, pos + 4, True)
    if text.startswith('false', pos):
      return _ParseResult(False, pos + 5, True)
    if text.startswith('null', pos):
      return _ParseResult(None, pos + 4, True)
    return _ParseResult(None, pos, False)

  def _parse_object(self, text: str, pos: int) -> _ParseResult:
    if pos >= len(text) or text[pos] != '{':
      return _ParseResult({}, pos, False)

    result: dict[str, Any] = {}
    pos += 1

    while True:
      pos = self._skip_ws(text, pos)
      if pos >= len(text):
        return _ParseResult(result, pos, False)
      if text[pos] == '}':
        return _ParseResult(result, pos + 1, True)

      key_result = self._parse_string(text, pos)
      if not key_result.complete or not isinstance(key_result.value, str):
        return _ParseResult(result, pos, False)
      key = key_result.value
      pos = self._skip_ws(text, key_result.pos)
      if pos >= len(text) or text[pos] != ':':
        return _ParseResult(result, pos, False)

      value_result = self._parse_value(text, pos + 1)
      if not value_result.complete:
        # key 对应 value 未闭合时：
        # - 若是“部分可见子容器”（非空 dict/list），应保留已可见部分
        # - 若是半截基础类型（string/number/literal），不应进入 snapshot
        if isinstance(value_result.value, dict) and value_result.value:
          result[key] = value_result.value
        elif isinstance(value_result.value, list) and value_result.value:
          result[key] = value_result.value
        return _ParseResult(result, pos, False)
      result[key] = value_result.value

      pos = self._skip_ws(text, value_result.pos)
      if pos >= len(text):
        return _ParseResult(result, pos, False)
      if text[pos] == ',':
        pos += 1
        continue
      if text[pos] == '}':
        return _ParseResult(result, pos + 1, True)
      return _ParseResult(result, pos, False)

  def _parse_array(self, text: str, pos: int) -> _ParseResult:
    if pos >= len(text) or text[pos] != '[':
      return _ParseResult([], pos, False)

    result: list[Any] = []
    pos += 1

    while True:
      pos = self._skip_ws(text, pos)
      if pos >= len(text):
        # 数组尾部断裂时，已完整元素仍可见。
        return _ParseResult(result, pos, False)
      if text[pos] == ']':
        return _ParseResult(result, pos + 1, True)

      value_result = self._parse_value(text, pos)
      if not value_result.complete:
        # 当前元素未闭合时，停止并保留前序完整元素。
        return _ParseResult(result, pos, False)
      result.append(value_result.value)

      pos = self._skip_ws(text, value_result.pos)
      if pos >= len(text):
        return _ParseResult(result, pos, False)
      if text[pos] == ',':
        pos += 1
        continue
      if text[pos] == ']':
        return _ParseResult(result, pos + 1, True)
      return _ParseResult(result, pos, False)

  def _parse_string(self, text: str, pos: int) -> _ParseResult:
    if pos >= len(text) or text[pos] != '"':
      return _ParseResult('', pos, False)

    chars: list[str] = []
    i = pos + 1
    while i < len(text):
      ch = text[i]
      if ch == '"':
        return _ParseResult(''.join(chars), i + 1, True)
      if ch == '\\':
        i += 1
        if i >= len(text):
          return _ParseResult(''.join(chars), i, False)
        escaped = text[i]
        escape_map = {
            '"': '"',
            '\\': '\\',
            '/': '/',
            'b': '\b',
            'f': '\f',
            'n': '\n',
            'r': '\r',
            't': '\t',
        }
        if escaped in escape_map:
          chars.append(escape_map[escaped])
          i += 1
          continue
        if escaped == 'u':
          hex_digits = text[i + 1:i + 5]
          if len(hex_digits) < 4 or any(c not in '0123456789abcdefABCDEF' for c in hex_digits):
            return _ParseResult(''.join(chars), i, False)
          chars.append(chr(int(hex_digits, 16)))
          i += 5
          continue
        chars.append(escaped)
        i += 1
        continue
      chars.append(ch)
      i += 1
    return _ParseResult(''.join(chars), i, False)

  def _parse_number(self, text: str, pos: int) -> _ParseResult:
    i = pos
    if text[i] == '-':
      i += 1
      if i >= len(text):
        return _ParseResult(0, i, False)

    if i < len(text) and text[i] == '0':
      i += 1
    else:
      if i >= len(text) or not text[i].isdigit():
        return _ParseResult(0, i, False)
      while i < len(text) and text[i].isdigit():
        i += 1

    if i < len(text) and text[i] == '.':
      i += 1
      if i >= len(text) or not text[i].isdigit():
        return _ParseResult(0, i, False)
      while i < len(text) and text[i].isdigit():
        i += 1

    if i < len(text) and text[i] in {'e', 'E'}:
      i += 1
      if i < len(text) and text[i] in {'+', '-'}:
        i += 1
      if i >= len(text) or not text[i].isdigit():
        return _ParseResult(0, i, False)
      while i < len(text) and text[i].isdigit():
        i += 1

    raw_number = text[pos:i]
    try:
      value = float(raw_number) if any(ch in raw_number for ch in {'.', 'e', 'E'}) else int(raw_number)
      return _ParseResult(value, i, True)
    except ValueError:
      return _ParseResult(0, pos, False)


if __name__ == '__main__':
  # 最小自检
  extractor = JsonExtractor()

  # 用例 1：完整 JSON
  case1 = extractor.extract(
      raw_text='{"result":{"executionDetails":{},"items":[{"id":1},{"id":2}]}}',
      previous_snapshot=None,
      is_stream_end=False,
  )
  assert case1.visible_snapshot.get('result', {}).get('executionDetails') == {}

  # 用例 2：对象尾部断裂
  case2 = extractor.extract(
      raw_text='{"result":{"a":1,"b":2,"c":',
      previous_snapshot=None,
      is_stream_end=False,
  )
  assert case2.visible_snapshot == {'result': {'a': 1, 'b': 2}}

  # 用例 3：数组中间元素断裂
  case3 = extractor.extract(
      raw_text='{"result":{"exceptionInfos":[{"t":1},{"t":',
      previous_snapshot=None,
      is_stream_end=False,
  )
  assert case3.visible_snapshot == {'result': {'exceptionInfos': [{'t': 1}]}}

  # 用例 4：changes 计算
  prev = {'result': {'exceptionInfos': [{'t': 1}]}}
  curr = extractor.extract(
      raw_text='{"result":{"exceptionInfos":[{"t":1},{"t":2}],"summary":"ok"}}',
      previous_snapshot=prev,
      is_stream_end=True,
  )
  assert '/result/summary' in curr.changes['new_paths']
  assert curr.changes['new_array_items'].get('/result/exceptionInfos') == 1
  assert curr.changes['is_stream_end'] is True

  print('json_extractor minimal self-check passed')
