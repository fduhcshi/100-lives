"""人生轨迹模拟：Generate → Critic → (带反馈) Regenerate。

每个宇宙独立生成一条轨迹；A / B 两个选择共享同一批宇宙。
单条轨迹最多生成 3 次（初次 + 2 次重生成），仍不合格则保留最后一版
并标记 accepted=False（宁可保留低质量数据，也不让配对宇宙缺腿）。
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, List, Optional, Tuple

from pydantic import ValidationError

from app.models.trajectory import (
    CriticResult,
    Trajectory,
    TrajectoryFeatures,
    Universe,
    YearState,
)
from app.prompts.simulation import SIMULATION_SYSTEM_V1, build_simulation_user
from app.services.critic import critique_trajectory, passes
from app.services.llm import LLMError, call_llm_json
from app.utils.json_parser import to_bool, to_float
from app.utils.logger import get_logger

logger = get_logger("simulator")

MAX_ATTEMPTS = 3  # 初次 + 最多 2 次重生成


class TrajectoryParseError(ValueError):
    """轨迹输出结构不完整。"""


def _parse_years(raw_years, expected: int) -> List[YearState]:
    if not isinstance(raw_years, list) or not raw_years:
        raise TrajectoryParseError("years 为空或不是数组")
    if len(raw_years) < expected:
        raise TrajectoryParseError(f"years 只有 {len(raw_years)} 项，应为 {expected} 项")
    raw_years = raw_years[:expected]
    states: List[YearState] = []
    for index, item in enumerate(raw_years, start=1):
        if not isinstance(item, dict):
            item = {}
        states.append(YearState(year=index, **{
            k: item.get(k, "") for k in
            ("career", "finance", "relationship", "location", "wellbeing", "major_event", "decision")
        }))
    return states


def _parse_scores(data: dict) -> dict:
    raw = data.get("final_scores") if isinstance(data.get("final_scores"), dict) else data
    scores = {
        "final_career_score": to_float(raw.get("career", raw.get("final_career_score"))),
        "final_finance_score": to_float(raw.get("finance", raw.get("final_finance_score"))),
        "final_relationship_score": to_float(raw.get("relationship", raw.get("final_relationship_score"))),
        "final_wellbeing_score": to_float(raw.get("wellbeing", raw.get("final_wellbeing_score"))),
        "regret_score": to_float(raw.get("regret", raw.get("regret_score"))),
    }
    if any(v is None for v in scores.values()):
        missing = [k for k, v in scores.items() if v is None]
        raise TrajectoryParseError(f"评分缺失: {missing}")
    return scores


def parse_trajectory_payload(data, universe_id: int, choice_label: str, years_expected: int) -> Trajectory:
    """把 LLM 输出解析成 Trajectory；结构/类型问题统一抛 TrajectoryParseError，
    这样生成循环可以把问题描述反馈给模型重试，而不是直接报废这个宇宙。"""
    try:
        return _parse_trajectory_payload(data, universe_id, choice_label, years_expected)
    except ValidationError as exc:
        fields = "; ".join(
            "{}: {}".format(".".join(str(p) for p in e.get("loc", ())), e.get("msg", ""))
            for e in exc.errors()[:3]
        )
        raise TrajectoryParseError(f"字段类型或格式不合法（{fields}）") from exc


def _parse_trajectory_payload(data, universe_id: int, choice_label: str, years_expected: int) -> Trajectory:
    if not isinstance(data, dict):
        raise TrajectoryParseError("输出不是 JSON 对象")
    summary = (data.get("summary") or "").strip() if isinstance(data.get("summary"), str) else ""
    if not summary:
        raise TrajectoryParseError("summary 缺失")
    year_states = _parse_years(data.get("years"), years_expected)
    raw_features = data.get("features") if isinstance(data.get("features"), dict) else {}
    features = TrajectoryFeatures(
        career_direction=raw_features.get("career_direction", "flat"),
        location_change=to_bool(raw_features.get("location_change")),
        startup=to_bool(raw_features.get("startup")),
        job_switch=to_bool(raw_features.get("job_switch")),
        relationship_change=to_bool(raw_features.get("relationship_change")),
        financial_direction=raw_features.get("financial_direction", "flat"),
        wellbeing_direction=raw_features.get("wellbeing_direction", "flat"),
        main_theme=raw_features.get("main_theme", "unknown"),
    )
    trajectory_id = f"{choice_label.lower()}_u{universe_id:02d}"
    return Trajectory(
        id=trajectory_id,
        universe_id=universe_id,
        choice=choice_label,
        summary=summary,
        years=year_states,
        features=features,
        **_parse_scores(data),
    )


async def _soft_critic(
    profile: str, choice_label: str, choice_text: str, universe: Universe, trajectory: Trajectory
) -> CriticResult:
    """Critic 调用本身失败时不让整条轨迹报废（保留数据，标记跳过检查）。"""
    try:
        return await critique_trajectory(profile, choice_label, choice_text, universe, trajectory)
    except LLMError as exc:
        logger.warning("轨迹 %s 的 Critic 调用失败，跳过检查: %s", trajectory.id, exc)
        return CriticResult(
            consistency=60, realism=60, coherence=60, diversity=60, accepted=True, checked=False,
            problems=["（Critic 调用失败，本条未经过质量检查）"],
        )


async def _simulate_one(
    profile: str,
    choice_label: str,
    choice_text: str,
    universe: Universe,
    years: int,
    start_year: int,
    semaphore: asyncio.Semaphore,
) -> Tuple[Optional[Trajectory], int]:
    """模拟单个宇宙的一条轨迹。返回 (轨迹或 None, 重生成次数)。"""
    feedback = ""
    last_trajectory: Optional[Trajectory] = None
    attempts_used = 0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts_used = attempt
        user_prompt = build_simulation_user(
            profile, choice_label, choice_text, universe.model_dump(), years, start_year, feedback
        )
        try:
            # 生成与 Critic 都在信号量内：MAX_CONCURRENCY 对两者统一生效
            async with semaphore:
                data = await call_llm_json(
                    SIMULATION_SYSTEM_V1, user_prompt, temperature=0.9,
                    max_tokens=6000 + years * 400,
                )
                trajectory = parse_trajectory_payload(data, universe.id, choice_label, years)
                critic = await _soft_critic(profile, choice_label, choice_text, universe, trajectory)
        except (TrajectoryParseError, LLMError) as exc:
            reason = exc if isinstance(exc, TrajectoryParseError) else f"生成调用失败: {exc}"
            logger.warning("轨迹 %s 第 %d 次生成失败: %s", f"{choice_label}_u{universe.id}", attempt, reason)
            feedback = f"上一版输出无法解析（{reason}）。请严格按照要求的 JSON 结构重新输出。"
            # 不清除 last_trajectory：宁可保留前面已解析的版本，也不让配对宇宙缺腿
            continue

        last_trajectory = trajectory
        trajectory.critic = critic
        if passes(critic):
            trajectory.regenerated = attempt - 1
            return trajectory, attempt - 1
        feedback = "；".join(critic.problems) if critic.problems else "整体质量不达标，请让年份之间更有因果衔接、更贴近普通人生活。"
        logger.info("轨迹 %s 未通过检查（第 %d 次）: %s", trajectory.id, attempt, feedback[:80])

    # 全部尝试后仍不达标：保留最后一版（标记 accepted=False）
    if last_trajectory is not None:
        assert last_trajectory.critic is not None
        last_trajectory.regenerated = attempts_used - 1
        return last_trajectory, attempts_used - 1
    return None, attempts_used - 1


async def simulate_choice(
    profile: str,
    choice_label: str,
    choice_text: str,
    universes: List[Universe],
    years: int,
    start_year: int,
    semaphore: asyncio.Semaphore,
    on_progress: Optional[Callable[[int], Awaitable[None]] | Callable[[int], None]] = None,
) -> List[Trajectory]:
    """并发模拟一个选择下的所有宇宙。失败的宇宙被跳过（不会阻塞其他宇宙）。"""

    async def run_one(universe: Universe) -> Optional[Trajectory]:
        try:
            trajectory, _regen = await _simulate_one(
                profile, choice_label, choice_text, universe, years, start_year, semaphore
            )
            return trajectory
        except Exception as exc:  # 兜底：单宇宙失败不影响整体
            logger.error("宇宙 %d 的选择 %s 模拟异常: %s", universe.id, choice_label, exc)
            return None
        finally:
            if on_progress:
                result = on_progress(1)
                if asyncio.iscoroutine(result):
                    await result

    results = await asyncio.gather(*[run_one(u) for u in universes])
    trajectories = [t for t in results if t is not None]
    logger.info("选择 %s 完成：%d/%d 条轨迹", choice_label, len(trajectories), len(universes))
    return trajectories
