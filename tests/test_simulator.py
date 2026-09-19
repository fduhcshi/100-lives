# -*- coding: utf-8 -*-
"""模拟流水线测试：宇宙生成、轨迹解析、Critic 重生成、聚类校验、配对统计。"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.models.trajectory import Trajectory, Universe
from app.services import cluster as cluster_service
from app.services import summarizer as summarizer_service
from app.services.llm import MockLLMProvider
from app.services import llm as llm_module
from app.services.simulator import (
    MAX_ATTEMPTS,
    TrajectoryParseError,
    _simulate_one,
    parse_trajectory_payload,
    simulate_choice,
)
from app.services.universe_generator import generate_universes

PROFILE = "我是一名 30 岁的运营专员，单身，最近在纠结要不要辞职去另一座城市发展。"
CHOICE_A = "留在现在的城市，继续当前工作"
CHOICE_B = "辞职去另一座城市，接受新工作"


def _universe(uid: int = 1) -> Universe:
    return Universe(
        id=uid,
        macro_environment="行业平稳增长",
        career_shock="第二年组织调整",
        financial_shock="第三年行情较好",
        relationship_shock="第四年家庭压力增加",
        opportunity="第三年出现创业邀请",
        random_event="认识一个关键朋友",
    )


def _trajectory_payload(years: int = 2, **overrides) -> dict:
    payload = {
        "summary": "两年里稳步上升，第二年抓住了机会。",
        "years": [
            {"year": i, "career": "职责扩大", "finance": "储蓄增加", "relationship": "稳定",
             "location": "上海", "wellbeing": "良好", "major_event": "进入新项目", "decision": "主动争取"}
            for i in range(1, years + 1)
        ],
        "features": {"career_direction": "up", "location_change": False, "startup": False,
                     "job_switch": False, "relationship_change": False,
                     "financial_direction": "up", "wellbeing_direction": "flat",
                     "main_theme": "steady_growth"},
        "final_scores": {"career": 75, "finance": 70, "relationship": 80, "wellbeing": 65, "regret": 30},
    }
    payload.update(overrides)
    return payload


def _critic_payload(accepted: bool = True, **overrides) -> dict:
    payload = {
        "consistency": 82, "realism": 78, "coherence": 80, "diversity": 75,
        "accepted": accepted, "problems": [] if accepted else ["年份之间因果衔接不足"],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 宇宙生成
# ---------------------------------------------------------------------------

async def test_generate_universes():
    semaphore = asyncio.Semaphore(5)
    progress_log = []

    universes = await generate_universes(
        PROFILE, years=5, n=7, start_year=2026, semaphore=semaphore,
        on_progress=lambda done, total: progress_log.append((done, total)),
    )
    assert len(universes) == 7
    assert [u.id for u in universes] == list(range(1, 8))
    for uni in universes:
        assert uni.macro_environment and uni.career_shock and uni.opportunity
    assert progress_log  # 进度回调被触发过


# ---------------------------------------------------------------------------
# 轨迹解析
# ---------------------------------------------------------------------------

def test_parse_trajectory_ok():
    trajectory = parse_trajectory_payload(_trajectory_payload(3), universe_id=4, choice_label="A", years_expected=3)
    assert trajectory.id == "a_u04"
    assert trajectory.choice == "A"
    assert trajectory.complete
    assert [y.year for y in trajectory.years] == [1, 2, 3]  # 相对年数被重排


def test_parse_trajectory_string_scores_and_directions():
    payload = _trajectory_payload()
    payload["final_scores"] = {"career": "72", "finance": 68.5, "relationship": "80分",
                               "wellbeing": 65, "regret": "30"}
    payload["features"]["career_direction"] = "上升"
    payload["features"]["location_change"] = "是"
    trajectory = parse_trajectory_payload(payload, 1, "B", 2)
    assert trajectory.final_career_score == 72.0
    assert trajectory.final_finance_score == 68.5
    assert trajectory.final_relationship_score == 80.0
    assert trajectory.features.career_direction == "up"
    assert trajectory.features.location_change is True


def test_parse_trajectory_too_few_years():
    with pytest.raises(TrajectoryParseError):
        parse_trajectory_payload(_trajectory_payload(1), 1, "A", 5)


def test_parse_trajectory_extra_years_truncated():
    trajectory = parse_trajectory_payload(_trajectory_payload(4), 1, "A", 2)
    assert len(trajectory.years) == 2


def test_parse_trajectory_missing_score():
    payload = _trajectory_payload()
    payload["final_scores"] = {"career": 70, "finance": 70, "relationship": 70, "wellbeing": 70}
    with pytest.raises(TrajectoryParseError):
        parse_trajectory_payload(payload, 1, "A", 2)


def test_parse_trajectory_score_clamped():
    payload = _trajectory_payload()
    payload["final_scores"] = {"career": 150, "finance": 70, "relationship": 70,
                               "wellbeing": 70, "regret": -5}
    trajectory = parse_trajectory_payload(payload, 1, "A", 2)
    assert trajectory.final_career_score == 100.0
    assert trajectory.regret_score == 0.0


# ---------------------------------------------------------------------------
# 生成 → Critic → 重生成
# ---------------------------------------------------------------------------

async def test_simulate_one_accept_first_try():
    llm_module.set_provider(MockLLMProvider(scripted=[
        json.dumps(_trajectory_payload(), ensure_ascii=False),
        json.dumps(_critic_payload(True), ensure_ascii=False),
    ]))
    semaphore = asyncio.Semaphore(2)
    trajectory, regen = await _simulate_one(PROFILE, "A", CHOICE_A, _universe(3), 2, 2026, semaphore)
    assert trajectory is not None and trajectory.complete
    assert trajectory.id == "a_u03"
    assert regen == 0
    assert trajectory.critic.accepted


async def test_simulate_one_regenerates_on_rejection():
    llm_module.set_provider(MockLLMProvider(scripted=[
        json.dumps(_trajectory_payload(), ensure_ascii=False),          # 第 1 次生成
        json.dumps(_critic_payload(False), ensure_ascii=False),         # 拒绝
        json.dumps(_trajectory_payload(), ensure_ascii=False),          # 第 2 次生成（带反馈）
        json.dumps(_critic_payload(True), ensure_ascii=False),          # 通过
    ]))
    semaphore = asyncio.Semaphore(2)
    trajectory, regen = await _simulate_one(PROFILE, "A", CHOICE_A, _universe(1), 2, 2026, semaphore)
    assert trajectory.regenerated == 1
    assert trajectory.critic.accepted


async def test_simulate_one_keeps_last_attempt_when_all_rejected():
    responses = []
    for _ in range(MAX_ATTEMPTS):
        responses.append(json.dumps(_trajectory_payload(), ensure_ascii=False))
        responses.append(json.dumps(_critic_payload(False), ensure_ascii=False))
    llm_module.set_provider(MockLLMProvider(scripted=responses))
    semaphore = asyncio.Semaphore(2)
    trajectory, regen = await _simulate_one(PROFILE, "B", CHOICE_B, _universe(2), 2, 2026, semaphore)
    # 保留最后一版，标记未通过
    assert trajectory is not None
    assert trajectory.critic.accepted is False
    assert trajectory.regenerated == MAX_ATTEMPTS - 1


async def test_simulate_choice_full_run_with_heuristic_mock():
    # 未 script 的 Mock：全部走启发式模板
    llm_module.set_provider(MockLLMProvider(seed=11))
    semaphore = asyncio.Semaphore(4)
    universes = [_universe(i) for i in range(1, 6)]
    progress = []

    trajectories = await simulate_choice(
        PROFILE, "A", CHOICE_A, universes, years=3, start_year=2026,
        semaphore=semaphore, on_progress=lambda _: progress.append(1),
    )
    assert len(trajectories) == 5
    assert {t.id for t in trajectories} == {f"a_u{i:02d}" for i in range(1, 6)}
    assert all(t.complete for t in trajectories)
    assert len(progress) == 5


# ---------------------------------------------------------------------------
# 聚类校验
# ---------------------------------------------------------------------------

async def test_cluster_sanitizes_ids():
    trajectories = []
    for i in range(1, 7):
        payload = _trajectory_payload()
        payload["summary"] = f"第 {i} 条测试轨迹"
        trajectories.append(parse_trajectory_payload(payload, i, "A", 2))

    llm_module.set_provider(MockLLMProvider(scripted=[json.dumps({
        "clusters": [
            {"name": "第一类", "description": "d", "trajectory_ids": ["a_u01", "a_u02", "a_u99"],
             "common_pattern": "p", "key_risk": "r", "key_opportunity": "o",
             "representative_trajectory_id": "a_u02"},
            {"name": "第二类", "description": "d", "trajectory_ids": ["a_u03"],
             "common_pattern": "p", "key_risk": "r", "key_opportunity": "o",
             "representative_trajectory_id": "a_u01"},  # 不在组内 → 修正为组内第一个
        ],
        "most_typical_trajectory_id": "a_u04",
        "most_surprising_trajectory_id": "a_u77",  # 不存在 → None
        "common_risks": ["风险一", 42, "   ", "风险二"],
        "common_opportunities": ["机会一"],
    }, ensure_ascii=False)]))

    result = await cluster_service.cluster_choice_async("A", CHOICE_A, trajectories)
    all_ids = [tid for c in result["clusters"] for tid in c.trajectory_ids]
    # 每条轨迹恰好一类：a_u99 被丢弃，a_u04/a_u05/a_u06 进入"其他路径"
    assert sorted(all_ids) == [f"a_u{i:02d}" for i in range(1, 7)]
    assert len(set(all_ids)) == 6
    first = next(c for c in result["clusters"] if c.name == "第一类")
    assert "a_u99" not in first.trajectory_ids
    assert first.representative_trajectory_id == "a_u02"
    second = next(c for c in result["clusters"] if c.name == "第二类")
    assert second.representative_trajectory_id == "a_u03"
    other = next(c for c in result["clusters"] if c.name == "其他路径")
    assert "a_u04" in other.trajectory_ids
    assert result["most_typical_trajectory_id"] == "a_u04"
    assert result["most_surprising_trajectory_id"] is None
    assert result["common_risks"] == ["风险一", "风险二"]


# ---------------------------------------------------------------------------
# Matched Pair 统计
# ---------------------------------------------------------------------------

def _make_trajectory(uid: int, choice: str, career: float, regret: float) -> Trajectory:
    payload = _trajectory_payload()
    payload["final_scores"] = {"career": career, "finance": 60, "relationship": 60,
                               "wellbeing": 60, "regret": regret}
    return parse_trajectory_payload(payload, uid, choice, 2)


def test_compute_matched_metrics_counts():
    universes = [_universe(1), _universe(2), _universe(3)]
    trajs_a = [
        _make_trajectory(1, "A", 70, 40),
        _make_trajectory(2, "A", 55, 30),
        _make_trajectory(3, "A", 80, 20),
    ]
    trajs_b = [
        _make_trajectory(1, "B", 50, 20),
        _make_trajectory(2, "B", 54, 31),
        _make_trajectory(3, "B", 90, 55),
    ]
    metrics, pairs = summarizer_service.compute_matched_metrics(universes, trajs_a, trajs_b)
    career = metrics["career"]
    assert career.a_better == 1  # 宇宙1: Δ=+20
    assert career.b_better == 1  # 宇宙3: Δ=-10
    assert career.close == 1     # 宇宙2: Δ=+1
    regret = metrics["regret"]   # 越低越好：宇宙1 A=40 B=20 → B 更好；宇宙3 A=20 B=55 → A 更好
    assert regret.a_better == 1
    assert regret.b_better == 1
    assert regret.close == 1
    assert len(pairs) == 3
    assert pairs[0]["max_abs_delta"] >= pairs[-1]["max_abs_delta"]  # 按分歧排序


def test_compute_matched_metrics_skips_unpaired():
    universes = [_universe(1), _universe(2)]
    trajs_a = [_make_trajectory(1, "A", 70, 30), _make_trajectory(2, "A", 60, 30)]
    trajs_b = [_make_trajectory(1, "B", 50, 30)]  # 宇宙2 的 B 缺失
    metrics, pairs = summarizer_service.compute_matched_metrics(universes, trajs_a, trajs_b)
    assert len(pairs) == 1
    assert metrics["career"].a_better == 1


def test_choice_summary_overall_score_uses_inverse_regret():
    trajectory = _make_trajectory(1, "A", career=80, regret=20)
    trajectory.final_finance_score = 70
    trajectory.final_relationship_score = 60
    trajectory.final_wellbeing_score = 50
    summary = summarizer_service.build_choice_summary("测试选择", [trajectory], {"clusters": []})
    # (职业80 + 财务70 + 关系60 + 满意度50 + 低后悔80) / 5 = 68
    assert summary.overall_score == 68.0


# ---------------------------------------------------------------------------
# 评审后新增：类型/NaN/降级路径
# ---------------------------------------------------------------------------

async def test_parse_type_error_goes_through_retry_loop():
    # pydantic ValidationError（LLM 把字符串字段输出成数字）必须走生成重试，
    # 而不是绕过循环直接报废宇宙
    bad_type = _trajectory_payload()
    bad_type["years"][0]["finance"] = 85000
    llm_module.set_provider(MockLLMProvider(scripted=[
        json.dumps(bad_type, ensure_ascii=False),
        json.dumps(_trajectory_payload(), ensure_ascii=False),
        json.dumps(_critic_payload(True), ensure_ascii=False),
    ]))
    semaphore = asyncio.Semaphore(2)
    trajectory, regen = await _simulate_one(PROFILE, "A", CHOICE_A, _universe(1), 2, 2026, semaphore)
    assert trajectory is not None
    assert regen == 1
    assert trajectory.critic.accepted


async def test_parse_nan_score_triggers_retry():
    # NaN 不能变成满分 100；应按"评分缺失"进入重试
    bad = _trajectory_payload()
    bad["final_scores"] = {"career": float("nan"), "finance": 70, "relationship": 70,
                           "wellbeing": 70, "regret": 30}
    llm_module.set_provider(MockLLMProvider(scripted=[
        json.dumps(bad, ensure_ascii=False),
        json.dumps(_trajectory_payload(), ensure_ascii=False),
        json.dumps(_critic_payload(True), ensure_ascii=False),
    ]))
    semaphore = asyncio.Semaphore(2)
    trajectory, regen = await _simulate_one(PROFILE, "A", CHOICE_A, _universe(1), 2, 2026, semaphore)
    assert trajectory is not None and regen == 1
    assert trajectory.final_career_score is not None


async def test_keep_last_parsed_when_later_attempts_fail():
    # 第 1 次解析成功但被 Critic 拒绝；第 2/3 次生成调用失败：
    # 必须保留第 1 次解析版本，而不是让配对宇宙缺腿
    responses = [
        json.dumps(_trajectory_payload(), ensure_ascii=False),
        json.dumps(_critic_payload(False), ensure_ascii=False),
        "网关持续返回 HTTP 503", "网关持续返回 HTTP 503",   # 第 2 次：解析失败×2
        "网关持续返回 HTTP 503", "网关持续返回 HTTP 503",   # 第 3 次：解析失败×2
    ]
    llm_module.set_provider(MockLLMProvider(scripted=responses))
    semaphore = asyncio.Semaphore(2)
    trajectory, regen = await _simulate_one(PROFILE, "A", CHOICE_A, _universe(1), 2, 2026, semaphore)
    assert trajectory is not None
    assert trajectory.critic.accepted is False
    assert regen == MAX_ATTEMPTS - 1


async def test_soft_critic_marks_unchecked_on_garbage_critic():
    # Critic 两次都返回非 JSON：_soft_critic 捕获 LLMError，checked=False 标记
    llm_module.set_provider(MockLLMProvider(scripted=[
        json.dumps(_trajectory_payload(), ensure_ascii=False),
        "这不是 JSON", "这也不是 JSON",
    ]))
    semaphore = asyncio.Semaphore(2)
    trajectory, _ = await _simulate_one(PROFILE, "A", CHOICE_A, _universe(1), 2, 2026, semaphore)
    assert trajectory is not None
    assert trajectory.critic.checked is False
    assert trajectory.critic.problems


async def test_cluster_falls_back_when_llm_garbage_json():
    # 聚类 LLM 两次非 JSON：call_llm_json 现在抛 LLMError，cluster 兜底生效，
    # 而不是让整个 run 失败
    trajectories = []
    for i in range(1, 5):
        payload = _trajectory_payload()
        payload["summary"] = f"第 {i} 条测试轨迹"
        trajectories.append(parse_trajectory_payload(payload, i, "A", 2))
    llm_module.set_provider(MockLLMProvider(scripted=["垃圾", "垃圾"]))
    result = await cluster_service.cluster_choice_async("A", CHOICE_A, trajectories)
    all_ids = [tid for c in result["clusters"] for tid in c.trajectory_ids]
    assert sorted(all_ids) == [f"a_u{i:02d}" for i in range(1, 5)]
    assert any(c.name == "其他路径" for c in result["clusters"])


async def test_future_self_prompt_includes_profile():
    from app.services.future_self import chat_with_future_self

    class Recording(MockLLMProvider):
        def __init__(self):
            super().__init__(scripted=["还记得，当初最担心的事确实发生了。"])
            self.seen_user = None

        async def complete(self, system_prompt, user_prompt, *, temperature=0.8, max_tokens=4096):
            self.seen_user = user_prompt
            return await super().complete(
                system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens
            )

    llm_module.set_provider(Recording())
    trajectory = {
        "id": "a_u01", "summary": "两年稳步上升", "years": [
            {"year": 1, "location": "上海", "major_event": "进入新项目", "career": "职责扩大",
             "finance": "储蓄增加", "relationship": "稳定", "wellbeing": "良好", "decision": "主动争取"},
        ],
    }
    universe = {"macro_environment": "行业平稳", "career_shock": "无", "financial_shock": "无",
                "relationship_shock": "无", "opportunity": "无", "random_event": "无"}
    reply = await chat_with_future_self(
        future_year=2027, profile="30岁，运营专员，纠结要不要换城市。",
        choice_label="A", choice_text="留在现在的城市", trajectory=trajectory, universe=universe,
        message="你后悔吗？", history=[],
    )
    assert reply
    provider = llm_module.get_provider()
    assert "运营专员" in provider.seen_user
    assert "换城市" in provider.seen_user
