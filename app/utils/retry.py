"""指数退避重试。"""
from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.utils.logger import get_logger

logger = get_logger("retry")

T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    label: str = "",
) -> T:
    """带指数退避 + 抖动的重试。最后一次失败时原样抛出。"""
    prefix = f"[{label}] " if label else ""
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except retry_on as exc:  # noqa: PERF203
            last_error = exc
            if attempt == attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, 0.5)
            logger.warning("%s第 %d/%d 次尝试失败：%s，%.1fs 后重试", prefix, attempt, attempts, exc, delay)
            await asyncio.sleep(delay)
    assert last_error is not None
    raise last_error
