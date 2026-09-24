import { WorkflowEntrypoint } from "cloudflare:workers";
import { buildResult, DEFAULT_LIVES, MAX_LIVES, MAX_YEARS, MODEL, normalizeTrajectory, normalizeUniverses, parseModelJson, validateRequest } from "./logic.js";

const RUN_ID = /^[a-zA-Z0-9_-]{1,100}$/;
const STEP_CONFIG = { retries: { limit: 1, delay: "2 seconds" } };
const JSON_HEADERS = { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" };

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function error(detail, status = 400) {
  return json({ detail }, status);
}

async function readJson(request, maxBytes = 12000) {
  if (Number(request.headers.get("content-length")) > maxBytes) throw new Error("提交的内容过长");
  const text = await request.text();
  if (text.length > maxBytes) throw new Error("提交的内容过长");
  try { return JSON.parse(text); } catch { throw new Error("请求不是有效的 JSON"); }
}

function modelText(response) {
  const text = response?.choices?.[0]?.message?.content ?? response?.response;
  if (typeof text !== "string" || !text.trim()) throw new Error("模型返回了空回复");
  return text;
}

async function askAI(env, system, prompt, maxTokens = 2000) {
  const response = await env.AI.run(env.AI_MODEL || MODEL, {
    messages: [
      { role: "system", content: `${system}\n只输出 JSON，不要 Markdown，不要推理过程。` },
      { role: "user", content: `/no_think\n${prompt}` },
    ],
    max_tokens: maxTokens,
    temperature: 0.7,
    chat_template_kwargs: { enable_thinking: false },
  });
  return parseModelJson(modelText(response));
}

function universePrompt(request) {
  return `用户情况：${request.profile}\n未来 ${request.years} 年。生成 ${request.num_lives} 个彼此不同但现实可信的外部世界，两个选择将共用它们。输出 JSON 对象，键 universes 为数组，每项有 macro_environment、career_shock、financial_shock、relationship_shock、opportunity、random_event 六个简短中文字符串。不要建议选择，也不要编造超自然事件。`;
}

function trajectoryPrompt(request, universe, choice, startYear) {
  const choiceText = choice === "A" ? request.choice_a : request.choice_b;
  return `用户情况：${request.profile}\n选择 ${choice}：${choiceText}\n同一外部世界：${JSON.stringify(universe)}\n从 ${startYear} 年起模拟 ${request.years} 年。用普通人的生活尺度，写具体、连贯、有因果的轨迹，允许好坏混合，不要把模型分数说成真实概率。输出 JSON 对象：summary 为不超过 90 字的摘要；years 为恰好 ${request.years} 项，每项有 career、finance、relationship、location、wellbeing、major_event、decision 七个简短中文字符串；features 为对象，含 career_direction、financial_direction、wellbeing_direction（只用 up/down/flat），location_change、startup、job_switch、relationship_change（布尔值），main_theme（简短中文）；final_scores 为对象，含 career、finance、relationship、wellbeing、regret 五个 0–100 数字，regret 越低越好。保持和外部世界事件一致。`;
}

function insightPrompt(request, trajectories) {
  const brief = trajectories.map(t => ({ choice: t.choice, universe_id: t.universe_id, summary: t.summary, career: t.final_career_score, finance: t.final_finance_score, relationship: t.final_relationship_score, wellbeing: t.final_wellbeing_score, regret: t.regret_score }));
  return `用户情况：${request.profile}\nA：${request.choice_a}\nB：${request.choice_b}\n共享世界中的轨迹：${JSON.stringify(brief)}\n请根据这些小样本做审慎的比较，不要声称预测未来，不要武断推荐。输出 JSON 对象，每个值为 1–2 句中文，键为 structural_difference、deciding_factors、unimportant_factors、who_fits_a、who_fits_b、biggest_risk、info_to_confirm。`;
}

export class SimulationWorkflow extends WorkflowEntrypoint {
  async run(event, step) {
    const { runId, request } = event.payload;
    const startYear = new Date().getFullYear();
    const started = Date.now();

    const universes = await step.do("universes", STEP_CONFIG, async () => {
      const raw = await askAI(this.env, "你负责为人生选择对比设计公平且多样的外部世界。", universePrompt(request), 1100);
      return normalizeUniverses(raw, request.num_lives);
    });

    const trajectories = [];
    for (const universe of universes) {
      for (const choice of ["A", "B"]) {
        const name = `trajectory-${choice}-${universe.id}`;
        const trajectory = await step.do(name, STEP_CONFIG, async () => {
          const raw = await askAI(this.env, "你是严谨的现实人生轨迹模拟器。让人物行为有因果，不编造必然的幸福或灾难。", trajectoryPrompt(request, universe, choice, startYear), 2300);
          return normalizeTrajectory(raw, choice, universe, request.years);
        });
        trajectories.push(trajectory);
      }
    }

    const insight = await step.do("insight", STEP_CONFIG, () => askAI(this.env, "你负责解释两种选择的结构性差异和需要核实的信息。", insightPrompt(request, trajectories), 900));
    return buildResult(runId, request, universes, trajectories, insight, (Date.now() - started) / 1000, 2 + trajectories.length);
  }
}

async function workflowStatus(env, runId) {
  if (!RUN_ID.test(runId)) return null;
  try {
    const instance = await env.SIMULATION.get(runId);
    return await instance.status();
  } catch { return null; }
}

function statusPayload(runId, state) {
  if (state.status === "complete") return { run_id: runId, stage: "done", progress: 1, message: "模拟完成", detail: {}, error: null, updated_at: null };
  if (state.status === "errored" || state.status === "terminated") {
    return { run_id: runId, stage: "failed", progress: 0, message: "云端模拟失败，请稍后重试。", detail: {}, error: "模型或云端额度暂时不可用", updated_at: null };
  }
  return { run_id: runId, stage: state.status === "queued" ? "queued" : "simulation", progress: state.status === "queued" ? 0 : 0.15, message: state.status === "queued" ? "排队中…" : "云端正在生成平行人生；小样本报告需要几分钟。", detail: {}, error: null, updated_at: null };
}

async function completeResult(env, runId) {
  const state = await workflowStatus(env, runId);
  return state?.status === "complete" && state.output?.request ? state.output : null;
}

function safeScriptJson(value) {
  return JSON.stringify(value).replace(/[<>&\u2028\u2029]/g, c => ({ "<": "\\u003c", ">": "\\u003e", "&": "\\u0026", "\u2028": "\\u2028", "\u2029": "\\u2029" })[c]);
}

async function assetText(env, path) {
  const response = await env.ASSETS.fetch(`https://assets.local${path}`);
  if (!response.ok) throw new Error(`缺少网页资源 ${path}`);
  return response.text();
}

async function standaloneHtml(env, data) {
  const [template, css, script] = await Promise.all([
    assetText(env, "/result.html"), assetText(env, "/static/style.css"), assetText(env, "/static/result.js"),
  ]);
  return template
    .replace('<link rel="stylesheet" href="/static/style.css">', `<style>\n${css}\n</style>`)
    .replace('<script src="/static/result.js" defer></script>', `<script>window.__100_LIVES_RESULT__=${safeScriptJson(data)};window.__100_LIVES_STANDALONE__=true;</script><script>\n${script}\n</script>`);
}

async function futureChat(env, raw) {
  const runId = String(raw?.run_id || "");
  const trajectoryId = String(raw?.trajectory_id || "");
  const message = String(raw?.message || "").trim();
  const history = Array.isArray(raw?.history) ? raw.history.slice(-10) : [];
  if (!RUN_ID.test(runId) || !trajectoryId || !message || message.length > 2000) return error("对话内容有误", 400);
  const result = await completeResult(env, runId);
  if (!result) return error("未找到该报告，或报告已过期", 404);
  const trajectory = result.trajectories.find(t => t.id === trajectoryId);
  if (!trajectory) return error("未找到该轨迹", 404);
  const futureYear = result.start_year + result.request.years - 1;
  const turns = history.filter(x => ["user", "assistant"].includes(x?.role) && typeof x?.content === "string").map(x => ({ role: x.role, content: x.content.slice(0, 1000) }));
  const response = await env.AI.run(env.AI_MODEL || MODEL, {
    messages: [
      { role: "system", content: `你是 ${futureYear} 年的这个人，基于以下虚构模拟轨迹聊天。不要声称真的预测未来。个人情况：${result.request.profile}\n轨迹：${JSON.stringify(trajectory).slice(0, 5000)}` },
      ...turns,
      { role: "user", content: message },
    ],
    max_tokens: 450,
    temperature: 0.7,
    chat_template_kwargs: { enable_thinking: false },
  });
  return json({ reply: modelText(response), future_year: futureYear });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    try {
      if (path === "/api/health" && request.method === "GET") return json({ status: "ok", llm_configured: true, mode: "cloudflare" });
      if (path === "/api/config" && request.method === "GET") return json({ mode: "cloudflare", max_lives: MAX_LIVES, default_lives: DEFAULT_LIVES, max_years: MAX_YEARS });
      if (path === "/api/simulate" && request.method === "POST") {
        let input;
        try { input = validateRequest(await readJson(request)); } catch (e) { return error(e.message); }
        const runId = crypto.randomUUID();
        await env.SIMULATION.create({ id: runId, params: { runId, request: input } });
        return json({ run_id: runId }, 202);
      }
      const match = path.match(/^\/api\/(status|result)\/([^/]+)(\/html)?$/);
      if (match && request.method === "GET") {
        const [, kind, runId, html] = match;
        if (!RUN_ID.test(runId)) return error("未找到该运行", 404);
        if (kind === "status" && !html) {
          const state = await workflowStatus(env, runId);
          return state ? json(statusPayload(runId, state)) : error("未找到该运行", 404);
        }
        if (kind === "result") {
          const data = await completeResult(env, runId);
          if (!data) return error("报告尚未完成或已过期", 404);
          if (html) return new Response(await standaloneHtml(env, data), { headers: { "content-type": "text/html; charset=utf-8", "content-disposition": `attachment; filename="100-lives-${runId}.html"`, "cache-control": "no-store" } });
          return json(data);
        }
      }
      if (path === "/api/future-self-chat" && request.method === "POST") return futureChat(env, await readJson(request, 20000));
      if (/^\/result\/[^/]+$/.test(path) && request.method === "GET") {
        const response = await env.ASSETS.fetch(new URL("/result.html", url));
        return new Response(response.body, { status: response.status, headers: { ...Object.fromEntries(response.headers), "cache-control": "no-store" } });
      }
      if (path.startsWith("/api/")) return error("未找到接口", 404);
      return env.ASSETS.fetch(request);
    } catch (e) {
      console.error("request failed", e);
      return error("云端服务暂时不可用，请稍后重试", 503);
    }
  },
};
