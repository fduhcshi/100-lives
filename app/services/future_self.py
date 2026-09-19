"""Future Self：与某条模拟人生中『未来的自己』聊天。"""
from __future__ import annotations

from typing import List

from app.prompts.future_self import FUTURE_SELF_SYSTEM_V1, build_future_self_user
from app.services.llm import call_llm
from app.utils.logger import get_logger

logger = get_logger("future_self")


def _trajectory_text(trajectory: dict) -> str:
    lines = [f"概述：{trajectory.get('summary', '')}"]
    for year in trajectory.get("years", []):
        lines.append(
            f"第 {year.get('year')} 年｜{year.get('location', '')}｜"
            f"重大事件：{year.get('major_event', '')}｜"
            f"职业：{year.get('career', '')}｜财务：{year.get('finance', '')}｜"
            f"关系：{year.get('relationship', '')}｜身心：{year.get('wellbeing', '')}｜"
            f"当年的决定：{year.get('decision', '')}"
        )
    return "\n".join(lines)


def _universe_text(universe: dict | None) -> str:
    if not universe:
        return "（未知）"
    return (
        f"宏观环境：{universe.get('macro_environment', '')}；"
        f"职业冲击：{universe.get('career_shock', '')}；"
        f"财务冲击：{universe.get('financial_shock', '')}；"
        f"关系冲击：{universe.get('relationship_shock', '')}；"
        f"机会：{universe.get('opportunity', '')}；"
        f"随机事件：{universe.get('random_event', '')}"
    )


def _history_text(history: List[dict]) -> str:
    if not history:
        return ""
    role_name = {"user": "用户", "assistant": "未来的我"}
    return "\n".join(
        f"{role_name.get(m.get('role'), '用户')}：{m.get('content', '')}" for m in history
    )


async def chat_with_future_self(
    *,
    future_year: int,
    profile: str,
    choice_label: str,
    choice_text: str,
    trajectory: dict,
    universe: dict | None,
    message: str,
    history: List[dict],
) -> str:
    system_prompt = FUTURE_SELF_SYSTEM_V1.replace("{future_year}", str(future_year))
    user_prompt = build_future_self_user(
        profile=profile,
        choice_label=choice_label,
        choice_text=choice_text,
        trajectory_text=_trajectory_text(trajectory),
        universe_text=_universe_text(universe),
        history_text=_history_text(history),
        question=message,
    )
    logger.info("Future Self 对话（%s，%d 轮历史）", trajectory.get("id"), len(history))
    return await call_llm(system_prompt, user_prompt, temperature=0.8, max_tokens=2000)
