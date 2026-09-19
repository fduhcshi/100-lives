# -*- coding: utf-8 -*-
"""测试夹具。"""
from __future__ import annotations

import pytest

from app.services import llm as llm_module


@pytest.fixture(autouse=True)
def reset_provider():
    """每个测试之间重置 provider 单例，避免 scripted 状态串场。"""
    llm_module.set_provider(None)
    yield
    llm_module.set_provider(None)
