"""FastAPI 入口。

路由：
- GET  /                     → 首页
- GET  /result/{run_id}      → 结果页
- POST /api/simulate         → 开始一次模拟（后台运行，立即返回 run_id）
- GET  /api/status/{run_id}  → 进度轮询
- GET  /api/result/{run_id}  → 完整结果 JSON
- POST /api/future-self-chat → 和某条人生里"未来的自己"聊天
- GET  /api/health           → 健康检查
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models.request import FutureSelfChatRequest, SimulationRequest
from app.services import llm as llm_module
from app.services import future_self as future_self_service
from app.services.pipeline import execute_run
from app.services.runs import RunStore
from app.utils.logger import get_logger

logger = get_logger("api")

store: RunStore | None = None
_background_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store
    settings.ensure_dirs()
    store = RunStore(settings.runs_dir, settings.static_dir)
    if llm_module.llm_configured():
        try:
            llm_module.get_provider()
        except Exception as exc:
            logger.warning("LLM Provider 初始化失败: %s", exc)
    else:
        logger.warning("LLM 未配置：/api/simulate 将返回 400（可设置 LLM_MOCK=1 走离线 Mock）")
    yield
    for task in list(_background_tasks):
        if not task.done():
            task.cancel()
    _background_tasks.clear()
    try:
        provider = llm_module.get_provider()
    except Exception:
        provider = None
    close = getattr(provider, "aclose", None)
    if close:
        await close()


app = FastAPI(title="100 Lives", version="0.1.0", lifespan=lifespan)

_STATIC = Path(settings.static_dir)
if _STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(_STATIC / "index.html", media_type="text/html")


@app.get("/result/{run_id}", include_in_schema=False)
async def result_page(run_id: str) -> FileResponse:
    return FileResponse(_STATIC / "result.html", media_type="text/html")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "llm_configured": llm_module.llm_configured()}


@app.get("/api/config")
async def web_config() -> dict:
    return {"mode": "local", "max_lives": 100, "default_lives": 20, "max_years": 10}


@app.post("/api/simulate")
async def simulate(request: SimulationRequest) -> JSONResponse:
    assert store is not None
    if not llm_module.llm_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "LLM 未配置：请在项目根目录的 .env 中设置 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL"
                "（或设置 LLM_MOCK=1 使用离线 Mock），然后重启服务。"
            ),
        )
    run_id = store.create(request)
    task = asyncio.create_task(_run_simulation(run_id, request))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return JSONResponse({"run_id": run_id}, status_code=202)


async def _run_simulation(run_id: str, request: SimulationRequest) -> None:
    await execute_run(run_id, request, store, settings.max_concurrency)


@app.get("/api/status/{run_id}")
async def status(run_id: str) -> dict:
    assert store is not None
    data = store.get_status(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="未找到该运行")
    return data


@app.get("/api/result/{run_id}")
async def result(run_id: str) -> dict:
    assert store is not None
    data = store.load_result(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="未找到该运行")
    return data


@app.get("/api/result/{run_id}/html")
async def download_result_html(run_id: str) -> FileResponse:
    assert store is not None
    path = store.get_html_path(run_id)
    if path is None:
        raise HTTPException(status_code=404, detail="未找到该 HTML 报告")
    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        filename=f"100-lives-{run_id}.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.post("/api/future-self-chat")
async def future_self_chat(body: FutureSelfChatRequest) -> dict:
    assert store is not None
    if not llm_module.llm_configured():
        raise HTTPException(
            status_code=503,
            detail="LLM 未配置，无法与未来的自己对话（可设置 LLM_MOCK=1 使用离线 Mock）。",
        )

    found = store.find_trajectory(body.run_id, body.trajectory_id)
    if found is None:
        raise HTTPException(status_code=404, detail="未找到该轨迹")
    result_data, trajectory = found["result"], found["trajectory"]

    request = result_data.get("request", {})
    years = int(request.get("years") or 5)
    start_year = int(result_data.get("start_year") or datetime.now().year)
    future_year = start_year + years - 1
    choice = trajectory.get("choice", "A")
    choice_text = request.get("choice_a") if choice == "A" else request.get("choice_b")

    universe = next(
        (u for u in result_data.get("universes", []) if u.get("id") == trajectory.get("universe_id")),
        None,
    )

    try:
        reply = await future_self_service.chat_with_future_self(
            future_year=future_year,
            profile=str(request.get("profile") or ""),
            choice_label=choice,
            choice_text=str(choice_text or ""),
            trajectory=trajectory,
            universe=universe,
            message=body.message,
            history=[m.model_dump() for m in body.history],
        )
    except llm_module.LLMError as exc:
        logger.warning("Future Self 对话失败: %s", exc)
        raise HTTPException(status_code=502, detail=f"模型调用失败：{exc}") from exc

    if not reply or not reply.strip():
        raise HTTPException(status_code=502, detail="模型返回了空回复，请重试一次")

    return {"reply": reply.strip(), "future_year": future_year}
