"""平行世界与人生轨迹数据结构。

所有字段都带宽容校验：LLM 输出经过 normalize 后才进入这些模型，
分数统一 clamp 到 0-100，方向枚举统一为 up/down/flat。
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.utils.json_parser import to_bool, to_float

DIRECTIONS = {"up", "down", "flat"}

_DIRECTION_ALIASES = {
    "up": "up", "上升": "up", "升": "up", "upward": "up", "提高": "up", "变好": "up", "增长": "up",
    "down": "down", "下降": "down", "降": "down", "downward": "down", "降低": "down", "变差": "down", "下滑": "down",
    "flat": "flat", "持平": "flat", "稳定": "flat", "不变": "flat", "stable": "flat", "平稳": "flat",
}


def clamp_score(value) -> Optional[float]:
    v = to_float(value)
    if v is None:
        return None
    return max(0.0, min(100.0, v))


def normalize_direction(value) -> str:
    if not isinstance(value, str):
        return "flat"
    return _DIRECTION_ALIASES.get(value.strip().lower(), _DIRECTION_ALIASES.get(value.strip(), "flat"))


def _clean_str(v) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        v = str(v)
    return v.strip()


class Universe(BaseModel):
    """一个平行宇宙的外部条件（两个选择共享同一个宇宙，保证 A/B 对比公平）。"""

    id: int
    macro_environment: str = ""
    career_shock: str = ""
    financial_shock: str = ""
    relationship_shock: str = ""
    opportunity: str = ""
    random_event: str = ""

    @field_validator("macro_environment", "career_shock", "financial_shock",
                     "relationship_shock", "opportunity", "random_event")
    @classmethod
    def clean(cls, v) -> str:
        return _clean_str(v)[:200]

    def brief(self) -> str:
        parts = [f"宏观环境：{self.macro_environment}", f"职业冲击：{self.career_shock}",
                 f"财务冲击：{self.financial_shock}", f"关系冲击：{self.relationship_shock}",
                 f"机会：{self.opportunity}", f"随机事件：{self.random_event}"]
        return "；".join(p for p in parts if p.split("：", 1)[-1])


class YearState(BaseModel):
    """某一年的状态快照。year 为相对年数（1 表示第一年）。"""

    year: int
    career: str = ""
    finance: str = ""
    relationship: str = ""
    location: str = ""
    wellbeing: str = ""
    major_event: str = ""
    decision: str = ""

    @field_validator("career", "finance", "relationship", "location", "wellbeing",
                     "major_event", "decision")
    @classmethod
    def clean(cls, v) -> str:
        return _clean_str(v)[:300]


class TrajectoryFeatures(BaseModel):
    """从轨迹中提取的结构化标签，供聚类与统计使用。"""

    career_direction: str = "flat"
    location_change: bool = False
    startup: bool = False
    job_switch: bool = False
    relationship_change: bool = False
    financial_direction: str = "flat"
    wellbeing_direction: str = "flat"
    main_theme: str = "unknown"

    @field_validator("career_direction", "financial_direction", "wellbeing_direction")
    @classmethod
    def dir_(cls, v) -> str:
        return normalize_direction(v)

    @field_validator("location_change", "startup", "job_switch", "relationship_change")
    @classmethod
    def bool_(cls, v) -> bool:
        return to_bool(v)

    @field_validator("main_theme")
    @classmethod
    def theme(cls, v) -> str:
        return _clean_str(v)[:60] or "unknown"

    def brief(self) -> str:
        arrow = {"up": "↑", "down": "↓", "flat": "→"}
        flags = []
        if self.location_change:
            flags.append("换城市")
        if self.job_switch:
            flags.append("换工作")
        if self.startup:
            flags.append("创业")
        if self.relationship_change:
            flags.append("关系变化")
        flag_text = "/".join(flags) if flags else "无重大变动"
        return (f"职业{arrow[self.career_direction]} 财务{arrow[self.financial_direction]} "
                f"关系{arrow['flat' if not self.relationship_change else 'up']} "
                f"心态{arrow[self.wellbeing_direction]}｜{flag_text}｜主题:{self.main_theme}")


class CriticResult(BaseModel):
    """Critic 对一条轨迹的质量检查结果。

    checked=False 表示 Critic 调用失败、本条未经过质量检查（数据保留）。
    """

    consistency: float = 0.0
    realism: float = 0.0
    coherence: float = 0.0
    diversity: float = 0.0
    accepted: bool = False
    checked: bool = True
    problems: List[str] = Field(default_factory=list)

    @field_validator("consistency", "realism", "coherence", "diversity")
    @classmethod
    def score_(cls, v) -> float:
        val = to_float(v, default=0.0) or 0.0
        return max(0.0, min(100.0, val))

    @field_validator("accepted", mode="before")
    @classmethod
    def accept_(cls, v):
        return to_bool(v)

    @field_validator("problems")
    @classmethod
    def problems_(cls, v) -> List[str]:
        if not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            text = _clean_str(item)
            if text:
                cleaned.append(text[:200])
        return cleaned[:8]


class Trajectory(BaseModel):
    """一条完整的人生轨迹。"""

    id: str
    universe_id: int
    choice: str  # "A" | "B"
    summary: str = ""
    years: List[YearState] = Field(default_factory=list)
    features: TrajectoryFeatures = Field(default_factory=TrajectoryFeatures)
    final_career_score: Optional[float] = None
    final_finance_score: Optional[float] = None
    final_relationship_score: Optional[float] = None
    final_wellbeing_score: Optional[float] = None
    regret_score: Optional[float] = None
    critic: Optional[CriticResult] = None
    regenerated: int = 0
    cluster_name: Optional[str] = None

    @field_validator("choice")
    @classmethod
    def choice_(cls, v) -> str:
        v = (v or "").strip().upper()
        return "A" if v.startswith("A") else "B"

    @field_validator("final_career_score", "final_finance_score", "final_relationship_score",
                     "final_wellbeing_score", "regret_score", mode="before")
    @classmethod
    def score_(cls, v):
        return clamp_score(v)

    @field_validator("summary")
    @classmethod
    def summary_(cls, v) -> str:
        return _clean_str(v)[:500]

    @property
    def complete(self) -> bool:
        return all([
            self.final_career_score is not None,
            self.final_finance_score is not None,
            self.final_relationship_score is not None,
            self.final_wellbeing_score is not None,
            self.regret_score is not None,
            bool(self.years),
            bool(self.summary),
        ])

    def scores(self) -> dict[str, float | None]:
        return {
            "career": self.final_career_score,
            "finance": self.final_finance_score,
            "relationship": self.final_relationship_score,
            "wellbeing": self.final_wellbeing_score,
            "regret": self.regret_score,
        }
