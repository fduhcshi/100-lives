"""Critic：轨迹质量检查。"""
from __future__ import annotations

import json

from app.models.trajectory import CriticResult, Trajectory, Universe
from app.prompts.critic import CRITIC_SYSTEM_V1, build_critic_user
from app.services.llm import call_llm_json
from app.utils.json_parser import to_bool, to_float


async def critique_trajectory(
    profile: str, choice_label: str, choice_text: str, universe: Universe, trajectory: Trajectory
) -> CriticResult:
    trajectory_payload = {
        "summary": trajectory.summary,
        "years": [y.model_dump() for y in trajectory.years],
        "final_scores": trajectory.scores(),
    }
    user_prompt = build_critic_user(
        profile,
        choice_label,
        choice_text,
        universe.brief(),
        json.dumps(trajectory_payload, ensure_ascii=False),
    )
    data = await call_llm_json(CRITIC_SYSTEM_V1, user_prompt, temperature=0.2, max_tokens=2000)
    if not isinstance(data, dict):
        data = {}
    return CriticResult(
        consistency=to_float(data.get("consistency"), default=0.0) or 0.0,
        realism=to_float(data.get("realism"), default=0.0) or 0.0,
        coherence=to_float(data.get("coherence"), default=0.0) or 0.0,
        diversity=to_float(data.get("diversity"), default=0.0) or 0.0,
        accepted=to_bool(data.get("accepted"), default=False),
        problems=data.get("problems") if isinstance(data.get("problems"), list) else [],
    )


def passes(critic: CriticResult) -> bool:
    """通过标准：Critic 接受，且 realism / consistency 不低于 60。"""
    return critic.accepted and critic.realism >= 60 and critic.consistency >= 60
