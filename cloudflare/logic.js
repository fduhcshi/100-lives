// Small Cloudflare edition. The local Python pipeline remains the full edition.
export const MODEL = "@cf/qwen/qwen3-30b-a3b-fp8";
export const MAX_LIVES = 3;
export const DEFAULT_LIVES = 2;
export const MAX_YEARS = 5;

export const DISCLAIMER = "本页所有数字是「在当前模型、提示词与采样策略下，这种结果在模拟轨迹中出现的频率」，不是现实概率，也不是对未来的预测。云端版是小样本体验，分数只是模型内部比较指标。";

const UNIVERSE_FIELDS = ["macro_environment", "career_shock", "financial_shock", "relationship_shock", "opportunity", "random_event"];
const YEAR_FIELDS = ["career", "finance", "relationship", "location", "wellbeing", "major_event", "decision"];
const SCORE_FIELDS = ["career", "finance", "relationship", "wellbeing", "regret"];
const LABELS = { career: "职业发展", finance: "财务状况", relationship: "亲密关系", wellbeing: "生活满意度", regret: "后悔程度（越低越好）" };

const string = (value, limit = 300) => typeof value === "string" ? value.trim().slice(0, limit) : "";
const list = (value, limit = 5) => Array.isArray(value) ? value.filter(x => typeof x === "string").map(x => string(x, 200)).filter(Boolean).slice(0, limit) : [];
const number = value => Number.isFinite(Number(value)) ? Math.max(0, Math.min(100, Number(value))) : null;
const direction = value => ["up", "down", "flat"].includes(value) ? value : "flat";

export function validateRequest(raw) {
  if (!raw || typeof raw !== "object") throw new Error("请填写模拟内容。");
  const profile = string(raw.profile, 1501);
  const choice_a = string(raw.choice_a, 201);
  const choice_b = string(raw.choice_b, 201);
  const years = Number(raw.years);
  const num_lives = Number(raw.num_lives);
  if (profile.length < 10 || profile.length > 1500) throw new Error("个人情况需为 10–1500 字。云端版限制输入长度以节省额度。");
  if (!choice_a || choice_a.length > 200 || !choice_b || choice_b.length > 200) throw new Error("每个选择需为 1–200 字。");
  if (!Number.isInteger(years) || years < 1 || years > MAX_YEARS) throw new Error(`云端版最多模拟 ${MAX_YEARS} 年。`);
  if (!Number.isInteger(num_lives) || num_lives < 2 || num_lives > MAX_LIVES) throw new Error(`云端版每个选择可模拟 2–${MAX_LIVES} 条人生。`);
  return { profile, choice_a, choice_b, years, num_lives };
}

export function parseModelJson(text) {
  const cleaned = String(text || "").replace(/<think>[\s\S]*?<\/think>/g, "").trim();
  const start = Math.min(...[cleaned.indexOf("{"), cleaned.indexOf("[")].filter(x => x >= 0));
  const end = Math.max(cleaned.lastIndexOf("}"), cleaned.lastIndexOf("]"));
  if (!Number.isFinite(start) || end < start) throw new Error("模型未返回有效 JSON");
  return JSON.parse(cleaned.slice(start, end + 1));
}

export function normalizeUniverses(raw, count) {
  const source = Array.isArray(raw) ? raw : raw?.universes;
  if (!Array.isArray(source) || source.length < count) throw new Error("模型生成的平行世界数量不足");
  return source.slice(0, count).map((item, index) => {
    if (!item || typeof item !== "object" || !string(item.macro_environment)) throw new Error("平行世界内容不完整");
    return { id: index + 1, ...Object.fromEntries(UNIVERSE_FIELDS.map(key => [key, string(item[key], 200)])) };
  });
}

export function normalizeTrajectory(raw, choice, universe, years) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.years) || raw.years.length < years || !string(raw.summary)) {
    throw new Error("模型生成的人生轨迹不完整");
  }
  const scores = raw.final_scores || raw;
  if (SCORE_FIELDS.some(key => number(scores[key]) === null)) throw new Error("模型生成的轨迹缺少评分");
  const features = raw.features || {};
  return {
    id: `${choice.toLowerCase()}_u${String(universe.id).padStart(2, "0")}`,
    universe_id: universe.id,
    choice,
    summary: string(raw.summary, 500),
    years: raw.years.slice(0, years).map((row, index) => ({ year: index + 1, ...Object.fromEntries(YEAR_FIELDS.map(key => [key, string(row?.[key])])) })),
    features: {
      career_direction: direction(features.career_direction),
      financial_direction: direction(features.financial_direction),
      wellbeing_direction: direction(features.wellbeing_direction),
      location_change: features.location_change === true,
      startup: features.startup === true,
      job_switch: features.job_switch === true,
      relationship_change: features.relationship_change === true,
      main_theme: string(features.main_theme, 60) || "unknown",
    },
    final_career_score: number(scores.career),
    final_finance_score: number(scores.finance),
    final_relationship_score: number(scores.relationship),
    final_wellbeing_score: number(scores.wellbeing),
    regret_score: number(scores.regret),
    critic: null,
    regenerated: 0,
    cluster_name: string(features.main_theme, 60) || "个人路径",
  };
}

function summary(choiceText, trajectories) {
  const n = trajectories.length;
  const avg = field => Math.round(trajectories.reduce((sum, t) => sum + t[field], 0) / n * 10) / 10;
  const career = avg("final_career_score");
  const finance = avg("final_finance_score");
  const relationship = avg("final_relationship_score");
  const wellbeing = avg("final_wellbeing_score");
  const regret = avg("regret_score");
  return {
    choice_text: choiceText,
    num_lives: n,
    avg_career_score: career,
    avg_finance_score: finance,
    avg_relationship_score: relationship,
    avg_wellbeing_score: wellbeing,
    avg_regret_score: regret,
    overall_score: Math.round((career + finance + relationship + wellbeing + 100 - regret) / 5 * 10) / 10,
    common_risks: [],
    common_opportunities: [],
    most_typical_trajectory_id: trajectories[0]?.id || null,
    most_surprising_trajectory_id: trajectories.at(-1)?.id || null,
    clusters: trajectories.map(t => ({
      name: t.cluster_name,
      description: t.summary,
      trajectory_ids: [t.id],
      common_pattern: t.summary,
      key_risk: "",
      key_opportunity: "",
      representative_trajectory_id: t.id,
    })),
  };
}

function matched(universes, trajectories) {
  const a = new Map(trajectories.filter(t => t.choice === "A").map(t => [t.universe_id, t]));
  const b = new Map(trajectories.filter(t => t.choice === "B").map(t => [t.universe_id, t]));
  const metrics = Object.fromEntries(SCORE_FIELDS.map(key => [key, { label: LABELS[key], a_better: 0, b_better: 0, close: 0 }]));
  const examples = [];
  for (const u of universes) {
    const ta = a.get(u.id), tb = b.get(u.id);
    if (!ta || !tb) continue;
    for (const key of SCORE_FIELDS) {
      let delta = ta[`final_${key}_score`] - tb[`final_${key}_score`];
      if (key === "regret") delta = tb.regret_score - ta.regret_score;
      const counter = metrics[key];
      if (delta > 3) counter.a_better++;
      else if (delta < -3) counter.b_better++;
      else counter.close++;
    }
    examples.push({ universe_id: u.id, macro_environment: u.macro_environment, title: "同一世界的两种选择", narrative: `选择 A：${ta.summary} 选择 B：${tb.summary}` });
  }
  return { universe_count: examples.length, metrics, examples, divergence_insight: "同一个外部环境下，不同选择会形成不同的路径；请重点比较自己能否承受对应的代价。" };
}

export function buildResult(runId, request, universes, trajectories, insight, durationSeconds, llmCalls) {
  const choiceA = trajectories.filter(t => t.choice === "A");
  const choiceB = trajectories.filter(t => t.choice === "B");
  if (!choiceA.length || !choiceB.length) throw new Error("没有生成完整的 A/B 轨迹");
  const fields = ["structural_difference", "deciding_factors", "unimportant_factors", "who_fits_a", "who_fits_b", "biggest_risk", "info_to_confirm"];
  return {
    run_id: runId,
    created_at: new Date().toISOString(),
    start_year: new Date().getFullYear(),
    request,
    universes,
    trajectories: [...trajectories].sort((x, y) => x.choice.localeCompare(y.choice) || x.universe_id - y.universe_id),
    choice_summaries: { A: summary(request.choice_a, choiceA), B: summary(request.choice_b, choiceB) },
    matched_comparison: matched(universes, trajectories),
    insight: Object.fromEntries(fields.map(key => [key, string(insight?.[key], 500)])),
    stats: { llm_calls: llmCalls, regenerations: 0, duration_seconds: Math.round(durationSeconds), failed_trajectories: 0 },
    disclaimer: DISCLAIMER,
  };
}
