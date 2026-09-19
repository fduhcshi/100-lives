"""轨迹聚类：把一个选择下的所有轨迹交给 LLM 归纳成典型人生路径。

聚类结果在 Python 侧做严格校验：ID 必须真实存在、每条轨迹恰好一类、
漏分的轨迹归入"其他路径"，保证前端拿到的分布一定完整。
"""
from __future__ import annotations

from typing import List

from app.models.result import Cluster
from app.models.trajectory import Trajectory
from app.prompts.cluster import CLUSTER_SYSTEM_V1, build_cluster_user
from app.services.llm import LLMError, call_llm_json
from app.utils.logger import get_logger

logger = get_logger("cluster")

_ARROW = {"up": "↑", "down": "↓", "flat": "→"}


def _trajectory_line(t: Trajectory) -> str:
    f = t.features
    flags = "/".join(name for name, on in (
        ("换城市", f.location_change), ("换工作", f.job_switch),
        ("创业", f.startup), ("关系变化", f.relationship_change),
    ) if on) or "无重大变动"
    features = (
        f"职业{_ARROW[f.career_direction]} 财务{_ARROW[f.financial_direction]} "
        f"心态{_ARROW[f.wellbeing_direction]}｜{flags}｜{f.main_theme}"
    )
    scores = (
        f"C{t.final_career_score:.0f} F{t.final_finance_score:.0f} "
        f"R{t.final_relationship_score:.0f} W{t.final_wellbeing_score:.0f} 后悔{t.regret_score:.0f}"
    )
    return f"{t.id}｜{features}｜{scores}｜{t.summary}"


def _clean_str_list(raw, limit: int = 6) -> List[str]:
    if not isinstance(raw, list):
        return []
    cleaned = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip()[:200])
        if len(cleaned) >= limit:
            break
    return cleaned


async def cluster_choice_async(
    choice_label: str, choice_text: str, trajectories: List[Trajectory]
) -> dict:
    if not trajectories:
        return {
            "clusters": [], "most_typical_trajectory_id": None,
            "most_surprising_trajectory_id": None,
            "common_risks": [], "common_opportunities": [],
        }

    known_ids = {t.id for t in trajectories}
    lines = [_trajectory_line(t) for t in trajectories]
    user_prompt = build_cluster_user(choice_label, choice_text, lines)

    try:
        data = await call_llm_json(CLUSTER_SYSTEM_V1, user_prompt, temperature=0.3, max_tokens=7000)
    except LLMError as exc:
        logger.error("选择 %s 聚类失败: %s", choice_label, exc)
        data = {}
    if not isinstance(data, dict):
        data = {}

    # -- 校验与修复 ------------------------------------------------------------
    assigned: set[str] = set()
    clusters: List[Cluster] = []
    for raw in data.get("clusters", []) or []:
        if not isinstance(raw, dict):
            continue
        ids: List[str] = []
        for tid in raw.get("trajectory_ids", []) or []:
            if isinstance(tid, str) and tid in known_ids and tid not in assigned:
                ids.append(tid)
                assigned.add(tid)
        if not ids:
            continue
        representative = raw.get("representative_trajectory_id")
        if representative not in ids:
            representative = ids[0]
        clusters.append(Cluster(
            name=str(raw.get("name") or "未命名路径")[:60],
            description=str(raw.get("description") or "")[:300],
            trajectory_ids=ids,
            common_pattern=str(raw.get("common_pattern") or "")[:300],
            key_risk=str(raw.get("key_risk") or "")[:300],
            key_opportunity=str(raw.get("key_opportunity") or "")[:300],
            representative_trajectory_id=representative,
        ))

    unassigned = [t.id for t in trajectories if t.id not in assigned]
    if unassigned:
        clusters.append(Cluster(
            name="其他路径",
            description="未能归入主要类别的轨迹。",
            trajectory_ids=unassigned,
            common_pattern="模式较为分散。",
            key_risk="样本少，风险不明确。",
            key_opportunity="包含一些非典型走向。",
            representative_trajectory_id=unassigned[0],
        ))

    def _valid_id(value) -> str | None:
        return value if isinstance(value, str) and value in known_ids else None

    return {
        "clusters": clusters,
        "most_typical_trajectory_id": _valid_id(data.get("most_typical_trajectory_id")),
        "most_surprising_trajectory_id": _valid_id(data.get("most_surprising_trajectory_id")),
        "common_risks": _clean_str_list(data.get("common_risks")),
        "common_opportunities": _clean_str_list(data.get("common_opportunities")),
    }
