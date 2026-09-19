"""一次完整模拟的编排（流水线）。

流程：universes → 并发 simulate(A/B)（内含 critic 与重生成）→ cluster →
matched comparison → 洞察报告 → 保存。全程更新 run 状态供前端轮询。
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

from app.models.request import SimulationRequest
from app.models.result import (
    MatchedComparison,
    RunResult,
    RunStats,
)
from app.services import cluster as cluster_service
from app.services import summarizer as summarizer_service
from app.services.llm import begin_call_tracking, end_call_tracking
from app.services.runs import RunStore
from app.services.simulator import simulate_choice
from app.services.universe_generator import generate_universes
from app.utils.logger import get_logger

logger = get_logger("pipeline")


async def execute_run(run_id: str, request: SimulationRequest, store: RunStore, max_concurrency: int) -> None:
    started = time.monotonic()
    semaphore = asyncio.Semaphore(max_concurrency)
    stats = begin_call_tracking()
    try:
        await _execute(run_id, request, store, semaphore, stats, started)
    except Exception as exc:
        logger.exception("运行 %s 失败", run_id)
        store.update(
            run_id, stage="failed",
            message=f"模拟失败：{exc}",
            error=f"{exc.__class__.__name__}: {exc}"[:500],
        )
    finally:
        end_call_tracking()


async def _execute(
    run_id: str,
    request: SimulationRequest,
    store: RunStore,
    semaphore: asyncio.Semaphore,
    stats,
    started: float,
) -> None:
    profile = request.profile
    years = request.years
    n = request.num_lives
    start_year = datetime.now().year
    total_trajectories = 2 * n

    # ---- 阶段 1：平行世界 -----------------------------------------------------
    store.update(run_id, stage="universes", progress=0.02,
                 message=f"正在创建 {n} 个平行世界", detail={"universes_done": 0, "universes_total": n})

    def universe_progress(done: int, total: int) -> None:
        store.update(run_id, progress=0.02 + 0.13 * (done / max(total, 1)),
                     detail={"universes_done": done, "universes_total": total})

    universes = await generate_universes(
        profile, years, n, start_year, semaphore, on_progress=universe_progress
    )
    if not universes:
        raise RuntimeError("平行世界生成失败（0 个宇宙），请检查 LLM 配置或稍后重试")
    if len(universes) < n:
        # 宇宙不足时降级使用现有数量，保持 A/B 配对完整
        n = len(universes)
        total_trajectories = 2 * n
        store.update(run_id, message=f"平行世界生成了 {n} 个（少于预期），继续模拟")

    # ---- 阶段 2：并发模拟 A / B（内含 Critic 与重生成）------------------------
    store.update(run_id, stage="simulation", progress=0.15,
                 message="正在让不同世界中的你做出选择",
                 detail={"done_a": 0, "done_b": 0, "total": n, "checked": 0})

    done_counters = {"A": 0, "B": 0}

    def make_progress(choice: str):
        def progress(_: int) -> None:
            done_counters[choice] += 1
            done = done_counters["A"] + done_counters["B"]
            store.update(
                run_id,
                progress=0.15 + 0.55 * (done / total_trajectories),
                message="正在让不同世界中的你做出选择",
                detail={
                    "done_a": done_counters["A"], "done_b": done_counters["B"],
                    "total": n, "checked": done,
                },
            )
        return progress

    trajs_a, trajs_b = await asyncio.gather(
        simulate_choice(profile, "A", request.choice_a, universes, years, start_year,
                        semaphore, on_progress=make_progress("A")),
        simulate_choice(profile, "B", request.choice_b, universes, years, start_year,
                        semaphore, on_progress=make_progress("B")),
    )
    if not trajs_a or not trajs_b:
        raise RuntimeError(
            f"轨迹生成失败（A: {len(trajs_a)} 条，B: {len(trajs_b)} 条），请稍后重试"
        )

    # ---- 阶段 3：聚类 ---------------------------------------------------------
    store.update(run_id, stage="clustering", progress=0.72,
                 message="正在寻找最常见的人生路径", detail={})
    clustering_a, clustering_b = await asyncio.gather(
        cluster_service.cluster_choice_async("A", request.choice_a, trajs_a),
        cluster_service.cluster_choice_async("B", request.choice_b, trajs_b),
    )
    summary_a = summarizer_service.build_choice_summary(request.choice_a, trajs_a, clustering_a)
    summary_b = summarizer_service.build_choice_summary(request.choice_b, trajs_b, clustering_b)

    # 把聚类名回写到轨迹上（前端表格展示用）
    for label, trajectories, clustering in (("A", trajs_a, clustering_a), ("B", trajs_b, clustering_b)):
        name_by_id: dict[str, str] = {}
        for c in clustering["clusters"]:
            for tid in c.trajectory_ids:
                name_by_id[tid] = c.name
        for t in trajectories:
            t.cluster_name = name_by_id.get(t.id)

    # ---- 阶段 4：Matched Pair Comparison --------------------------------------
    store.update(run_id, stage="comparison", progress=0.82,
                 message="正在对比相同世界中的不同选择", detail={})
    metrics, pairs = summarizer_service.compute_matched_metrics(universes, trajs_a, trajs_b)
    examples, divergence_insight = await summarizer_service.narrate_matched_pairs(
        profile, request.choice_a, request.choice_b, pairs
    )
    matched = MatchedComparison(
        universe_count=len(pairs),
        metrics=metrics,
        examples=examples,
        divergence_insight=divergence_insight,
    )

    # ---- 阶段 5：最终洞察 ------------------------------------------------------
    store.update(run_id, stage="summary", progress=0.92,
                 message="正在生成你的平行人生报告", detail={})
    insight = await summarizer_service.generate_insight(
        profile, request.choice_a, request.choice_b, n, summary_a, summary_b, matched
    )

    # ---- 保存 -------------------------------------------------------------------
    expected = 2 * n
    failed = expected - len(trajs_a) - len(trajs_b)
    regenerations = sum(t.regenerated for t in trajs_a + trajs_b)

    result = RunResult(
        run_id=run_id,
        created_at=datetime.now().isoformat(timespec="seconds"),
        start_year=start_year,
        request=request,
        universes=universes,
        trajectories=sorted(trajs_a + trajs_b, key=lambda t: (t.choice, t.universe_id)),
        choice_summaries={"A": summary_a, "B": summary_b},
        matched_comparison=matched,
        insight=insight,
        stats=RunStats(
            llm_calls=stats.calls,
            regenerations=regenerations,
            duration_seconds=round(time.monotonic() - started, 1),
            failed_trajectories=max(0, failed),
        ),
    )
    store.save_result(result)
    store.update(run_id, stage="done", progress=1.0, message="模拟完成", detail={})
    logger.info("运行 %s 完成：%d 条轨迹，%d 次 LLM 调用，%.1fs",
                run_id, len(result.trajectories), stats.calls, result.stats.duration_seconds)
