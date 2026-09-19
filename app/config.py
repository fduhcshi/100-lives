"""全局配置。

所有敏感配置（网关地址、API Key、模型名）只从环境变量 / 本地 .env 读取，
代码中不硬编码任何真实值；缺少配置时给出明确提示。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# 本地 .env（已被 .gitignore 排除）优先级低于真实环境变量
load_dotenv(BASE_DIR / ".env")


def _env_first(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return default


def _env_int(*names: str, default: int) -> int:
    raw = _env_first(*names)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(*names: str, default: bool = False) -> bool:
    raw = _env_first(*names)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


class Settings:
    """运行配置。llm_* 只做中性命名，来源由环境决定。"""

    def __init__(self) -> None:
        # LLM 网关：优先 LLM_*，回退到本机已设置的 ANTHROPIC_*（同为
        # Anthropic Messages 兼容接口时可直接复用，不需要额外配置）。
        self.llm_base_url: str | None = _env_first("LLM_BASE_URL", "ANTHROPIC_BASE_URL")
        self.llm_api_key: str | None = _env_first("LLM_API_KEY", "ANTHROPIC_API_KEY")
        self.llm_model: str | None = _env_first("LLM_MODEL", "ANTHROPIC_MODEL")
        self.llm_mock: bool = _env_bool("LLM_MOCK")

        self.max_concurrency: int = _env_int("MAX_CONCURRENCY", default=20)
        self.host: str = _env_first("HOST", default="127.0.0.1")
        self.port: int = _env_int("PORT", default=8000)
        self.log_level: str = _env_first("LOG_LEVEL", default="INFO")

        self.app_dir = BASE_DIR
        self.static_dir = BASE_DIR / "static"
        self.data_dir = BASE_DIR / "data"
        self.runs_dir = self.data_dir / "runs"

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @property
    def api_endpoint(self) -> str | None:
        """Anthropic Messages 兼容端点。

        兼容三种写法：BASE / BASE/v1 / BASE/v1/messages。
        """
        if not self.llm_base_url:
            return None
        base = self.llm_base_url.rstrip("/")
        if base.endswith("/v1/messages"):
            return base
        if base.endswith("/v1"):
            return f"{base}/messages"
        return f"{base}/v1/messages"

    def ensure_dirs(self) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
