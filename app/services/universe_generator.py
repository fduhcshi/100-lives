"""平行宇宙生成。

N 较大时拆成多批生成（每批 10 个），每批带不同的整体基调，
保证宇宙之间真正拉开差距；批与批之间并发执行。
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from app.models.trajectory import Universe
from app.prompts.universe import UNIVERSE_SYSTEM_V1, build_universe_user
from app.services.llm import LLMError, call_llm_json
from app.utils.logger import get_logger

logger = get_logger("universes")

CHUNK_SIZE = 10

_LEANS = [
    "整体偏有利，但中间也有挫折",
    "整体偏严峻，但也有局部机会",
    "波动较大，好坏事件交替出现",
    "相对平稳，缺少大起大落",
    "好坏混合，与常见的想象都有些不同",
]

_FIELDS = ("macro_environment", "career_shock", "financial_shock",
           "relationship_shock", "opportunity", "random_event")


def _valid_universe_item(item: dict) -> bool:
    return isinstance(item, dict) and all(
        isinstance(item.get(f), str) and item[f].strip() for f in _FIELDS
    )


def _normalize_universes(data, start_id: int) -> List[Universe]:
    if isinstance(data, dict):
        items = data.get("universes", [])
    elif isinstance(data, list):
        items = data
    else:
        items = []
    universes: List[Universe] = []
    for item in items:
        if not _valid_universe_item(item):
            continue
        universes.append(Universe(id=start_id + len(universes), **{f: item[f] for f in _FIELDS}))
    return universes


async def _generate_chunk(
    profile: str, years: int, start_year: int, n: int, lean: str, semaphore: asyncio.Semaphore
) -> List[Universe]:
    user_prompt = build_universe_user(profile, years, n, start_year, lean)
    async with semaphore:
        data = await call_llm_json(UNIVERSE_SYSTEM_V1, user_prompt, temperature=1.0, max_tokens=6000)
    return _normalize_universes(data, start_id=0)


async def generate_universes(
    profile: str,
    years: int,
    n: int,
    start_year: int,
    semaphore: asyncio.Semaphore,
    on_progress: Optional[callable] = None,
) -> List[Universe]:
    """生成 n 个彼此差异明显的平行宇宙。不足时最多补两轮。"""
    chunks: list[tuple[int, int]] = []  # (count, lean_index)
    remaining = n
    lean_index = 0
    while remaining > 0:
        size = min(CHUNK_SIZE, remaining)
        chunks.append((size, lean_index))
        lean_index = (lean_index + 1) % len(_LEANS)
        remaining -= size

    collected: List[Universe] = []
    for round_no in range(3):
        need = n - len(collected)
        if need <= 0:
            break
        if round_no > 0:
            # 用枚举序而不是 i（i 是 CHUNK_SIZE 的倍数，i % 5 恒为 0），
            # 保证补充批次的整体基调也能轮换；每批大小按剩余数量递减。
            chunks = [
                (min(CHUNK_SIZE, need - i), idx % len(_LEANS))
                for idx, i in enumerate(range(0, need, CHUNK_SIZE))
            ]
            logger.info("宇宙数量不足（%d/%d），补充第 %d 轮", len(collected), n, round_no)

        async def run_chunk(size: int, lean_idx: int, index: int) -> List[Universe]:
            lean = _LEANS[lean_idx]
            try:
                return await _generate_chunk(profile, years, start_year, size, lean, semaphore)
            except LLMError as exc:
                logger.error("宇宙批次 %d 生成失败: %s", index, exc)
                return []

        results = await asyncio.gather(*[
            run_chunk(size, lean_idx, index) for index, (size, lean_idx) in enumerate(chunks)
        ])
        for batch in results:
            collected.extend(batch)
        if on_progress:
            on_progress(len(collected), n)

    collected = collected[:n]
    # 统一重排 ID
    for i, universe in enumerate(collected, start=1):
        universe.id = i
    if len(collected) < n:
        logger.warning("宇宙最终只有 %d/%d 个", len(collected), n)
    return collected
