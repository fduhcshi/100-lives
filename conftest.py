# -*- coding: utf-8 -*-
"""根 conftest：在任何 app 导入之前强制离线 Mock，保证测试不碰真实网关。"""
import os

os.environ["LLM_MOCK"] = "1"
