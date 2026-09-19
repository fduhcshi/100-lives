"""API 请求数据结构。"""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, field_validator


class SimulationRequest(BaseModel):
    """一次平行人生模拟请求。"""

    profile: str = Field(..., min_length=10, max_length=5000, description="用户当前情况自述")
    choice_a: str = Field(..., min_length=1, max_length=300, description="待比较的选择 A")
    choice_b: str = Field(..., min_length=1, max_length=300, description="待比较的选择 B")
    years: int = Field(5, ge=1, le=10, description="模拟未来年数")
    num_lives: int = Field(20, ge=2, le=100, description="每个选择模拟多少条人生（= 平行世界数）")

    @field_validator("profile", "choice_a", "choice_b")
    @classmethod
    def strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("不能为空")
        return v


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        return v.strip()


class FutureSelfChatRequest(BaseModel):
    """与某条模拟人生中的『未来的自己』聊天。"""

    run_id: str = Field(..., min_length=4, max_length=64)
    trajectory_id: str = Field(..., min_length=3, max_length=32)
    message: str = Field(..., min_length=1, max_length=2000, description="用户这一轮的问题")
    history: List[ChatMessage] = Field(default_factory=list, max_length=20, description="此前的对话轮次（客户端维护）")

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("不能为空")
        return v
