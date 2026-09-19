# -*- coding: utf-8 -*-
"""LLM 层测试：JSON 解析、Provider 选择、Anthropic 兼容请求、重试与降级。"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.services import llm as llm_module
from app.services.llm import (
    AnthropicCompatProvider,
    LLMError,
    LLMNotConfiguredError,
    MockLLMProvider,
    call_llm,
    call_llm_json,
)
from app.utils.json_parser import JSONParseError, extract_json, to_bool, to_float

SYS = "[[task:test]] 你是测试助手。"
USER = "请输出 JSON。"


# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------

def test_extract_json_plain():
    assert extract_json('{"ok": true}') == {"ok": True}


def test_extract_json_fenced():
    text = "好的，以下是结果：\n```json\n{\"a\": 1}\n```\n以上。"
    assert extract_json(text) == {"a": 1}


def test_extract_json_prose_wrapped():
    text = "根据你的情况，我的分析如下：{\"career\": 72, \"note\": \"}括号在字符串里\"} 希望有帮助。"
    assert extract_json(text) == {"career": 72, "note": "}括号在字符串里"}


def test_extract_json_array():
    assert extract_json("前缀 [1, 2, 3] 后缀") == [1, 2, 3]


def test_extract_json_trailing_comma():
    assert extract_json('{"a": [1, 2, 3,], "b": {"c": 1,},}') == {"a": [1, 2, 3], "b": {"c": 1}}


def test_extract_json_nested_before_outer():
    # 有两个顶层片段时，取第一个合法的
    text = '说明 {"x": 1} 结尾再补一段 {"y": 2}'
    assert extract_json(text) == {"x": 1}


def test_extract_json_invalid_raises():
    with pytest.raises(JSONParseError):
        extract_json("这里完全没有 JSON")


def test_extract_json_unmatched_brace_in_prose():
    # 说明文字里有一个多余的 '{'：真正的 JSON 不是顶层片段，内层回退应能救回
    text = "好的，这是您要的数据结构 { 概述如下：\n{\"summary\": \"ok\", \"years\": [1, 2]}"
    assert extract_json(text) == {"summary": "ok", "years": [1, 2]}


def test_extract_json_inner_chunk_after_broken_outer():
    # 外层片段损坏（不闭合），内层对象仍可解析
    text = '前缀 {"broken": { 结尾 {"a": 1} 补个闭括号 } }'
    value = extract_json(text)
    assert isinstance(value, dict) and value.get("a") == 1


def test_extract_json_empty_raises():
    with pytest.raises(JSONParseError):
        extract_json("")


def test_to_float():
    assert to_float("72") == 72.0
    assert to_float("72.5分") == 72.5
    assert to_float(7) == 7.0
    assert to_float(None, default=5.0) == 5.0
    assert to_float("abc", default=1.5) == 1.5


def test_to_float_nan_inf_are_missing():
    # json.loads 允许裸 NaN/Infinity；它们不能变成 100 满分，应视为缺失
    import json as _json
    nan = _json.loads('{"x": NaN}')["x"]
    inf = _json.loads('{"x": Infinity}')["x"]
    assert to_float(nan) is None
    assert to_float(inf) is None
    assert to_float(nan, default=0.0) == 0.0


def test_to_bool():
    assert to_bool("true") is True
    assert to_bool("是") is True
    assert to_bool("false") is False
    assert to_bool(1) is True
    assert to_bool(None, default=True) is True


# ---------------------------------------------------------------------------
# Provider 选择与端点规范化
# ---------------------------------------------------------------------------

async def test_provider_not_configured(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "llm_mock", False)
    monkeypatch.setattr(settings, "llm_base_url", None)
    monkeypatch.setattr(settings, "llm_api_key", None)
    monkeypatch.setattr(settings, "llm_model", None)
    with pytest.raises(LLMNotConfiguredError):
        await call_llm(SYS, USER)


def test_endpoint_normalization():
    assert AnthropicCompatProvider._normalize_endpoint("http://gw.example/api") == "http://gw.example/api/v1/messages"
    assert AnthropicCompatProvider._normalize_endpoint("http://gw.example/api/") == "http://gw.example/api/v1/messages"
    assert AnthropicCompatProvider._normalize_endpoint("http://gw.example/api/v1") == "http://gw.example/api/v1/messages"
    assert AnthropicCompatProvider._normalize_endpoint("http://gw.example/api/v1/messages") == "http://gw.example/api/v1/messages"


# ---------------------------------------------------------------------------
# AnthropicCompatProvider（httpx MockTransport）
# ---------------------------------------------------------------------------

def _make_provider(handler) -> AnthropicCompatProvider:
    return AnthropicCompatProvider(
        "https://gw.example/api", "test-key", "test-model", transport=httpx.MockTransport(handler)
    )


def test_anthropic_provider_ok():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content.decode("utf-8"))
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": '{"ok": true}'}],
            "stop_reason": "end_turn",
        })

    provider = _make_provider(handler)
    text = asyncio.run(provider.complete("system-prompt", "user-prompt", temperature=0.5, max_tokens=123))
    assert text == '{"ok": true}'
    body = seen["json"]
    assert body["model"] == "test-model"
    assert body["max_tokens"] == 123
    assert body["temperature"] == 0.5
    assert body["system"] == "system-prompt"
    assert body["messages"] == [{"role": "user", "content": "user-prompt"}]
    # 鉴权头存在且不携带空值
    assert seen["headers"].get("x-api-key") == "test-key"
    assert "anthropic-version" in seen["headers"]


def test_anthropic_provider_empty_reply():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": []})

    provider = _make_provider(handler)
    with pytest.raises(LLMError, match="空回复"):
        asyncio.run(provider.complete("s", "u"))


def test_anthropic_provider_400_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad request for other reasons")

    provider = _make_provider(handler)
    with pytest.raises(LLMError, match="HTTP 400"):
        asyncio.run(provider.complete("s", "u"))


def test_anthropic_provider_temperature_fallback():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        calls.append(body)
        if "temperature" in body:
            return httpx.Response(400, text="temperature is not supported")
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    provider = _make_provider(handler)
    text = asyncio.run(provider.complete("s", "u", temperature=0.9))
    assert text == "ok"
    assert len(calls) == 2
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]


def test_anthropic_provider_429_retries(monkeypatch):
    attempts = {"n": 0}

    async def fast_sleep(delay):
        attempts["slept"] = attempts.get("slept", 0) + 1

    monkeypatch.setattr("app.utils.retry.asyncio.sleep", fast_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json={"content": [{"type": "text", "text": "fine"}]})

    provider = _make_provider(handler)
    assert asyncio.run(provider.complete("s", "u")) == "fine"
    assert attempts["n"] == 3


def test_anthropic_provider_network_error(monkeypatch):
    async def fast_sleep(delay):
        pass

    monkeypatch.setattr("app.utils.retry.asyncio.sleep", fast_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    provider = _make_provider(handler)
    with pytest.raises(LLMError):
        asyncio.run(provider.complete("s", "u"))


# ---------------------------------------------------------------------------
# call_llm_json 与 Mock Provider
# ---------------------------------------------------------------------------

def test_call_llm_json_retry_on_bad_json():
    llm_module.set_provider(MockLLMProvider(scripted=["这不是 JSON", '{"ok": 1}']))
    assert asyncio.run(call_llm_json(SYS, USER)) == {"ok": 1}


def test_call_llm_json_double_failure_raises_llm_error():
    # 两次都解析失败必须抛 LLMError：业务侧所有降级路径都只捕获 LLMError
    llm_module.set_provider(MockLLMProvider(scripted=["nope", "still nope"]))
    with pytest.raises(LLMError):
        asyncio.run(call_llm_json(SYS, USER))


def test_mock_provider_universe_task():
    provider = MockLLMProvider(seed=7)
    system = "[[task:universes]] 平行宇宙生成器。"
    user = "请一次性生成 3 个宇宙，未来 5 年。"

    data = json.loads(asyncio.run(provider.complete(system, user)))
    assert len(data["universes"]) == 3
    for uni in data["universes"]:
        assert set(uni) == {"macro_environment", "career_shock", "financial_shock",
                            "relationship_shock", "opportunity", "random_event"}
        assert all(isinstance(v, str) and v for v in uni.values())


def test_mock_provider_deterministic():
    a = MockLLMProvider(seed=7)
    b = MockLLMProvider(seed=7)
    text = "请模拟从 2026 年开始的 5 年。"
    assert asyncio.run(a.complete("[[task:simulation]]", text)) == asyncio.run(b.complete("[[task:simulation]]", text))
