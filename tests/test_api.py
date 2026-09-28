# -*- coding: utf-8 -*-
"""API 端到端测试：完整跑通一次模拟（离线 Mock LLM），覆盖所有端点。"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.config import settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "runs_dir", tmp_path / "runs")
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client


VALID_REQUEST = {
    "profile": "想在闲暇时间培养一项可以长期坚持的爱好，每周有一个下午可以投入。",
    "choice_a": "每周参加陶艺课，练习手作",
    "choice_b": "学习摄影，记录日常与自然",
    "years": 2,
    "num_lives": 2,
}


def _wait_done(client: TestClient, run_id: str, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        resp = client.get(f"/api/status/{run_id}")
        assert resp.status_code == 200, resp.text
        last = resp.json()
        if last["stage"] in ("done", "failed"):
            return last
        time.sleep(0.05)
    pytest.fail(f"模拟超时未完成：{last}")


def _run_simulation(client: TestClient) -> tuple[str, dict]:
    resp = client.post("/api/simulate", json=VALID_REQUEST)
    assert resp.status_code == 202, resp.text
    run_id = resp.json()["run_id"]
    status = _wait_done(client, run_id)
    assert status["stage"] == "done", status
    result = client.get(f"/api/result/{run_id}")
    assert result.status_code == 200
    return run_id, result.json()


# ---------------------------------------------------------------------------
# 基础端点
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["llm_configured"] is True  # conftest 强制 LLM_MOCK=1


def test_index_and_result_pages(client):
    resp = client.get("/")
    assert resp.status_code == 200
    resp = client.get("/result/20260915_000000_abcdef")
    assert resp.status_code == 200


def test_status_unknown_run(client):
    assert client.get("/api/status/99999999_000000_abcdef").status_code == 404
    assert client.get("/api/status/../../etc").status_code in (404, 301)


def test_result_unknown_run(client):
    assert client.get("/api/result/99999999_000000_abcdef").status_code == 404


# ---------------------------------------------------------------------------
# 请求校验
# ---------------------------------------------------------------------------

def test_simulate_validation(client):
    # profile 太短
    bad = dict(VALID_REQUEST, profile="太短")
    assert client.post("/api/simulate", json=bad).status_code == 422
    # num_lives 超界
    bad = dict(VALID_REQUEST, num_lives=1)
    assert client.post("/api/simulate", json=bad).status_code == 422
    bad = dict(VALID_REQUEST, num_lives=101)
    assert client.post("/api/simulate", json=bad).status_code == 422
    # years 超界
    bad = dict(VALID_REQUEST, years=11)
    assert client.post("/api/simulate", json=bad).status_code == 422
    # 缺字段
    assert client.post("/api/simulate", json={"profile": "x" * 20}).status_code == 422


def test_simulate_requires_llm(client, monkeypatch):
    from app.main import app  # noqa: F401
    from app.services import llm as llm_module
    monkeypatch.setattr(llm_module, "llm_configured", lambda: False)
    resp = client.post("/api/simulate", json=VALID_REQUEST)
    assert resp.status_code == 400
    assert "LLM" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 完整流水线（离线 Mock）
# ---------------------------------------------------------------------------

def test_full_simulation_run(client):
    run_id, result = _run_simulation(client)

    # 基本结构
    assert result["run_id"] == run_id
    assert result["disclaimer"]
    assert result["start_year"] >= 2026
    assert result["request"]["years"] == 2

    # 4 条轨迹（2 宇宙 × A/B），配对完整
    trajectories = result["trajectories"]
    assert len(trajectories) == 4
    ids = {t["id"] for t in trajectories}
    assert ids == {"a_u01", "a_u02", "b_u01", "b_u02"}
    for trajectory in trajectories:
        assert trajectory["complete"] if "complete" in trajectory else True
        assert len(trajectory["years"]) == 2
        assert trajectory["summary"]
        assert trajectory["cluster_name"]
        assert trajectory["final_career_score"] is not None
        assert trajectory["critic"] is not None

    # 汇总
    for label in ("A", "B"):
        summary = result["choice_summaries"][label]
        assert summary["num_lives"] == 2
        assert 0 <= summary["overall_score"] <= 100
        assert summary["clusters"]
        cluster_ids = [tid for c in summary["clusters"] for tid in c["trajectory_ids"]]
        expected = {t["id"] for t in trajectories if t["choice"] == label}
        assert sorted(cluster_ids) == sorted(expected)  # 聚类覆盖全部轨迹

    # 配对比较：每个指标的世界数总和 == 共享宇宙数
    matched = result["matched_comparison"]
    assert matched["universe_count"] == 2
    for metric in matched["metrics"].values():
        assert metric["a_better"] + metric["b_better"] + metric["close"] == 2

    # 洞察报告
    insight = result["insight"]
    for field in ("structural_difference", "deciding_factors", "biggest_risk"):
        assert insight[field]

    # 统计：LLM 调用次数 > 0，结果文件已保存
    assert result["stats"]["llm_calls"] > 0
    assert result["stats"]["duration_seconds"] >= 0
    assert result["stats"]["failed_trajectories"] == 0


def test_result_json_file_persisted(client, tmp_path):
    run_id, _ = _run_simulation(client)
    saved = (tmp_path / "runs" / f"{run_id}.json").read_text(encoding="utf-8")
    assert run_id in saved
    import json
    assert json.loads(saved)["run_id"] == run_id


def test_result_standalone_html_file_persisted(client, tmp_path):
    run_id, _ = _run_simulation(client)
    saved = (tmp_path / "runs" / f"{run_id}.html").read_text(encoding="utf-8")
    assert run_id in saved
    assert "window.__100_LIVES_RESULT__" in saved
    assert "window.__100_LIVES_STANDALONE__ = true" in saved
    assert '<link rel="stylesheet" href="/static/style.css">' not in saved
    assert '<script src="/static/result.js"' not in saved
    assert "<style>" in saved
    assert "min-width: 112px" in saved
    assert ".download-report span { display: none" not in saved

    # 即使磁盘上是旧版 HTML，下载时也应使用当前模板和样式重新生成。
    (tmp_path / "runs" / f"{run_id}.html").write_text("旧版报告", encoding="utf-8")
    download = client.get(f"/api/result/{run_id}/html")
    assert download.status_code == 200
    assert download.content == saved.encode("utf-8")
    assert "attachment" in download.headers["content-disposition"]
    assert download.headers["cache-control"] == "no-store, max-age=0"


def test_result_html_download_unknown_run(client):
    resp = client.get("/api/result/99999999_000000_abcdef/html")
    assert resp.status_code == 404


def test_status_detail_during_run(client, monkeypatch):
    # 用一个慢一点的 Mock（每次调用延迟 30ms）验证状态机能被轮询观察到中间阶段
    import asyncio

    from app.services import llm as llm_module
    from app.services.llm import MockLLMProvider

    class SlowMock(MockLLMProvider):
        async def complete(self, system_prompt, user_prompt, *, temperature=0.8, max_tokens=4096):
            await asyncio.sleep(0.03)
            return await super().complete(
                system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens
            )

    llm_module.set_provider(SlowMock(seed=3))

    resp = client.post("/api/simulate", json=VALID_REQUEST)
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    seen_stages = set()
    seen_details = []
    deadline = time.monotonic() + 60
    final = None
    while time.monotonic() < deadline:
        status = client.get(f"/api/status/{run_id}").json()
        seen_stages.add(status["stage"])
        seen_details.append(status["detail"])
        assert 0.0 <= status["progress"] <= 1.0
        final = status
        if status["stage"] in ("done", "failed"):
            break
        time.sleep(0.01)
    assert final["stage"] == "done", final
    assert final["progress"] == 1.0
    # 能观察到中间阶段与明细字段
    assert "universes" in seen_stages
    assert "simulation" in seen_stages
    universes_detail = next((d for d in seen_details if "universes_done" in d), None)
    assert universes_detail is not None and universes_detail["universes_total"] == 2
    sim_detail = next((d for d in seen_details if "done_a" in d), None)
    assert sim_detail is not None and sim_detail["total"] == 2


# ---------------------------------------------------------------------------
# Future Self 聊天
# ---------------------------------------------------------------------------

def test_future_self_chat(client):
    run_id, result = _run_simulation(client)
    trajectory = next(t for t in result["trajectories"] if t["choice"] == "A")

    resp = client.post("/api/future-self-chat", json={
        "run_id": run_id,
        "trajectory_id": trajectory["id"],
        "message": "这些年你后悔吗？",
        "history": [],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reply"]
    expected_year = result["start_year"] + result["request"]["years"] - 1
    assert body["future_year"] == expected_year

    # 带历史轮次
    resp2 = client.post("/api/future-self-chat", json={
        "run_id": run_id,
        "trajectory_id": trajectory["id"],
        "message": "那工作呢？",
        "history": [
            {"role": "user", "content": "这些年你后悔吗？"},
            {"role": "assistant", "content": body["reply"]},
        ],
    })
    assert resp2.status_code == 200


def test_future_self_chat_errors(client):
    run_id, result = _run_simulation(client)

    # 轨迹不存在
    resp = client.post("/api/future-self-chat", json={
        "run_id": run_id, "trajectory_id": "z_u99", "message": "你好", "history": [],
    })
    assert resp.status_code == 404

    # run 不存在
    resp = client.post("/api/future-self-chat", json={
        "run_id": "99999999_000000_abcdef", "trajectory_id": "a_u01",
        "message": "你好", "history": [],
    })
    assert resp.status_code == 404

    # message 为空
    resp = client.post("/api/future-self-chat", json={
        "run_id": run_id, "trajectory_id": "a_u01", "message": "  ", "history": [],
    })
    assert resp.status_code == 422

    # history 非法角色
    resp = client.post("/api/future-self-chat", json={
        "run_id": run_id, "trajectory_id": "a_u01", "message": "你好",
        "history": [{"role": "system", "content": "hax"}],
    })
    assert resp.status_code == 422
