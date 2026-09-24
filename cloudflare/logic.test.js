import assert from "node:assert/strict";
import test from "node:test";
import { buildResult, normalizeTrajectory, normalizeUniverses, parseModelJson, validateRequest } from "./logic.js";

const request = { profile: "我正在考虑留在目前的城市，还是接受外地的工作机会。", choice_a: "留在目前城市", choice_b: "去外地工作", years: 3, num_lives: 2 };

test("cloud limits keep a run within the free-tier experience", () => {
  assert.deepEqual(validateRequest(request), request);
  assert.throws(() => validateRequest({ ...request, num_lives: 20 }), /2–3/);
  assert.throws(() => validateRequest({ ...request, years: 10 }), /最多模拟 5 年/);
});

test("model output normalizes into the existing result-page contract", () => {
  const universes = normalizeUniverses(parseModelJson('```json\n{"universes":[{"macro_environment":"平稳"},{"macro_environment":"收缩"}]}\n```'), 2);
  const raw = {
    summary: "逐渐找到工作节奏",
    years: Array.from({ length: 3 }, (_, i) => ({ career: `第 ${i + 1} 年` })),
    features: { main_theme: "稳步成长" },
    final_scores: { career: 80, finance: 70, relationship: 60, wellbeing: 75, regret: 20 },
  };
  const trajectories = universes.flatMap(u => ["A", "B"].map(choice => normalizeTrajectory(raw, choice, u, 3)));
  const result = buildResult("sample", request, universes, trajectories, {}, 42, 6);
  assert.equal(result.trajectories.length, 4);
  assert.equal(result.choice_summaries.A.num_lives, 2);
  assert.equal(result.matched_comparison.universe_count, 2);
  assert.equal(result.matched_comparison.metrics.career.close, 2);
  assert.equal(result.choice_summaries.B.overall_score, 73);
  assert.equal(result.stats.llm_calls, 6);
});
