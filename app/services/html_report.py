"""把一次模拟结果导出为可独立打开的单文件 HTML 报告。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_STYLE_TAG = '<link rel="stylesheet" href="/static/style.css">'
_SCRIPT_TAG = '<script src="/static/result.js" defer></script>'


def _script_safe_json(data: dict[str, Any]) -> str:
    """序列化可安全嵌入 ``<script>`` 的 JSON，避免用户文本提前闭合标签。"""
    return (
        json.dumps(data, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_standalone_report(data: dict[str, Any], static_dir: Path) -> str:
    """基于线上结果页生成内嵌数据、样式和脚本的独立 HTML。"""
    static_dir = Path(static_dir)
    template = (static_dir / "result.html").read_text(encoding="utf-8")
    css = (static_dir / "style.css").read_text(encoding="utf-8")
    javascript = (static_dir / "result.js").read_text(encoding="utf-8")

    if _STYLE_TAG not in template or _SCRIPT_TAG not in template:
        raise ValueError("结果页模板缺少预期的 CSS 或 JavaScript 引用")

    embedded_data = _script_safe_json(data)
    style_block = f"<style>\n{css}\n</style>"
    script_block = (
        "<script>\n"
        f"window.__100_LIVES_RESULT__ = {embedded_data};\n"
        "window.__100_LIVES_STANDALONE__ = true;\n"
        "</script>\n"
        f"<script>\n{javascript}\n</script>"
    )
    return template.replace(_STYLE_TAG, style_block).replace(_SCRIPT_TAG, script_block)
