"""日志。

只输出必要信息：日志中绝不打印 API Key、完整请求头或环境变量。
"""
from __future__ import annotations

import logging

from app.config import settings

_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_root_logger: logging.Logger | None = None


def get_logger(name: str) -> logging.Logger:
    global _root_logger
    if _root_logger is None:
        _root_logger = logging.getLogger("hundred_lives")
        _root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FMT, datefmt="%H:%M:%S"))
        _root_logger.addHandler(handler)
        _root_logger.propagate = False
    return _root_logger.getChild(name)
