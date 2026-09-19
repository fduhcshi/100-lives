"""A/B 汇总：均值统计、Matched Pair Comparison、配对叙述与最终洞察报告。"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.models.result import (
    ChoiceSummary,
    Cluster,
    InsightReport,
    MatchedComparison,
    MatchedExample,
    MatchedMetric,
    METRIC_LABELS,
)
from app.models.trajectory import Trajectory, Universe
from app.prompts.summary import (
    INSIGHT_SYSTEM_V1,
    MATCHED_NARRATIVE_SYSTEM_V1,
    build_insight_user,
    build_matched_user,
)
from app.services.llm import LLMError, call_llm_json
from app.utils.json_parser import to_float
from app.utils.logger import get_logger

logger = get_logger("summary")

_CLOSE_THRESHOLD = 3.0  # |Δ| 不超过 3 分视为"相近"

# regret 是"越低越好"，其余四个指标"越高越好"
_METRIC_KEYS = ("career", "finance", "relationship", "wellbeing", "regret")
_LOWER_IS_BETTER = {"regret"}


def build_choice_summary(
    choice_text: str, trajectories: List[Trajectory], clustering: dict
) -> ChoiceSummary:
    n = len(trajectories)

    def avg(attr: str) -> float:
        values = [getattr(t, attr) for t in trajectories if getattr(t, attr) is not None]
        return round(sum(values) / len(values), 1) if values else 0.0

    career = avg("final_career_score")
    finance = avg("final_finance_score")
    relationship = avg("final_relationship_score")
    wellbeing = avg("final_wellbeing_score")
    regret = avg("regret_score")
    # 五项等权：后悔是负向指标，因此先转换成“低后悔得分”。
    overall = round((career + finance + relationship + wellbeing + (100 - regret)) / 5, 1) if n else 0.0

    return ChoiceSummary(
        choice_text=choice_text,
        num_lives=n,
        avg_career_score=career,
        avg_finance_score=finance,
        avg_relationship_score=relationship,
        avg_wellbeing_score=wellbeing,
        avg_regret_score=regret,
        overall_score=overall,
        common_risks=clustering.get("common_risks", []),
        common_opportunities=clustering.get("common_opportunities", []),
        most_typical_trajectory_id=clustering.get("most_typical_trajectory_id"),
        most_surprising_trajectory_id=clustering.get("most_surprising_trajectory_id"),
        clusters=clustering.get("clusters", []),
    )


def _metric_delta(metric: str, a: Trajectory, b: Trajectory) -> Optional[float]:
    attr_map = {
        "career": "final_career_score", "finance": "final_finance_score",
        "relationship": "final_relationship_score", "wellbeing": "final_wellbeing_score",
        "regret": "regret_score",
    }
    va = getattr(a, attr_map[metric])
    vb = getattr(b, attr_map[metric])
    if va is None or vb is None:
        return None
    delta = va - vb  # >0 表示 A 更高
    return -delta if metric in _LOWER_IS_BETTER else delta  # 统一成 >0 表示 A 更好


def compute_matched_metrics(
    universes: List[Universe], trajs_a: List[Trajectory], trajs_b: List[Trajectory]
) -> Tuple[Dict[str, MatchedMetric], List[dict]]:
    """纯 Python 计算：每个共享宇宙的 Δ_i = Score(A_i) - Score(B_i)。

    返回 (各指标计数, 配对明细)。明细按最大分歧排序，供叙述生成使用。
    """
    by_universe_a = {t.universe_id: t for t in trajs_a}
    by_universe_b = {t.universe_id: t for t in trajs_b}
    universe_by_id = {u.id: u for u in universes}
    pair_ids = sorted(set(by_universe_a) & set(by_universe_b))

    metrics: Dict[str, MatchedMetric] = {}
    pairs: List[dict] = []
    for uid in pair_ids:
        a, b = by_universe_a[uid], by_universe_b[uid]
        deltas = {}
        for metric in _METRIC_KEYS:
            delta = _metric_delta(metric, a, b)
            if delta is None:
                continue
            deltas[metric] = delta
            counter = metrics.setdefault(metric, MatchedMetric(label=METRIC_LABELS[metric]))
            if delta > _CLOSE_THRESHOLD:
                counter.a_better += 1
            elif delta < -_CLOSE_THRESHOLD:
                counter.b_better += 1
            else:
                counter.close += 1
        if deltas:
            pairs.append({
                "universe_id": uid,
                "universe": universe_by_id.get(uid),
                "a": a,
                "b": b,
                "deltas": deltas,
                "max_abs_delta": max(abs(d) for d in deltas.values()),
            })

    pairs.sort(key=lambda p: p["max_abs_delta"], reverse=True)
    return metrics, pairs


def _fallback_examples(pairs: List[dict], limit: int = 3) -> List[MatchedExample]:
    examples = []
    for pair in pairs[:limit]:
        uni = pair["universe"]
        examples.append(MatchedExample(
            universe_id=pair["universe_id"],
            macro_environment=uni.macro_environment if uni else "",
            title="外部条件相同，走向不同",
            narrative=f"选择 A 的你：{pair['a'].summary} 选择 B 的你：{pair['b'].summary}",
        ))
    return examples


async def narrate_matched_pairs(
    profile: str, choice_a: str, choice_b: str, pairs: List[dict]
) -> Tuple[List[MatchedExample], str]:
    """让 LLM 为分歧最大的几个宇宙写对比叙述；失败时退回模板叙述。"""
    if not pairs:
        return [], ""

    def _pair_text(pair: dict) -> str:
        uni = pair["universe"]
        macro = uni.macro_environment if uni else "（未知）"
        deltas = "，".join(
            f"{METRIC_LABELS[m]}差 {d:+.0f} 分（正值=A 更好）" for m, d in pair["deltas"].items()
        )
        return (
            f"宇宙 #{pair['universe_id']}｜外部环境：{macro}\n"
            f"- 选择 A 的轨迹：{pair['a'].summary}\n"
            f"- 选择 B 的轨迹：{pair['b'].summary}\n"
            f"- 差异：{deltas}"
        )

    top = pairs[:6]
    user_prompt = build_matched_user(
        profile, choice_a, choice_b,
        "\n\n".join(_pair_text(p) for p in top), n=len(pairs),
    )
    try:
        data = await call_llm_json(
            MATCHED_NARRATIVE_SYSTEM_V1, user_prompt, temperature=0.5, max_tokens=3000
        )
        if not isinstance(data, dict):
            data = {}
        known = {p["universe_id"] for p in top}
        examples = []
        for raw in data.get("examples", []) or []:
            if not isinstance(raw, dict):
                continue
            uid = int(to_float(raw.get("universe_id"), default=-1) or -1)
            if uid not in known:
                continue
            pair = next(p for p in top if p["universe_id"] == uid)
            uni = pair["universe"]
            examples.append(MatchedExample(
                universe_id=uid,
                macro_environment=uni.macro_environment if uni else "",
                title=str(raw.get("title") or "")[:100],
                narrative=str(raw.get("narrative") or "")[:500],
            ))
        insight = str(data.get("divergence_insight") or "")[:400]
        if examples and insight:
            return examples, insight
        logger.warning("配对叙述结果不完整，使用模板叙述兜底")
    except LLMError as exc:
        logger.warning("配对叙述生成失败，使用模板叙述兜底: %s", exc)

    fallback = _fallback_examples(pairs)
    insight = "在分歧最大的几个共享世界里，决定差异的往往不是第一年的起点，而是第二到第三年对机会与冲击的响应方式。"
    return fallback, insight


async def generate_insight(
    profile: str,
    choice_a: str,
    choice_b: str,
    n: int,
    summary_a: ChoiceSummary,
    summary_b: ChoiceSummary,
    matched: MatchedComparison,
) -> InsightReport:
    def _summary_text(label: str, s: ChoiceSummary) -> str:
        lines = [
            f"选择 {label}（{s.choice_text}）：{s.num_lives} 条轨迹，"
            f"均值 职业{s.avg_career_score}/财务{s.avg_finance_score}/关系{s.avg_relationship_score}"
            f"/满意度{s.avg_wellbeing_score}/后悔{s.avg_regret_score}",
        ]
        for c in s.clusters:
            lines.append(
                f"- {c.name}（{len(c.trajectory_ids)} 个世界）：{c.description} 风险：{c.key_risk} 机会：{c.key_opportunity}"
            )
        return "\n".join(lines)

    def _matched_text() -> str:
        lines = [f"共 {matched.universe_count} 个共享宇宙（每个宇宙同时模拟了 A 与 B）："]
        for key, m in matched.metrics.items():
            lines.append(f"- {m.label}：A 更好 {m.a_better} 个世界，B 更好 {m.b_better} 个世界，相近 {m.close} 个世界")
        return "\n".join(lines)

    user_prompt = build_insight_user(
        profile, choice_a, choice_b, n,
        _summary_text("A", summary_a), _summary_text("B", summary_b), _matched_text(),
    )
    try:
        data = await call_llm_json(INSIGHT_SYSTEM_V1, user_prompt, temperature=0.4, max_tokens=3000)
        if not isinstance(data, dict):
            data = {}
        report = InsightReport(
            structural_difference=str(data.get("structural_difference") or "")[:800],
            deciding_factors=str(data.get("deciding_factors") or "")[:800],
            unimportant_factors=str(data.get("unimportant_factors") or "")[:800],
            who_fits_a=str(data.get("who_fits_a") or "")[:800],
            who_fits_b=str(data.get("who_fits_b") or "")[:800],
            biggest_risk=str(data.get("biggest_risk") or "")[:800],
            info_to_confirm=str(data.get("info_to_confirm") or "")[:800],
        )
        if report.structural_difference:
            return report
        logger.warning("洞察报告为空，使用兜底文案")
    except LLMError as exc:
        logger.warning("洞察报告生成失败，使用兜底文案: %s", exc)

    return InsightReport(
        structural_difference=f"在 {n} 个共享世界的模拟中，两个选择呈现出不同的结构性模式（本次洞察生成失败，详见上方聚类与配对数据）。",
        deciding_factors="请参考『相同世界，不同选择』部分的最大分歧案例。",
        unimportant_factors="（本次未生成）",
        who_fits_a="请结合聚类路径自行判断。",
        who_fits_b="请结合聚类路径自行判断。",
        biggest_risk="请参考两侧的常见风险列表。",
        info_to_confirm="建议在决定前核实新环境的真实信息（团队、成长速度、退出成本）。",
    )
