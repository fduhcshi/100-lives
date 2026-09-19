"""从 LLM 文本输出中稳健地提取 JSON。

LLM 经常在 JSON 外面套一层说明文字或 ```json 围栏，本模块负责把这些
情况都兜住；同时修复常见的小问题（尾随逗号）。
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*\n?(.*?)```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


class JSONParseError(ValueError):
    """无法从文本中提取合法 JSON。"""


def _try_load(text: str) -> Any | None:
    """尝试直接解析，失败后做一次尾随逗号修复再解析。"""
    if not text or not text.strip():
        return None
    candidate = text.strip()
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        return json.loads(_TRAILING_COMMA_RE.sub(r"\1", candidate))
    except (json.JSONDecodeError, ValueError):
        return None


def _balanced_substrings(text: str) -> list[str]:
    """按括号配对从文本中切出所有可能的 JSON 片段（由外到内）。

    除了顶层片段，也包含嵌套在里面的片段（带嵌套深度，外层在前）——
    说明文字里出现多余的 '{' 时，真正的 JSON 对象不是顶层片段，
    但仍然可以被切出来。
    """
    results: list[tuple[int, int, str]] = []  # (depth, order, chunk)
    stack: list[tuple[str, int]] = []
    pairs = {"{": "}", "[": "]"}
    closers = {"}": "{", "]": "["}
    in_string = False
    escape = False
    order = 0
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            if in_string:
                escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in pairs:
            stack.append((ch, i))
        elif ch in closers and stack and stack[-1][0] == closers[ch]:
            _, start = stack.pop()
            depth = len(stack)
            results.append((depth, order, text[start : i + 1]))
            order += 1
    # 深度升序（顶层在前），同深度按出现顺序；上限防御异常超长输出
    results.sort(key=lambda item: item[0])
    return [chunk for _, _, chunk in results[:200]]


def extract_json(text: str) -> Any:
    """提取并解析第一个合法 JSON 值；失败抛出 JSONParseError。"""
    if not isinstance(text, str):
        raise JSONParseError(f"期望字符串，得到 {type(text).__name__}")

    # 1. 围栏内的内容优先
    for fenced in _FENCE_RE.findall(text):
        value = _try_load(fenced)
        if value is not None:
            return value

    # 2. 整段直接是 JSON
    value = _try_load(text)
    if value is not None:
        return value

    # 3. 括号配对切片（覆盖前面带说明文字 / 后面带补充说明的情况）
    for chunk in _balanced_substrings(text):
        value = _try_load(chunk)
        if value is not None:
            return value

    snippet = text.strip()[:120].replace("\n", " ")
    raise JSONParseError(f"无法从输出中提取 JSON，开头为：{snippet!r}")


def to_float(value: Any, default: float | None = None) -> float | None:
    """宽容地把 LLM 输出转成 float（支持 "72"、"72.5"、72、"72分" 等）。

    NaN / Infinity 视为无效（json.loads 允许裸 NaN，但 min/max 对 NaN 的
    比较语义会把 NaN 变成满分），返回 default 走"缺失"处理。
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        result = float(value)
        return default if (math.isnan(result) or math.isinf(result)) else result
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace("，", "").replace(",", ""))
        if match:
            return float(match.group(0))
    return default


def to_bool(value: Any, default: bool = False) -> bool:
    """宽容地把 LLM 输出转成 bool。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "y", "1", "是", "有", "发生了", "会"):
            return True
        if lowered in ("false", "no", "n", "0", "否", "没有", "无"):
            return False
    return default
