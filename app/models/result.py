"""运行结果数据结构（聚类、A/B 汇总、配对比较、洞察报告、完整 Run）。"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.request import SimulationRequest
from app.models.trajectory import Trajectory, Universe

DISCLAIMER = (
    "本页所有数字是「在当前模型、提示词与采样策略下，这种结果在模拟轨迹中出现的频率」，"
    "不是现实概率，也不是对未来的预测。分数只是模型内部比较指标，不是客观测量。"
)

METRIC_LABELS = {
    "career": "职业发展",
    "finance": "财务状况",
    "relationship": "亲密关系",
    "wellbeing": "生活满意度",
    "regret": "后悔程度（越低越好）",
}


class Cluster(BaseModel):
    name: str
    description: str = ""
    trajectory_ids: List[str] = Field(default_factory=list)
    common_pattern: str = ""
    key_risk: str = ""
    key_opportunity: str = ""
    representative_trajectory_id: Optional[str] = None

    @field_validator("name", "description", "common_pattern", "key_risk", "key_opportunity")
    @classmethod
    def clean(cls, v) -> str:
        return (v or "").strip()[:300]


class ChoiceSummary(BaseModel):
    """单个选择（A 或 B）的汇总。均值只是模型内部相对比较指标。"""

    choice_text: str
    num_lives: int = 0
    avg_career_score: float = 0.0
    avg_finance_score: float = 0.0
    avg_relationship_score: float = 0.0
    avg_wellbeing_score: float = 0.0
    avg_regret_score: float = 0.0
    overall_score: float = 0.0
    common_risks: List[str] = Field(default_factory=list)
    common_opportunities: List[str] = Field(default_factory=list)
    most_typical_trajectory_id: Optional[str] = None
    most_surprising_trajectory_id: Optional[str] = None
    clusters: List[Cluster] = Field(default_factory=list)


class MatchedMetric(BaseModel):
    """同一组共享宇宙中，某指标 A/B 各自更优的世界数。"""

    label: str
    a_better: int = 0
    b_better: int = 0
    close: int = 0


class MatchedExample(BaseModel):
    universe_id: int
    macro_environment: str = ""
    title: str = ""
    narrative: str = ""


class MatchedComparison(BaseModel):
    """Matched Pair Comparison：在共享外部条件下直接对比 A_i 与 B_i。"""

    universe_count: int = 0
    metrics: Dict[str, MatchedMetric] = Field(default_factory=dict)
    examples: List[MatchedExample] = Field(default_factory=list)
    divergence_insight: str = ""


class InsightReport(BaseModel):
    """最终洞察报告：不简单推荐 A 或 B，而是回答结构性问题。"""

    structural_difference: str = ""
    deciding_factors: str = ""
    unimportant_factors: str = ""
    who_fits_a: str = ""
    who_fits_b: str = ""
    biggest_risk: str = ""
    info_to_confirm: str = ""


class RunStats(BaseModel):
    llm_calls: int = 0
    regenerations: int = 0
    duration_seconds: float = 0.0
    failed_trajectories: int = 0


class RunResult(BaseModel):
    """一次完整模拟的全部产物，保存为 JSON 与单文件 HTML 报告。"""

    run_id: str
    created_at: str
    start_year: int
    request: SimulationRequest
    universes: List[Universe] = Field(default_factory=list)
    trajectories: List[Trajectory] = Field(default_factory=list)
    choice_summaries: Dict[str, ChoiceSummary] = Field(default_factory=dict)
    matched_comparison: MatchedComparison = Field(default_factory=MatchedComparison)
    insight: InsightReport = Field(default_factory=InsightReport)
    stats: RunStats = Field(default_factory=RunStats)
    disclaimer: str = DISCLAIMER
