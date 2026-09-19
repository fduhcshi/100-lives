"""运行状态与结果存储（第一版用文件，不用数据库）。

- 内存 status dict 支撑 /api/status 轮询
- 结果同时保存为 data/runs/{run_id}.json 与可直接打开的单文件 HTML 报告
- 服务重启后：已完成的 run 仍可从磁盘读取（status 自动恢复为 done）
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.models.request import SimulationRequest
from app.models.result import RunResult
from app.services.html_report import render_standalone_report
from app.utils.logger import get_logger

logger = get_logger("runs")

_RUN_ID_RE = re.compile(r"^[0-9]{8}_[0-9]{6}_[0-9a-f]{6,8}$")


class RunStore:
    def __init__(self, runs_dir: Path, static_dir: Path | None = None) -> None:
        self.runs_dir = Path(runs_dir)
        self.static_dir = Path(static_dir) if static_dir else Path(__file__).resolve().parents[2] / "static"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._status: dict[str, dict[str, Any]] = {}

    # -- run 生命周期 ---------------------------------------------------------

    @staticmethod
    def new_run_id() -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{stamp}_{secrets.token_hex(3)}"

    @staticmethod
    def valid_run_id(run_id: str) -> bool:
        return bool(_RUN_ID_RE.match(run_id or ""))

    def create(self, request: SimulationRequest) -> str:
        run_id = self.new_run_id()
        self._status[run_id] = {
            "run_id": run_id,
            "stage": "queued",
            "progress": 0.0,
            "message": "排队中…",
            "detail": {},
            "error": None,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        logger.info("新建运行 %s（%d 年 × 每选择 %d 条）", run_id, request.years, request.num_lives)
        return run_id

    def update(
        self,
        run_id: str,
        *,
        stage: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        detail: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        status = self._status.get(run_id)
        if status is None:
            return
        if stage is not None:
            status["stage"] = stage
        if progress is not None:
            status["progress"] = max(0.0, min(1.0, progress))
        if message is not None:
            status["message"] = message
        if detail is not None:
            status["detail"] = detail
        if error is not None:
            status["error"] = error
        status["updated_at"] = datetime.now().isoformat(timespec="seconds")

    # -- 查询 ------------------------------------------------------------------

    def get_status(self, run_id: str) -> Optional[dict[str, Any]]:
        if not self.valid_run_id(run_id):
            return None
        status = self._status.get(run_id)
        if status is not None:
            return dict(status)
        # 服务重启后：内存丢了，但磁盘上有完成结果
        if self._result_path(run_id).exists():
            return {
                "run_id": run_id,
                "stage": "done",
                "progress": 1.0,
                "message": "已完成",
                "detail": {},
                "error": None,
                "updated_at": None,
            }
        return None

    def load_result(self, run_id: str) -> Optional[dict[str, Any]]:
        if not self.valid_run_id(run_id):
            return None
        path = self._result_path(run_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("读取运行 %s 失败: %s", run_id, exc)
            return None

    def get_html_path(self, run_id: str) -> Optional[Path]:
        """使用当前前端资源重新生成 HTML，确保旧运行下载到最新报告样式。"""
        if not self.valid_run_id(run_id):
            return None
        payload = self.load_result(run_id)
        if payload is None:
            return None
        path = self._html_path(run_id)
        tmp_path = path.with_suffix(".html.tmp")
        try:
            tmp_path.write_text(
                render_standalone_report(payload, self.static_dir),
                encoding="utf-8",
            )
            os.replace(tmp_path, path)
        except (OSError, ValueError) as exc:
            logger.error("刷新运行 %s 的 HTML 报告失败: %s", run_id, exc)
            return None
        finally:
            tmp_path.unlink(missing_ok=True)
        return path

    def find_trajectory(self, run_id: str, trajectory_id: str) -> Optional[dict[str, Any]]:
        """返回 (result, trajectory) 或 None；供未来自己聊天使用。"""
        result = self.load_result(run_id)
        if result is None:
            return None
        for trajectory in result.get("trajectories", []):
            if trajectory.get("id") == trajectory_id:
                return {"result": result, "trajectory": trajectory}
        return None

    # -- 持久化 -----------------------------------------------------------------

    def _result_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def _html_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.html"

    def save_result(self, result: RunResult) -> Path:
        path = self._result_path(result.run_id)
        html_path = self._html_path(result.run_id)
        payload = result.model_dump()
        # 先写临时文件再原子替换：避免写入中途崩溃/磁盘满留下半截 JSON，
        # 否则 get_status 会因文件存在而报 done，load_result 却解析失败。
        tmp_path = path.with_suffix(".json.tmp")
        html_tmp_path = html_path.with_suffix(".html.tmp")
        try:
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            html_tmp_path.write_text(
                render_standalone_report(payload, self.static_dir),
                encoding="utf-8",
            )
            os.replace(tmp_path, path)
            os.replace(html_tmp_path, html_path)
        finally:
            tmp_path.unlink(missing_ok=True)
            html_tmp_path.unlink(missing_ok=True)
        logger.info("运行 %s 已保存到 %s 和 %s", result.run_id, path.name, html_path.name)
        return path
