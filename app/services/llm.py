"""统一 LLM 适配层。

业务代码只调用 call_llm / call_llm_json，不绑定任何具体 API。
当前提供两个 Provider：

- AnthropicCompatProvider：Anthropic Messages 兼容接口（网关 / 官方 / 代理均可）
- MockLLMProvider：离线模板输出，供开发与测试使用

网关地址、密钥、模型名全部来自环境配置，代码中不出现任何真实值。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import re
from abc import ABC, abstractmethod
from contextvars import ContextVar
from typing import Any

import httpx

from app.config import settings
from app.utils.json_parser import JSONParseError, extract_json
from app.utils.logger import get_logger
from app.utils.retry import retry_async

logger = get_logger("llm")

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMError(Exception):
    """LLM 调用失败。"""


class LLMNotConfiguredError(LLMError):
    """LLM 未配置（无密钥/地址/模型，且未开启 Mock）。"""


class RetryableLLMError(LLMError):
    """可重试的 LLM 错误（限流/网关抖动）。"""


def _status_hint(status_code: int) -> str:
    """把网关 HTTP 状态翻译成不含内部信息的中文提示。"""
    hints = {
        400: "网关拒绝了请求参数（HTTP 400）",
        401: "网关鉴权失败：请检查 API Key 是否正确（HTTP 401）",
        403: "网关拒绝了访问权限（HTTP 403）",
        404: "网关上找不到该模型或端点：请检查 LLM_MODEL / LLM_BASE_URL（HTTP 404）",
        413: "请求体过大（HTTP 413）",
        422: "网关无法处理该请求（HTTP 422）",
    }
    return hints.get(status_code, f"网关返回了异常响应（HTTP {status_code}）")


# ---------------------------------------------------------------------------
# Provider 接口
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self, system_prompt: str, user_prompt: str, *, temperature: float = 0.8, max_tokens: int = 4096
    ) -> str:
        raise NotImplementedError


class AnthropicCompatProvider(LLMProvider):
    """Anthropic Messages 兼容接口。

    - 同时发送 x-api-key 与 authorization，兼容常见网关。
    - 对 429/5xx/网络错误做指数退避重试。
    - 网关不认识 temperature / system 参数时自动降级重试一次。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        max_concurrency: int = 20,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = self._normalize_endpoint(base_url)
        self._api_key = api_key
        self._model = model
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15.0, read=300.0, write=30.0, pool=15.0),
            limits=httpx.Limits(
                max_connections=max_concurrency + 8,
                max_keepalive_connections=max_concurrency + 4,
            ),
            transport=transport,
        )

    @staticmethod
    def _normalize_endpoint(base_url: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/v1/messages"):
            return base
        if base.endswith("/v1"):
            return f"{base}/messages"
        return f"{base}/v1/messages"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "authorization": f"Bearer {self._api_key}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        def call() -> Any:
            return self._client.post(self._endpoint, headers=self._headers(), json=payload)

        async def do_call() -> httpx.Response:
            try:
                return await call()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise RetryableLLMError(f"网络错误: {exc.__class__.__name__}") from exc

        try:
            return await retry_async(do_call, attempts=3, base_delay=1.5, label="llm")
        except RetryableLLMError as exc:
            raise LLMError(str(exc)) from exc

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        content = data.get("content")
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            return "".join(parts)
        if isinstance(content, str):
            return content
        return ""

    async def complete(
        self, system_prompt: str, user_prompt: str, *, temperature: float = 0.8, max_tokens: int = 4096
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt
        if temperature is not None:
            payload["temperature"] = max(0.0, min(1.0, temperature))

        for attempt in range(1, 4):
            resp = await self._post(payload)

            if resp.status_code in _RETRYABLE_STATUS:
                if attempt == 3:
                    raise LLMError(f"网关持续返回 HTTP {resp.status_code}")
                await asyncio.sleep(1.5 * attempt)
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError as exc:
                    raise LLMError("网关返回了非 JSON 响应") from exc
                text = self._extract_text(data)
                if not text.strip():
                    raise LLMError("网关返回了空回复")
                if data.get("stop_reason") == "max_tokens":
                    logger.warning("回复可能被 max_tokens 截断（%s 字符）", len(text))
                return text

            # 400：尝试参数降级（部分网关不支持 temperature / system）
            if resp.status_code == 400 and "temperature" in payload:
                logger.warning("网关拒绝 temperature 参数，去掉后重试")
                payload.pop("temperature", None)
                continue
            if resp.status_code == 400 and "system" in payload:
                logger.warning("网关拒绝 system 参数，合并进首条 user 消息后重试")
                merged = f"{system_prompt}\n\n---\n\n{user_prompt}"
                payload.pop("system", None)
                payload["messages"] = [{"role": "user", "content": merged}]
                continue

            # 错误原文只进服务端日志；异常消息不带网关内部信息（避免泄漏到前端）
            logger.warning("网关返回 HTTP %s：%s", resp.status_code, resp.text[:400])
            raise LLMError(_status_hint(resp.status_code))

        raise LLMError("LLM 调用失败（未知原因）")

    async def aclose(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Mock Provider（离线开发 / 测试）
# ---------------------------------------------------------------------------

_UNIVERSE_POOL = {
    "macro_environment": [
        "AI行业继续增长，但招聘比前两年更加理性",
        "宏观经济下行，行业进入收缩期",
        "行业平稳，没有大浪也没有风口",
        "政策出现利好，相关赛道升温",
        "资本市场回暖，跳槽窗口变多",
    ],
    "career_shock": [
        "第二年遇到一次组织调整", "第一年项目被砍，团队合并",
        "第三年部门扩编，出现管理岗", "第二年直属领导离职",
        "第四年公司业务收缩，开始冻结招聘",
    ],
    "financial_shock": [
        "第三年市场行情较好", "第二年年终奖缩水",
        "房价和租金走势平稳", "第二年股市波动加大",
        "第四年所在行业薪酬普涨",
    ],
    "relationship_shock": [
        "第四年家庭因素导致城市选择压力增加", "第二年异地问题开始显现",
        "第三年朋友圈因搬家而重组", "第一年伴侣工作变忙，相处时间减少",
        "第五年家人健康问题需要照顾",
    ],
    "opportunity": [
        "第三年出现创业团队邀请", "第二年出现内部转岗机会",
        "第四年出现去海外团队的机会", "第二年有个老同事拉你合伙做副业",
        "第三年头部公司开放了你匹配的岗位",
    ],
    "random_event": [
        "认识一个对职业发展影响很大的朋友", "一次体检结果敲响警钟",
        "偶然参加的行业聚会带来新信息", "老家发生一件事让你重新思考优先级",
        "一次失败的面试反而带来了新认识",
    ],
}

_THEMES = ["high_income_high_pressure", "stable_slow_burn", "pivot_and_retry",
           "family_first", "startup_gamble", "quiet_plateau"]

_SUMMARY_TEMPLATES = [
    "前两年稳步积累，{mid}年遇到转折后调整方向，最终{ending}。",
    "开局顺利，{mid}年外部冲击打乱节奏，之后{ending}。",
    "起伏明显的一年，{mid}年抓住机会，{ending}。",
]

_MID_EVENTS = ["第二", "第三", "第四"]
_ENDINGS = ["进入相对稳定的状态", "重新找回节奏", "在取舍中找到了新的平衡",
            "仍在调整期，留有悬念", "收获了意料之外的成长"]


class MockLLMProvider(LLMProvider):
    """离线 Mock：按 system prompt 里的 [[task:xxx]] 标记生成对应结构的模板内容。

    - seed 决定随机性，相同输入可复现。
    - 可选 scripted 队列优先弹出（单元测试精确控制每一轮输出）。
    """

    def __init__(self, seed: int = 42, scripted: list[str] | None = None) -> None:
        self.seed = seed
        self._scripted = list(scripted or [])

    def _rng(self, context: str) -> random.Random:
        digest = hashlib.sha256(f"{self.seed}:{context}".encode("utf-8")).hexdigest()[:8]
        return random.Random(int(digest, 16))

    async def complete(
        self, system_prompt: str, user_prompt: str, *, temperature: float = 0.8, max_tokens: int = 4096
    ) -> str:
        if self._scripted:
            return self._scripted.pop(0)

        match = re.search(r"\[\[task:(\w+)\]\]", system_prompt or "")
        task = match.group(1) if match else ""
        rng = self._rng(task + (user_prompt or "")[:200])
        handler = getattr(self, f"_gen_{task}", None)
        if handler is None:
            handler = self._gen_chat
        return handler(rng, user_prompt or "")

    # -- 各任务的模板输出 ---------------------------------------------------

    def _gen_universes(self, rng: random.Random, user: str) -> str:
        n_match = re.search(r"一次性生成\s*(\d+)\s*个", user)
        n = int(n_match.group(1)) if n_match else 10
        universes = []
        for _ in range(n):
            uni = {key: rng.choice(pool) for key, pool in _UNIVERSE_POOL.items()}
            universes.append(uni)
        return json.dumps({"universes": universes}, ensure_ascii=False)

    def _gen_simulation(self, rng: random.Random, user: str) -> str:
        years_match = re.search(r"开始的\s*(\d+)\s*年", user)
        years = int(years_match.group(1)) if years_match else 5
        year_rows = []
        for y in range(1, years + 1):
            year_rows.append({
                "year": y,
                "career": rng.choice(["职级小幅提升，职责扩大", "工作内容平稳，积累人脉",
                                      "换了方向，从零开始", "带小团队，压力变大", "岗位停滞，开始观望"]),
                "finance": rng.choice(["收入略增，储蓄稳步上涨", "收支平衡，大额支出增加",
                                       "收入波动，理财收益一般", "存款过了一个台阶", "为搬家付出一笔成本"]),
                "relationship": rng.choice(["关系稳定，沟通变多", "聚少离多，开始有摩擦",
                                           "认识新朋友，社交圈扩大", "家里开始催婚", "和伴侣一起做了个决定"]),
                "location": rng.choice(["北京", "广州", "成都", "武汉", "西安"]),
                "wellbeing": rng.choice(["精力充沛，作息规律", "长期高压，睡眠变差",
                                         "开始规律运动，状态回升", "情绪平稳但有些倦怠", "焦虑感增加，学会放松"]),
                "major_event": rng.choice(["部门重组，进入新方向", "一次重要的项目成败",
                                           "家里的一件事改变了优先级", "遇到一个关键的人",
                                           "一次说走就走的长期旅行"]),
                "decision": rng.choice(["主动争取核心项目", "按兵不动，继续积累",
                                        "接受新的挑战", "给自己留出休息期", "调整目标，降低节奏"]),
            })
        mid = rng.choice(_MID_EVENTS)
        ending = rng.choice(_ENDINGS)
        summary = rng.choice(_SUMMARY_TEMPLATES).format(mid=mid, ending=ending)
        return json.dumps({
            "summary": summary,
            "years": year_rows,
            "features": {
                "career_direction": rng.choice(["up", "down", "flat"]),
                "location_change": rng.random() < 0.3,
                "startup": rng.random() < 0.15,
                "job_switch": rng.random() < 0.4,
                "relationship_change": rng.random() < 0.4,
                "financial_direction": rng.choice(["up", "down", "flat"]),
                "wellbeing_direction": rng.choice(["up", "down", "flat"]),
                "main_theme": rng.choice(_THEMES),
            },
            "final_scores": {
                "career": rng.randint(45, 92),
                "finance": rng.randint(40, 90),
                "relationship": rng.randint(45, 90),
                "wellbeing": rng.randint(40, 88),
                "regret": rng.randint(15, 70),
            },
        }, ensure_ascii=False)

    def _gen_critic(self, rng: random.Random, user: str) -> str:
        accept = rng.random() < 0.9
        base = rng.randint(62, 95)
        return json.dumps({
            "consistency": base,
            "realism": min(100, base + rng.randint(-5, 5)),
            "coherence": min(100, base + rng.randint(-5, 5)),
            "diversity": min(100, base + rng.randint(-10, 10)),
            "accepted": accept,
            "problems": [] if accept else ["部分年份之间的因果衔接不够自然"],
        }, ensure_ascii=False)

    def _gen_cluster(self, rng: random.Random, user: str) -> str:
        ids = re.findall(r"\b([ab]_u\d+)\b", user)
        seen: list[str] = []
        for tid in ids:
            if tid not in seen:
                seen.append(tid)
        if not seen:
            return json.dumps({"clusters": [], "most_typical_trajectory_id": None,
                               "most_surprising_trajectory_id": None,
                               "common_risks": [], "common_opportunities": []}, ensure_ascii=False)
        k = 3 if len(seen) >= 6 else max(2, len(seen) // 2)
        names = ["高收入高压力线", "稳步积累型", "转折重启型", "平稳守成型", "倦怠调整型"]
        clusters = []
        for i, tid in enumerate(seen):
            slot = i % k
            while len(clusters) <= slot:
                clusters.append({"name": names[len(clusters) % len(names)],
                                 "description": "一类有共同起伏模式的人生。",
                                 "trajectory_ids": [], "common_pattern": "节奏相似，关键节点接近。",
                                 "key_risk": "外部冲击下没有缓冲。",
                                 "key_opportunity": "中期出现一次关键机会。",
                                 "representative_trajectory_id": None})
            clusters[slot]["trajectory_ids"].append(tid)
        for cluster in clusters:
            cluster["representative_trajectory_id"] = cluster["trajectory_ids"][0]
        return json.dumps({
            "clusters": clusters,
            "most_typical_trajectory_id": seen[len(seen) // 2],
            "most_surprising_trajectory_id": seen[0],
            "common_risks": ["长期高压带来健康与关系损耗", "关键机会窗口期很短", "外部环境变化快于预期"],
            "common_opportunities": ["中期出现一次关键机会", "人脉在第二年开始发挥作用", "财务上有一次结构性改善的可能"],
        }, ensure_ascii=False)

    def _gen_matched(self, rng: random.Random, user: str) -> str:
        return json.dumps({
            "examples": [
                {"universe_id": 1, "title": "同样面对行业波动时",
                 "narrative": "选择 A 的你选择稳住基本盘；选择 B 的你在第三年主动转岗，付出了短期代价。"},
                {"universe_id": 2, "title": "机会来临时",
                 "narrative": "选择 A 的你按兵不动；选择 B 的你抓住了新出现的窗口。"},
            ],
            "divergence_insight": "真正造成差异的不是第一年的收入，而是第二到第三年对机会的响应方式。",
        }, ensure_ascii=False)

    def _gen_insight(self, rng: random.Random, user: str) -> str:
        return json.dumps({
            "structural_difference": "A 的路径更依赖既有平台的积累，B 的路径更依赖新环境的适配速度。",
            "deciding_factors": "决定结果好坏的主要是第二到第三年出现的机会窗口，以及是否有缓冲垫。",
            "unimportant_factors": "第一年的收入差距在多数世界里最终影响都有限。",
            "who_fits_a": "更看重存量积累、讨厌重启成本的人。",
            "who_fits_b": "愿意用短期不确定性换长期空间的人。",
            "biggest_risk": "两个选择共同的最大的风险是：在没有缓冲的情况下做大幅调整。",
            "info_to_confirm": "建议在决定前进一步确认：新环境里前两年真实的成长速度与退出成本。",
        }, ensure_ascii=False)

    def _gen_chat(self, rng: random.Random, user: str) -> str:
        return ("这条轨迹里的事我记得很清楚：头两年确实不容易，但第三年的那个转折很关键。"
                "如果说有什么想对你说的——把节奏掌握在自己手里，比选哪条路更重要。（离线 Mock 回答）")


# ---------------------------------------------------------------------------
# 模块级入口
# ---------------------------------------------------------------------------

_provider: LLMProvider | None = None


class CallStats:
    """一次 run 范围内的 LLM 调用计数（contextvar 传递，天然并发安全）。"""

    def __init__(self) -> None:
        self.calls = 0


_stats_var: ContextVar[CallStats | None] = ContextVar("llm_call_stats", default=None)


def begin_call_tracking() -> CallStats:
    """开启本任务树的调用计数；返回统计对象。"""
    stats = CallStats()
    _stats_var.set(stats)
    return stats


def end_call_tracking() -> None:
    _stats_var.set(None)


def llm_mock_enabled() -> bool:
    return settings.llm_mock


def llm_configured() -> bool:
    return settings.llm_mock or settings.llm_configured


def get_provider() -> LLMProvider:
    global _provider
    if _provider is not None:
        return _provider
    if settings.llm_mock:
        _provider = MockLLMProvider(seed=42)
        logger.warning("LLM Mock 模式已启用：输出为模板内容，仅用于开发/测试")
        return _provider
    if not settings.llm_configured:
        raise LLMNotConfiguredError(
            "LLM 未配置：请在 .env 中设置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL，"
            "或设置 LLM_MOCK=1 使用离线 Mock。"
        )
    assert settings.llm_base_url and settings.llm_api_key and settings.llm_model
    _provider = AnthropicCompatProvider(
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model,
        max_concurrency=settings.max_concurrency,
    )
    logger.info("LLM Provider 已就绪（Anthropic Messages 兼容接口）")
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """测试注入用。"""
    global _provider
    _provider = provider


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.8,
    max_tokens: int = 4096,
) -> str:
    provider = get_provider()
    stats = _stats_var.get()
    if stats is not None:
        stats.calls += 1
    try:
        return await provider.complete(
            system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens
        )
    except LLMNotConfiguredError:
        raise
    except LLMError:
        raise
    except Exception as exc:  # Provider 实现里的意外错误统一归一化
        raise LLMError(f"{exc.__class__.__name__}: {exc}") from exc


async def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.8,
    max_tokens: int = 8192,
) -> Any:
    """调用 LLM 并提取 JSON；第一次解析失败时追加纠正指令重试一次。

    两次都解析失败时抛 LLMError（而不是 JSONParseError）——所有业务侧的
    `except LLMError` 降级路径（聚类兜底、叙事模板、宇宙补齐）都依赖这一点。
    """
    text = await call_llm(system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens)
    try:
        return extract_json(text)
    except JSONParseError:
        logger.warning("输出不是合法 JSON，追加纠正指令重试一次")
        retry_prompt = (
            f"{user_prompt}\n\n---\n你上一次的输出不是合法 JSON（或 JSON 不完整）。"
            "请重新输出，只输出一个完整、合法的 JSON，不要任何其他文字。"
        )
        text2 = await call_llm(system_prompt, retry_prompt, temperature=temperature, max_tokens=max_tokens)
        try:
            return extract_json(text2)
        except JSONParseError as exc:
            raise LLMError("模型两次均未返回有效 JSON（内容可能被截断），已放弃解析") from exc
