"""单文件 HTML 报告导出测试。"""
from __future__ import annotations

import json

from app.services.html_report import _script_safe_json, render_standalone_report


def test_script_safe_json_cannot_close_embedded_script():
    encoded = _script_safe_json({"profile": "测试 </script><script>alert(1)</script> & 内容"})
    assert "</script>" not in encoded
    assert "<script>" not in encoded
    assert "\\u003c/script\\u003e" in encoded
    assert json.loads(encoded)["profile"].startswith("测试 </script>")


def test_standalone_report_embeds_assets_and_data(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "result.html").write_text(
        '<html><head><link rel="stylesheet" href="/static/style.css"></head>'
        '<body><script src="/static/result.js" defer></script></body></html>',
        encoding="utf-8",
    )
    (static_dir / "style.css").write_text("body { color: black; }", encoding="utf-8")
    (static_dir / "result.js").write_text("document.body.dataset.ready = 'yes';", encoding="utf-8")

    html = render_standalone_report({"run_id": "demo", "request": {"years": 5}}, static_dir)

    assert "body { color: black; }" in html
    assert "document.body.dataset.ready" in html
    assert '"run_id": "demo"' in html
    assert "/static/style.css" not in html
    assert "/static/result.js" not in html
