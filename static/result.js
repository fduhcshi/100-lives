/* 100 LIVES — result page logic (vanilla JS, ES2020) */
"use strict";

(function () {
  var $ = function (id) { return document.getElementById(id); };

  /* ---------------- tiny helpers ---------------- */

  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null && txt !== "") n.textContent = String(txt);
    return n;
  }
  /* 1 decimal max, no trailing .0 */
  function fmt(v) {
    if (typeof v !== "number" || !isFinite(v)) return "—";
    var r = Math.round(v * 10) / 10;
    return Number.isInteger(r) ? String(r) : r.toFixed(1);
  }
  function clamp100(v) { return Math.max(0, Math.min(100, typeof v === "number" && isFinite(v) ? v : 0)); }
  function lower(choice) { return String(choice || "a").toLowerCase() === "b" ? "b" : "a"; }
  function dot(cls) { var d = el("span", "dot " + cls); d.setAttribute("aria-hidden", "true"); return d; }

  var SCORE_ROWS = [
    { key: "avg_career_score", label: "职业发展" },
    { key: "avg_finance_score", label: "财务状况" },
    { key: "avg_relationship_score", label: "亲密关系" },
    { key: "avg_wellbeing_score", label: "生活满意度" },
    { key: "avg_regret_score", label: "后悔指数（越低越好）" }
  ];
  var TRAJ_SCORES = [
    { key: "final_career_score", label: "职业" },
    { key: "final_finance_score", label: "财务" },
    { key: "final_relationship_score", label: "关系" },
    { key: "final_wellbeing_score", label: "满意度" },
    { key: "regret_score", label: "后悔（低=好）" }
  ];
  var MATCH_ORDER = ["career", "finance", "relationship", "wellbeing", "regret"];

  /* ---------------- state ---------------- */

  var RUN_ID = null;
  var DATA = null;
  var trajMap = new Map();
  var universeMap = new Map();
  var chatStore = new Map(); /* trajId -> { turns: [], futureYear } */
  var activeTraj = null;
  var lastFocused = null;
  var chatBusy = false;
  var weights = [20, 20, 20, 20, 20];
  var matrixMetric = -1;
  var selectedWorld = null;

  /* ---------------- boot ---------------- */

  (function boot() {
    var embedded = window.__100_LIVES_RESULT__;
    if (embedded && embedded.request) {
      RUN_ID = embedded.run_id || null;
      showResult(embedded);
      return;
    }
    var m = location.pathname.match(/^\/result\/([^\/?#]+)/);
    RUN_ID = m ? decodeURIComponent(m[1]) : null;
    if (!RUN_ID) { showNotFound(); return; }
    loadResult();
  })();

  async function loadResult() {
    var data = null;
    try {
      var res = await fetch("/api/result/" + encodeURIComponent(RUN_ID));
      if (res.ok) data = await res.json();
    } catch (e) { data = null; }
    if (!data || !data.request) { showNotFound(); return; }
    showResult(data);
  }

  function showResult(data) {
    DATA = data;
    indexData();
    $("loading").style.display = "none";
    $("result-main").style.display = "block";
    renderAll();
  }

  function showNotFound() {
    $("loading").style.display = "none";
    $("not-found").style.display = "block";
  }

  function indexData() {
    (DATA.trajectories || []).forEach(function (t) { trajMap.set(t.id, t); });
    (DATA.universes || []).forEach(function (u) { universeMap.set(u.id, u); });
  }

  function renderAll() {
    renderHead();
    renderOverview();
    renderMatched();
    renderClusters();
    renderInsight();
    renderNotable();
    renderTable();
    renderStory();
  }

  /* ---------------- header ---------------- */

  function renderHead() {
    var req = DATA.request;
    var mc = DATA.matched_comparison || {};
    var uniCount = (typeof mc.universe_count === "number") ? mc.universe_count : req.num_lives;
    /* 使用实际生成的轨迹数（降级运行时可能少于请求的 num_lives） */
    var list = DATA.trajectories || [];
    var totals = { A: 0, B: 0 };
    list.forEach(function (t) { if (totals[t.choice] != null) totals[t.choice]++; });
    var perChoice = (totals.A === totals.B)
      ? "每个选择 " + totals.A + " 条"
      : "选择 A " + totals.A + " 条 · 选择 B " + totals.B + " 条";
    $("result-title").textContent = "你的 " + list.length + " 个平行人生";
    $("result-sub").textContent = req.years + " 年 · " + perChoice + " · " + uniCount + " 个共享平行世界";

    var download = $("download-report");
    var filename = "100-lives-" + (DATA.run_id || RUN_ID || "report") + ".html";
    download.setAttribute("download", filename);
    download.href = window.__100_LIVES_STANDALONE__
      ? location.href
      : "/api/result/" + encodeURIComponent(DATA.run_id || RUN_ID) + "/html";

    var line = $("result-choices");
    line.textContent = "";
    line.appendChild(choiceTag("A", req.choice_a));
    line.appendChild(choiceTag("B", req.choice_b));

    $("disclaimer-text").textContent = DATA.disclaimer ||
      "本页所有数字是『在当前模型与提示词下的模拟出现频率』，不是现实概率，也不是预测。";
    $("footer-note").textContent = "⚠ " + (DATA.disclaimer ||
      "本页所有数字是『在当前模型与提示词下的模拟出现频率』，不是现实概率，也不是预测。") +
      " · 运行编号 " + (DATA.run_id || RUN_ID);
  }

  function choiceTag(letter, choiceText) {
    var wrap = el("span", "choice-option");
    var chip = el("span", "chip chip-" + letter.toLowerCase());
    chip.appendChild(dot("dot-" + letter.toLowerCase()));
    chip.appendChild(el("span", null, letter));
    wrap.appendChild(chip);
    wrap.appendChild(el("span", "choice-text", choiceText || "—"));
    return wrap;
  }

  /* ---------------- 01 overview ---------------- */

  function renderOverview() {
    var legend = $("overview-legend");
    legend.textContent = "";
    var i1 = el("span", "item"); i1.appendChild(dot("dot-a")); i1.appendChild(el("span", null, "选择 A"));
    var i2 = el("span", "item"); i2.appendChild(dot("dot-b")); i2.appendChild(el("span", null, "选择 B"));
    legend.appendChild(i1); legend.appendChild(i2);

    var grid = $("overview-grid");
    grid.textContent = "";
    ["A", "B"].forEach(function (L) {
      var cs = (DATA.choice_summaries || {})[L];
      if (cs) grid.appendChild(overviewCard(L, cs));
    });
    renderDecisionResult();
  }

  function overallScore(cs) {
    if (!cs || !cs.num_lives) return null;
    return weightedScore(SCORE_ROWS.map(function (r) { return cs[r.key]; }));
  }

  function renderDecisionResult() {
    var wrap = $("decision-result");
    var summaries = DATA.choice_summaries || {};
    if (!summaries.A || !summaries.B) { wrap.style.display = "none"; return; }

    var a = overallScore(summaries.A);
    var b = overallScore(summaries.B);
    if (a === null || b === null) { wrap.style.display = "none"; return; }
    var diff = Math.round(Math.abs(a - b) * 10) / 10;
    var winner = a >= b ? "A" : "B";
    var title = diff < 1 ? "两种选择的综合表现非常接近" : "本次模拟更倾向选择 " + winner;
    var strength = diff < 1 ? "基本持平" : diff < 4 ? "轻微优势" : diff < 8 ? "中等优势" : "明显优势";

    wrap.textContent = "";
    var badge = el("span", "decision-badge", diff < 1 ? "≈ 接近" : "✦ 最终倾向");
    var content = el("div", "decision-copy");
    content.appendChild(el("h3", null, title));
    content.appendChild(el("p", "decision-scores", "A " + fmt(a) + " 分 · B " + fmt(b) + " 分 · " + strength + (diff >= 1 ? " " + fmt(diff) + " 分" : "")));
    content.appendChild(el("p", "decision-note", "综合分按当前偏好加权（默认等权），后悔以 100−后悔分计入；仅用于本次模拟内比较。"));
    wrap.appendChild(badge);
    wrap.appendChild(content);
    wrap.style.display = "flex";
  }

  function overviewCard(letter, cs) {
    var lc = letter.toLowerCase();
    var card = el("section", "card choice-card card-" + lc);

    var head = el("div", "choice-card-head");
    var identity = el("div", "choice-card-identity");
    var titleLine = el("div", "choice-card-title");
    var chip = el("span", "chip chip-" + lc); chip.appendChild(dot("dot-" + lc));
    chip.appendChild(el("span", null, "选择 " + letter));
    titleLine.appendChild(chip);
    titleLine.appendChild(el("span", "choice-text", cs.choice_text || "—"));
    identity.appendChild(titleLine);
    identity.appendChild(el("span", "count", (cs.num_lives != null ? cs.num_lives : "—") + " 条模拟人生"));
    head.appendChild(identity);
    var score = el("div", "overall-score overall-score-" + lc);
    score.appendChild(el("span", "label", "综合分"));
    score.appendChild(el("strong", null, fmt(overallScore(cs))));
    score.appendChild(el("span", "unit", "/ 100"));
    head.appendChild(score);
    card.appendChild(head);

    SCORE_ROWS.forEach(function (row) {
      var v = cs[row.key];
      var r = el("div", "stat-row");
      var top = el("div", "stat-top");
      top.appendChild(el("span", "stat-label", row.label));
      top.appendChild(el("span", "stat-value", fmt(v)));
      var meter = el("div", "meter");
      var fill = el("div", "meter-fill meter-" + lc);
      fill.style.width = clamp100(v) + "%";
      meter.appendChild(fill);
      r.appendChild(top); r.appendChild(meter);
      card.appendChild(r);
    });

    card.appendChild(el("p", "list-caption", "常见风险"));
    var risks = el("ul", "risk-list");
    (cs.common_risks && cs.common_risks.length ? cs.common_risks : ["（本次模拟未总结出明显风险）"]).forEach(function (t) {
      var li = el("li");
      li.appendChild(el("span", "icon", "⚠ 风险"));
      li.appendChild(el("span", null, t));
      risks.appendChild(li);
    });
    card.appendChild(risks);

    card.appendChild(el("p", "list-caption", "常见机会"));
    var opps = el("ul", "opp-list");
    (cs.common_opportunities && cs.common_opportunities.length ? cs.common_opportunities : ["（本次模拟未总结出明显机会）"]).forEach(function (t) {
      var li = el("li");
      li.appendChild(el("span", "icon", "✦ 机会"));
      li.appendChild(el("span", null, t));
      opps.appendChild(li);
    });
    card.appendChild(opps);
    return card;
  }

  /* ---------------- 02 matched worlds ---------------- */

  function renderMatched() {
    var mc = DATA.matched_comparison;
    var wrap = $("matched-metrics");
    wrap.textContent = "";
    if (!mc || !mc.metrics) { $("matched-intro").textContent = "本次模拟没有生成共享世界对比。"; return; }

    var uniCount = (typeof mc.universe_count === "number") ? mc.universe_count : DATA.request.num_lives;
    $("matched-intro").textContent = "在 " + uniCount + " 个共享外部世界中（每个世界同时模拟了 A 与 B 两种选择）：";

    MATCH_ORDER.forEach(function (k) {
      var m = mc.metrics[k];
      if (!m) return;
      var row = el("div", "match-row");
      row.appendChild(el("span", "m-label", m.label || k));
      var right = el("div");
      var a = m.a_better || 0, b = m.b_better || 0, c = m.close || 0;
      var bar = el("div", "stack-bar");
      bar.setAttribute("role", "img");
      bar.setAttribute("aria-label", (m.label || k) + "：A 更好 " + a + "，相近 " + c + "，B 更好 " + b);
      if (a > 0) { var sa = el("span", "seg seg-a"); sa.style.flex = String(a); bar.appendChild(sa); }
      if (c > 0) { var sc = el("span", "seg seg-n"); sc.style.flex = String(c); bar.appendChild(sc); }
      if (b > 0) { var sb = el("span", "seg seg-b"); sb.style.flex = String(b); bar.appendChild(sb); }
      if (a + b + c === 0) bar.style.background = "var(--gridline)";
      right.appendChild(bar);

      var cap = el("div", "match-caption");
      var c1 = el("span", "item"); c1.appendChild(dot("dot-a")); c1.appendChild(el("span", null, "A 更好 " + a));
      var c2 = el("span", "item"); c2.appendChild(dot("dot-n")); c2.appendChild(el("span", null, "相近 " + c));
      var c3 = el("span", "item"); c3.appendChild(dot("dot-b")); c3.appendChild(el("span", null, "B 更好 " + b));
      cap.appendChild(c1); cap.appendChild(c2); cap.appendChild(c3);
      right.appendChild(cap);
      row.appendChild(right);
      wrap.appendChild(row);
    });

    var dw = $("divergence-wrap");
    dw.textContent = "";
    if (mc.divergence_insight) {
      var callout = el("div", "callout");
      callout.appendChild(el("span", "cap", "✦ 最大分歧点"));
      callout.appendChild(el("span", null, mc.divergence_insight));
      dw.appendChild(callout);
    }

    var ew = $("examples-wrap");
    ew.textContent = "";
    (mc.examples || []).forEach(function (ex) {
      var card = el("div", "card example-card");
      card.appendChild(el("p", "meta", "宇宙 #" + ex.universe_id + (ex.macro_environment ? " · " + ex.macro_environment : "")));
      if (ex.title) card.appendChild(el("h3", null, ex.title));
      card.appendChild(el("p", null, ex.narrative || ""));
      ew.appendChild(card);
    });
  }

  /* ---------------- 03 clusters ---------------- */

  function renderClusters() {
    var grid = $("cluster-grid");
    grid.textContent = "";
    ["A", "B"].forEach(function (L) {
      var cs = (DATA.choice_summaries || {})[L];
      var col = el("div");
      var head = el("div", "cluster-col-head");
      var chip = el("span", "chip chip-" + L.toLowerCase());
      chip.appendChild(dot("dot-" + L.toLowerCase()));
      chip.appendChild(el("span", null, "选择 " + L));
      head.appendChild(chip);
      head.appendChild(el("span", "choice-text", cs ? cs.choice_text : "—"));
      head.appendChild(el("span", "count", "共 " + (cs && cs.num_lives != null ? cs.num_lives : "—") + " 个模拟世界"));
      col.appendChild(head);

      var clusters = (cs && Array.isArray(cs.clusters)) ? cs.clusters : [];
      if (!clusters.length) {
        col.appendChild(el("p", "muted", "本次模拟没有总结出明显的聚类路径。"));
      } else {
        clusters.forEach(function (c) { col.appendChild(clusterCard(c, L, cs)); });
      }
      grid.appendChild(col);
    });
  }

  function clusterCard(c, letter, cs) {
    var lc = letter.toLowerCase();
    var card = el("div", "card cluster-card");
    card.appendChild(el("span", "name", c.name || "未命名路径"));

    var count = Array.isArray(c.trajectory_ids) ? c.trajectory_ids.length : 0;
    /* 分母用该选择实际模拟的世界数（cs.num_lives），而不是请求值 */
    var n = (cs && typeof cs.num_lives === "number" && cs.num_lives > 0) ? cs.num_lives : count;
    var meta = el("div", "cluster-meta");
    var share = el("div", "cluster-share");
    var fill = el("div", "fill meter-" + lc);
    fill.style.width = clamp100(n ? count / n * 100 : 0) + "%";
    share.appendChild(fill);
    meta.appendChild(share);
    meta.appendChild(el("span", "cluster-count", count + " / " + n + " 个模拟世界"));
    card.appendChild(meta);

    if (c.description) card.appendChild(el("p", null, c.description));
    if (c.common_pattern) card.appendChild(kvLine("常见模式", c.common_pattern, ""));
    if (c.key_risk) card.appendChild(kvLine("⚠ 主要风险", c.key_risk, "kv-risk"));
    if (c.key_opportunity) card.appendChild(kvLine("✦ 关键机会", c.key_opportunity, "kv-opp"));

    var rep = trajMap.get(c.representative_trajectory_id) ||
      (count > 0 ? trajMap.get(c.trajectory_ids[0]) : null);
    if (rep && Array.isArray(rep.years) && rep.years.length) {
      var tl = el("div", "mini-timeline");
      pickEvenly(rep.years, 5).forEach(function (y) {
        var row = el("div", "row");
        row.appendChild(el("span", "yr", String((DATA.start_year || 0) + (y.year || 1) - 1)));
        row.appendChild(el("span", "ev", y.major_event || "—"));
        tl.appendChild(row);
      });
      card.appendChild(tl);
      var btn = el("button", "btn", "查看这条人生 →");
      btn.type = "button";
      btn.dataset.traj = rep.id;
      card.appendChild(btn);
    }
    return card;
  }

  function kvLine(k, v, cls) {
    var p = el("p", "kv-line " + (cls || ""));
    p.appendChild(el("span", "k", k + "："));
    p.appendChild(el("span", null, v));
    return p;
  }

  function pickEvenly(arr, n) {
    if (arr.length <= n) return arr;
    var out = [];
    for (var i = 0; i < n; i++) {
      var idx = Math.round(i * (arr.length - 1) / (n - 1));
      if (out.indexOf(arr[idx]) === -1) out.push(arr[idx]);
    }
    return out;
  }

  /* ---------------- 04 insight ---------------- */

  function renderInsight() {
    var ins = DATA.insight || {};
    var items = [
      ["两个选择最主要的结构性区别", ins.structural_difference],
      ["真正决定结果的因素", ins.deciding_factors],
      ["多数世界里不重要的因素", ins.unimportant_factors],
      ["什么偏好的人更适合 A", ins.who_fits_a],
      ["什么偏好的人更适合 B", ins.who_fits_b],
      ["最大风险", ins.biggest_risk],
      ["最值得进一步确认的信息", ins.info_to_confirm]
    ];
    var grid = $("insight-grid");
    grid.textContent = "";
    items.forEach(function (it, i) {
      var card = el("div", "card insight-card");
      card.appendChild(el("span", "idx", String(i + 1).padStart(2, "0")));
      card.appendChild(el("p", "q", it[0]));
      card.appendChild(el("p", "a", it[1] || "—"));
      grid.appendChild(card);
    });

    var st = DATA.stats || {};
    var parts = ["共 " + (st.llm_calls != null ? st.llm_calls : "—") + " 次模型调用",
      "重生成 " + (st.regenerations != null ? st.regenerations : "—") + " 条",
      "用时 " + fmt(st.duration_seconds) + " s"];
    if (st.failed_trajectories > 0) parts.push("低质量轨迹 " + st.failed_trajectories + " 条");
    $("stats-line").textContent = parts.join(" · ");
  }

  /* ---------------- 05 notable lives ---------------- */

  function renderNotable() {
    var grid = $("notable-grid");
    grid.textContent = "";
    ["A", "B"].forEach(function (L) {
      var cs = (DATA.choice_summaries || {})[L];
      if (!cs) return;
      grid.appendChild(notableCard(L, "最典型人生", cs.most_typical_trajectory_id));
      grid.appendChild(notableCard(L, "最意外人生", cs.most_surprising_trajectory_id));
    });
  }

  function notableCard(letter, kind, trajId) {
    var t = trajId ? trajMap.get(trajId) : null;
    if (!t) return el("span");

    var lc = letter.toLowerCase();
    var card = el("button", "card notable-card");
    card.type = "button";
    card.dataset.traj = t.id;

    var head = el("div", "badge-row");
    var chip = el("span", "chip chip-" + lc);
    chip.appendChild(dot("dot-" + lc));
    chip.appendChild(el("span", null, letter));
    head.appendChild(chip);
    head.appendChild(el("span", "choice-text", "选择 " + letter + " · " + kind));
    card.appendChild(head);

    card.appendChild(el("p", null, t.summary || "（这条轨迹没有摘要）"));

    var chips = el("div", "badge-row");
    chips.style.marginTop = "10px";
    TRAJ_SCORES.forEach(function (s) {
      var sc = el("span", "score-chip");
      var lbl = s.key === "regret_score" ? "后悔" : s.label;
      sc.appendChild(el("span", null, lbl + " "));
      sc.appendChild(el("b", null, fmt(t[s.key])));
      chips.appendChild(sc);
    });
    card.appendChild(chips);
    return card;
  }

  /* ---------------- 06 all trajectories ---------------- */

  function renderTable() {
    var wrap = $("traj-table-wrap");
    wrap.textContent = "";
    var list = (DATA.trajectories || []).slice().sort(function (x, y) {
      if (x.choice !== y.choice) return x.choice === "A" ? -1 : 1;
      return (x.universe_id || 0) - (y.universe_id || 0);
    });
    $("traj-count").textContent = String(list.length);

    var table = el("table", "traj");
    var thead = el("thead");
    var hr = el("tr");
    ["ID", "宇宙", "聚类", "职业", "财务", "关系", "满意度", "后悔", "摘要"].forEach(function (h) {
      hr.appendChild(el("th", null, h));
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    var tbody = el("tbody");
    list.forEach(function (t) {
      var tr = el("tr");
      tr.tabIndex = 0;
      tr.dataset.traj = t.id;

      var idTd = el("td");
      var idDot = el("span", "c-dot " + (lower(t.choice) === "a" ? "dot-a" : "dot-b"));
      idDot.setAttribute("aria-hidden", "true");
      idTd.appendChild(idDot);
      idTd.appendChild(el("span", null, t.id));
      tr.appendChild(idTd);

      tr.appendChild(el("td", null, "#" + (t.universe_id != null ? t.universe_id : "—")));
      tr.appendChild(el("td", null, t.cluster_name || "—"));
      tr.appendChild(el("td", null, fmt(t.final_career_score)));
      tr.appendChild(el("td", null, fmt(t.final_finance_score)));
      tr.appendChild(el("td", null, fmt(t.final_relationship_score)));
      tr.appendChild(el("td", null, fmt(t.final_wellbeing_score)));
      tr.appendChild(el("td", null, fmt(t.regret_score)));

      var summary = t.summary || "";
      var td = el("td", "summary-cell", summary.length > 40 ? summary.slice(0, 40) + "…" : summary);
      td.title = summary;
      tr.appendChild(td);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
  }

  /* ---------------- modal ---------------- */

  var modal = $("modal");

  function openModal(trajId) {
    var t = trajMap.get(trajId);
    if (!t) return;
    activeTraj = t;
    lastFocused = document.activeElement;

    var lc = lower(t.choice);
    var title = $("modal-title");
    title.textContent = "";
    title.appendChild(el("span", null, "选择 " + (t.choice || "?")));
    title.appendChild(el("span", "muted", " · 宇宙 #" + (t.universe_id != null ? t.universe_id : "—") +
      (t.cluster_name ? " · " + t.cluster_name : "")));

    var badge = $("critic-badge");
    var cr = t.critic;
    if (cr && cr.checked === false) {
      /* Critic 调用失败、从未真正检查过：绝不能显示"质量检查通过" */
      badge.style.display = ""; badge.className = "critic-badge bad";
      badge.textContent = "⚠ 未完成质量检查（评审调用失败，保留数据）";
    }
    else if (cr && cr.accepted === true) { badge.style.display = ""; badge.className = "critic-badge ok"; badge.textContent = "✓ 质量检查通过"; }
    else if (cr && cr.accepted === false) { badge.style.display = ""; badge.className = "critic-badge bad"; badge.textContent = "⚠ 低质量轨迹（未通过一致性检查）"; }
    else badge.style.display = "none";

    var regBadge = $("modal-head-badges");
    regBadge.textContent = "";
    if (typeof t.regenerated === "number" && t.regenerated > 0) {
      var rb = el("span", "critic-badge");
      rb.style.color = "var(--muted)";
      rb.style.borderColor = "var(--hairline)";
      rb.textContent = "↗ 已重生成 " + t.regenerated + " 次";
      regBadge.appendChild(rb);
    }
    var problems = (cr && Array.isArray(cr.problems)) ? cr.problems.filter(function (p) { return p; }) : [];
    if (problems.length) {
      var pb = el("span", "critic-badge");
      pb.style.color = "var(--warn)";
      pb.style.borderColor = "rgba(250, 178, 25, 0.5)";
      pb.textContent = "质量提示 " + problems.length + " 条";
      pb.title = problems.join("\n");
      regBadge.appendChild(pb);
    }

    renderModalScores(t);
    renderModalTimeline(t);
    renderUniverseBox(t);

    var finalYear = (DATA.start_year || 0) + (DATA.request.years || 0) - 1;
    var chatButton = $("modal-chat-btn");
    if (window.__100_LIVES_STANDALONE__) {
      chatButton.textContent = "与未来对话需启动本地服务";
      chatButton.disabled = true;
      chatButton.title = "这份离线 HTML 可以浏览完整报告；模型对话需要通过本地服务打开结果页。";
    } else {
      chatButton.textContent = "和 " + finalYear + " 年的这个自己聊聊 ✦";
      chatButton.disabled = false;
      chatButton.title = "";
    }

    showView("timeline");
    modal.classList.add("open");
    document.body.style.overflow = "hidden";
    $("modal-close").focus();
  }

  function closeModal() {
    modal.classList.remove("open");
    document.body.style.overflow = "";
    chatBusy = false;
    activeTraj = null;
    if (lastFocused && typeof lastFocused.focus === "function") lastFocused.focus();
  }

  function renderModalScores(t) {
    var lc = lower(t.choice);
    var row = $("modal-scores");
    row.textContent = "";
    TRAJ_SCORES.forEach(function (s) {
      var cell = el("div", "score-cell");
      var top = el("div", "score-cell-top");
      top.appendChild(el("span", "lbl", s.key === "regret_score" ? "后悔（低=好）" : s.label));
      top.appendChild(el("span", "val", fmt(t[s.key])));
      var meter = el("div", "meter");
      var fill = el("div", "meter-fill meter-" + lc);
      fill.style.width = clamp100(t[s.key]) + "%";
      meter.appendChild(fill);
      cell.appendChild(top);
      cell.appendChild(meter);
      row.appendChild(cell);
    });
  }

  function renderModalTimeline(t) {
    var lc = lower(t.choice);
    var list = $("modal-timeline");
    list.textContent = "";
    (t.years || []).forEach(function (y) {
      var block = el("div", "vt-year" + (lc === "b" ? " b" : ""));
      var head = el("div");
      head.appendChild(el("span", "yr", String((DATA.start_year || 0) + (y.year || 1) - 1)));
      if (y.location) head.appendChild(el("span", "loc-chip", y.location));
      block.appendChild(head);

      if (y.major_event) {
        var m = el("p", "major");
        m.appendChild(el("span", "k", "重大事件 · "));
        m.appendChild(el("span", null, y.major_event));
        block.appendChild(m);
      }
      [["职业", y.career], ["财务", y.finance], ["关系", y.relationship], ["状态", y.wellbeing]].forEach(function (pair) {
        if (!pair[1]) return;
        var p = el("p", "dim");
        p.appendChild(el("span", "k", pair[0]));
        p.appendChild(el("span", null, pair[1]));
        block.appendChild(p);
      });
      if (y.decision) {
        var d = el("p", "decision");
        d.appendChild(el("span", "k", "这一年你决定："));
        d.appendChild(el("span", null, y.decision));
        block.appendChild(d);
      }
      list.appendChild(block);
    });
  }

  function renderUniverseBox(t) {
    var u = universeMap.get(t.universe_id);
    var box = $("universe-box");
    var inner = $("universe-inner");
    inner.textContent = "";
    if (!u) { box.style.display = "none"; return; }
    box.style.display = "";
    box.open = false;
    [["宏观环境", u.macro_environment], ["职业冲击", u.career_shock], ["财务冲击", u.financial_shock],
     ["关系冲击", u.relationship_shock], ["出现的机会", u.opportunity], ["随机事件", u.random_event]]
      .forEach(function (pair) {
        var p = el("div", "kv");
        p.appendChild(el("span", "k", pair[0]));
        p.appendChild(el("span", null, pair[1] || "—"));
        inner.appendChild(p);
      });
  }

  function showView(view) {
    $("view-timeline").style.display = view === "timeline" ? "" : "none";
    $("view-chat").style.display = view === "chat" ? "" : "none";
    $("modal-back").style.display = view === "chat" ? "" : "none";
    if (view === "chat") {
      var s = chatSession(activeTraj);
      renderChat(s);
      autoGrow();
      $("chat-input").focus();
    }
  }

  /* ---------------- chat with future self ---------------- */

  function chatSession(t) {
    var s = chatStore.get(t.id);
    if (!s) {
      s = { turns: [], futureYear: (DATA.start_year || 0) + (DATA.request.years || 0) - 1 };
      chatStore.set(t.id, s);
    }
    return s;
  }

  function renderChat(s) {
    var log = $("chat-log");
    log.textContent = "";
    $("chat-head").textContent = "与 " + s.futureYear + " 的你对话（来自这条时间线的未来）";

    if (!s.turns.length) {
      $("chat-suggest").style.display = "";
    } else {
      $("chat-suggest").style.display = "none";
      s.turns.forEach(function (m) {
        if (m.role === "error") log.appendChild(errorChip(m.content));
        else log.appendChild(bubble(m.role, m.content, s));
      });
      scrollLog();
    }
  }

  function bubble(role, content, s) {
    var msg = el("div", "chat-msg " + role);
    if (role === "user") {
      msg.appendChild(el("div", "bubble", content));
    } else {
      var av = el("span", "avatar", String(s.futureYear));
      av.setAttribute("aria-hidden", "true");
      var col = el("div");
      col.appendChild(el("div", "who", s.futureYear + " 的你"));
      col.appendChild(el("div", "bubble", content));
      msg.appendChild(av);
      msg.appendChild(col);
    }
    return msg;
  }

  function errorChip(msgText) {
    var chip = el("div", "chat-msg");
    chip.appendChild(el("span", "err-chip", "⚠ " + msgText));
    return chip;
  }

  function typingBubble(s) {
    var msg = el("div", "chat-msg");
    var av = el("span", "avatar", String(s.futureYear));
    av.setAttribute("aria-hidden", "true");
    var t = el("div", "typing");
    t.appendChild(el("span")); t.appendChild(el("span")); t.appendChild(el("span"));
    msg.appendChild(av);
    msg.appendChild(t);
    return msg;
  }

  function scrollLog() {
    /* 真正的滚动容器是 modal-body（#view-chat），而不是内部的 chat-log。 */
    var viewport = $("view-chat");
    window.requestAnimationFrame(function () {
      viewport.scrollTop = viewport.scrollHeight;
    });
  }

  async function sendChat(preset) {
    if (!activeTraj || chatBusy) return;
    var input = $("chat-input");
    var text = (preset != null ? String(preset) : input.value).trim();
    if (!text) return;

    var s = chatSession(activeTraj);
    var log = $("chat-log");
    $("chat-suggest").style.display = "none";

    /* 后端上限 2000 字：超长时提示而不是发出必然失败的消息 */
    if (text.length > 2000) {
      s.turns.push({ role: "error", content: "消息太长（最多 2000 字），请精简后再发" });
      log.appendChild(errorChip("消息太长（最多 2000 字），请精简后再发"));
      scrollLog();
      input.focus();
      return;
    }

    s.turns.push({ role: "user", content: text });
    log.appendChild(bubble("user", text, s));
    input.value = "";
    autoGrow();

    var typing = typingBubble(s);
    log.appendChild(typing);
    scrollLog();

    chatBusy = true;
    $("chat-send").disabled = true;
    try {
      /* strict alternation: only completed user→assistant pairs, last 5 pairs (10 turns).
         后端对每条历史内容上限 4000 字：重发的历史在此截断，不阻塞对话 */
      var history = [];
      var pendingUser = null;
      s.turns.forEach(function (m) {
        if (m.role === "user") pendingUser = m.content;
        else if (m.role === "assistant" && pendingUser !== null) {
          history.push({ role: "user", content: pendingUser });
          history.push({ role: "assistant", content: m.content.length > 4000 ? m.content.slice(0, 4000) : m.content });
          pendingUser = null;
        }
      });
      history = history.slice(-10);

      var res = await fetch("/api/future-self-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_id: RUN_ID,
          trajectory_id: activeTraj.id,
          message: text,
          history: history
        })
      });
      if (!res.ok) {
        var detail = "";
        try {
          var j = await res.json();
          if (j && typeof j.detail === "string") detail = j.detail;
          else if (j && Array.isArray(j.detail)) detail = j.detail.map(function (d) {
            return d && typeof d.msg === "string" ? d.msg : String(d);
          }).join("；");
        } catch (e) { detail = ""; }
        throw new Error(detail || ("HTTP " + res.status));
      }
      var data = await res.json();
      if (!data || typeof data.reply !== "string") throw new Error("返回内容异常");
      if (typeof data.future_year === "number") s.futureYear = data.future_year;
      typing.remove();
      s.turns.push({ role: "assistant", content: data.reply });
      log.appendChild(bubble("assistant", data.reply, s));
    } catch (e) {
      typing.remove();
      s.turns.push({ role: "error", content: "发送失败：" + (e && e.message ? e.message : "未知错误") + "（再发送一次即可重试）" });
      log.appendChild(errorChip("发送失败：" + (e && e.message ? e.message : "未知错误") + "（再发送一次即可重试）"));
    }
    chatBusy = false;
    $("chat-send").disabled = false;
    scrollLog();
    input.focus();
  }

  function autoGrow() {
    var ta = $("chat-input");
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 96) + "px";
  }

  /* ---------------- visual story / local-only exploration ---------------- */

  function weightedScore(values) {
    if (values.some(function (v) { return typeof v !== "number" || !isFinite(v); })) return null;
    var sum = weights.reduce(function (a, b) { return a + b; }, 0);
    if (!sum) return null;
    return Math.round(values.reduce(function (total, v, i) {
      return total + (i === 4 ? 100 - v : v) * weights[i];
    }, 0) / sum * 10) / 10;
  }

  function pairs() {
    var worlds = new Map();
    (DATA.trajectories || []).forEach(function (t) {
      if (!worlds.has(t.universe_id)) worlds.set(t.universe_id, { id: t.universe_id });
      worlds.get(t.universe_id)[t.choice] = t;
    });
    (DATA.universes || []).forEach(function (u) { if (!worlds.has(u.id)) worlds.set(u.id, { id: u.id }); });
    return Array.from(worlds.values()).sort(function (a, b) { return a.id - b.id; });
  }

  function trajectoryScore(t, metric) {
    if (!t) return null;
    var values = TRAJ_SCORES.map(function (s) { return t[s.key]; });
    if (metric < 0) return weightedScore(values);
    var v = values[metric];
    return typeof v === "number" && isFinite(v) ? (metric === 4 ? 100 - v : v) : null;
  }

  function outcome(pair, metric) {
    var a = trajectoryScore(pair.A, metric), b = trajectoryScore(pair.B, metric);
    if (a === null || b === null) return "missing";
    return Math.abs(a - b) <= 3 ? "close" : a > b ? "A" : "B";
  }

  function counts(metric) {
    var result = { A: 0, B: 0, close: 0, missing: 0 };
    pairs().forEach(function (p) { result[outcome(p, metric)]++; });
    return result;
  }

  function storyTitle(parent, eyebrow, title, note) {
    parent.appendChild(el("p", "story-eyebrow", eyebrow));
    parent.appendChild(el("h2", "story-title", title));
    if (note) parent.appendChild(el("p", "muted", note));
  }

  function scoreTiles(parent) {
    var row = el("div", "story-scores");
    ["A", "B"].forEach(function (letter) {
      var cs = (DATA.choice_summaries || {})[letter];
      var tile = el("div", "story-score score-" + letter);
      tile.appendChild(el("span", null, "选择 " + letter));
      tile.appendChild(el("strong", null, fmt(overallScore(cs))));
      tile.appendChild(el("span", null, "/ 100 · 当前偏好综合分"));
      tile.appendChild(el("p", null, cs ? cs.choice_text : "暂无数据"));
      row.appendChild(tile);
    });
    parent.appendChild(row);
  }

  function preferenceLabel() {
    var total = weights.reduce(function (a, b) { return a + b; }, 0);
    return weights.map(function (v, i) { return TRAJ_SCORES[i].label + " " + Math.round(v / total * 100) + "%"; }).join(" · ");
  }

  function renderStory() {
    [2, 1, 3].forEach(renderExplore);
  }

  function renderExplore(section) {
    var host = $("explore-" + section);
    host.textContent = "";
    var panel = el("div", "card story-panel");
    host.appendChild(panel);
    if (section === 1) {
      storyTitle(panel, "EVERY WORLD COUNTS", pairs().length + " 个世界，" + (DATA.trajectories || []).length + " 条人生。", "每格对应同一个外部世界，左 A / 右 B。点击查看两条轨迹；相差不超过 3 分视为接近。");
      var filters = el("div", "matrix-filters");
      ["综合"].concat(TRAJ_SCORES.map(function (s) { return s.label; })).forEach(function (label, index) {
        var button = el("button", "btn", label); button.type = "button";
        button.setAttribute("aria-pressed", String(matrixMetric === index-1));
        button.addEventListener("click", function () { matrixMetric = index-1; renderExplore(1); }); filters.appendChild(button);
      });
      panel.appendChild(filters);
      var c = counts(matrixMetric);
      panel.appendChild(el("p", "matrix-summary", "A 更好 " + c.A + " · B 更好 " + c.B + " · 接近 " + c.close + " · 未配对/缺数据 " + c.missing));
      var grid = el("div", "world-matrix");
      pairs().forEach(function (pair) {
        var result = outcome(pair, matrixMetric);
        var label = result === "close" ? "接近" : result === "missing" ? "缺数据" : result + " 更好";
        var button = el("button", "world-cell world-" + result);
        button.type = "button"; button.setAttribute("aria-label", "世界 " + pair.id + "，" + label);
        button.setAttribute("aria-pressed", String(selectedWorld === pair.id));
        button.appendChild(el("span", "world-dots", "● ─ ●"));
        button.appendChild(el("span", null, "#" + pair.id));
        button.appendChild(el("small", null, label));
        button.addEventListener("click", function () { selectedWorld = pair.id; renderPairDetail(pair); renderExplore(3); grid.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); }); });
        grid.appendChild(button);
      });
      panel.appendChild(grid); panel.appendChild(el("div", "pair-detail", "点击一个世界，展开它的两种人生。"));
      var chosen = pairs().find(function (p) { return p.id === selectedWorld; }); if (chosen) renderPairDetail(chosen);
    } else if (section === 2) {
      storyTitle(panel, "WHAT MATTERS TO YOU", "你在意什么，答案就向哪里移动。", "拖动重要程度，五项会自动换算成权重。仅重新计算已有结果，不重新模拟人生。");
      var controls = el("div", "weight-controls");
      TRAJ_SCORES.forEach(function (s, i) {
        var label = el("label", "weight-row"); label.appendChild(el("span", null, s.label));
        var input = el("input"); input.type = "range"; input.min = "0"; input.max = "100"; input.value = weights[i]; input.setAttribute("aria-label", s.label + "重要程度");
        var output = el("output"); output.id = "weight-value-" + i;
        input.addEventListener("input", function () {
          var previous = weights[i]; weights[i] = Number(input.value);
          if (!weights.some(function (v) { return v > 0; })) { weights[i] = previous; input.value = previous; }
          updatePreferenceResults();
        });
        label.appendChild(input); label.appendChild(output); controls.appendChild(label);
      });
      panel.appendChild(controls);
      var reset = el("button", "btn", "恢复等权"); reset.type = "button"; reset.addEventListener("click", function () { weights = [20,20,20,20,20]; renderExplore(2); }); panel.appendChild(reset);
      panel.appendChild(el("div", "preference-results")); updatePreferenceResults();
    } else if (section === 3) {
      storyTitle(panel, "TWO ROADS AHEAD", "从今天出发，走进两条人生。", "默认展示同一世界的 A/B 轨迹；节点来自已生成的年度事件，可展开细读。");
      var complete = pairs().filter(function (p) { return p.A && p.B; });
      if (!complete.length) { panel.appendChild(el("p", null, "暂无完整配对轨迹。")); return; }
      var current = complete.find(function (p) { return p.id === selectedWorld; }) || complete[0];
      var select = el("select"); select.setAttribute("aria-label", "选择人生路线的世界");
      complete.forEach(function (p) { var option = el("option", null, "世界 #" + p.id); option.value = p.id; select.appendChild(option); }); select.value = current.id;
      select.addEventListener("change", function () { selectedWorld = Number(select.value); renderExplore(3); renderExplore(1); }); panel.appendChild(select);
      var river = el("div", "life-river");
      ["A", "B"].forEach(function (letter) {
        var lane = el("div", "river-lane river-" + letter); lane.appendChild(el("h3", null, "选择 " + letter));
        (current[letter].years || []).forEach(function (year) {
          var node = el("details", "river-node");
          node.appendChild(el("summary", null, ((DATA.start_year || 0) + year.year - 1) + " · " + (year.major_event || "平凡的一年")));
          [["地点",year.location],["职业",year.career],["财务",year.finance],["关系",year.relationship],["状态",year.wellbeing],["决定",year.decision]].forEach(function (item) { if(item[1]) node.appendChild(el("p", null, item[0]+"："+item[1])); }); lane.appendChild(node);
        });
        var inspect = el("button", "btn", "走近这个未来的自己 →"); inspect.type="button"; inspect.dataset.traj=current[letter].id; lane.appendChild(inspect); river.appendChild(lane);
      }); panel.appendChild(river);
    }
  }

  function renderPairDetail(pair) {
    var host = document.querySelector(".pair-detail"); if (!host) return; host.textContent="";
    var u=universeMap.get(pair.id); host.appendChild(el("h3",null,"世界 #"+pair.id));
    host.appendChild(el("p","muted",u ? u.macro_environment : "外部条件未记录"));
    ["A","B"].forEach(function(letter){ var t=pair[letter]; var box=el("div","pair-line"); box.appendChild(el("strong",null,letter+" · "+fmt(trajectoryScore(t,matrixMetric))+" 分")); box.appendChild(el("p",null,t ? t.summary : "该轨迹未生成")); if(t){var b=el("button","btn","查看 "+letter+" 完整时间线"); b.type="button";b.dataset.traj=t.id;box.appendChild(b);}host.appendChild(box); });
    if(matrixMetric===4)host.appendChild(el("p","muted","这里显示 100−后悔分，越高代表越少后悔。"));
  }

  function updatePreferenceResults() {
    var total=weights.reduce(function(a,b){return a+b;},0);
    weights.forEach(function(v,i){$("weight-value-"+i).textContent=Math.round(v/total*100)+"%";});
    var host=document.querySelector(".preference-results");host.textContent="";scoreTiles(host);
    var c=counts(-1);host.appendChild(el("p",null,"同一世界配对：A 更好 "+c.A+" · B 更好 "+c.B+" · 接近 "+c.close));
    renderOverview();
    renderExplore(1);
  }

  function makePoster() {
    var canvas=document.createElement("canvas");canvas.width=1080;canvas.height=1440;
    var ctx=canvas.getContext("2d");ctx.fillStyle="#fff4dd";ctx.fillRect(0,0,1080,1440);
    function text(value,x,y,size,color){ctx.fillStyle=color||"#26201a";ctx.font="bold "+size+"px sans-serif";ctx.fillText(value,x,y);}
    function lines(value,x,y,width,size,max){
      ctx.font="bold "+size+"px sans-serif";var chunks=[],line="";
      Array.from(value).forEach(function(ch){if(ctx.measureText(line+ch).width>width){chunks.push(line);line=ch;}else line+=ch;});if(line)chunks.push(line);
      chunks.slice(0,max).forEach(function(line,i){if(i===max-1&&chunks.length>max)line=line.slice(0,-1)+"…";text(line,x,y+i*(size+12),size);});
    }
    text("100 LIVES ✦",64,100,42);text("我的平行人生",64,208,76);
    text(pairs().length+" 个模拟世界 · "+DATA.request.years+" 年后的可能",64,278,30);
    ["A","B"].forEach(function(letter,i){var x=64+i*490;ctx.fillStyle=i ? "#ffb08f":"#a5dcff";ctx.fillRect(x,344,458,380);ctx.strokeStyle="#26201a";ctx.lineWidth=4;ctx.strokeRect(x,344,458,380);text("选择 "+letter,x+28,402,32);text(fmt(overallScore((DATA.choice_summaries||{})[letter])),x+28,520,92);text("当前偏好综合分 / 100",x+28,570,22);lines(DATA.request[i ? "choice_b":"choice_a"],x+28,624,390,26,2);});
    var c=counts(-1);text("相同世界，两种选择",64,810,38);
    var n=c.A+c.B+c.close, x=64;
    [[c.A,"#a5dcff"],[c.close,"#d6c9a8"],[c.B,"#ff5c2b"]].forEach(function(item){var width=n ? 948*item[0]/n:0;ctx.fillStyle=item[1];ctx.fillRect(x,852,width,48);x+=width;});
    text("A 更好 "+c.A+"   ·   接近 "+c.close+"   ·   B 更好 "+c.B,64,960,30);
    text("有效配对 "+n+" · 缺数据 "+c.missing+" · 相差 ≤ 3 分视为接近",64,1008,23);
    lines(preferenceLabel(),64,1100,948,23,3);
    text("模拟出现频率 ≠ 现实概率",64,1300,30);
    text("分数仅用于模拟内比较。未来，仍由你来写。",64,1360,24);
    var url=canvas.toDataURL("image/png");$("poster-preview").src=url;$("poster-save").href=url;$("poster-save").download="100-lives-"+RUN_ID+".png";
    $("poster-status").textContent="可保存图片后分享，当前偏好已包含在海报中。";
    $("poster-dialog").showModal();
  }

  $("share-poster").addEventListener("click",makePoster);
  $("poster-close").addEventListener("click",function(){$("poster-dialog").close();});

  /* ---------------- events ---------------- */

  document.addEventListener("click", function (e) {
    var trigger = e.target.closest("[data-traj]");
    if (trigger) { openModal(trigger.dataset.traj); return; }
    var chipBtn = e.target.closest(".suggest-chip");
    if (chipBtn && activeTraj) { sendChat(chipBtn.dataset.q); return; }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") {
      var row = e.target.closest && e.target.closest("tr[data-traj]");
      if (row) { e.preventDefault(); openModal(row.dataset.traj); }
    }
    if (e.key === "Escape" && modal.classList.contains("open")) closeModal();
  });

  modal.addEventListener("mousedown", function (e) {
    if (e.target === modal) closeModal();
  });

  $("modal-close").addEventListener("click", closeModal);
  $("modal-chat-btn").addEventListener("click", function () { showView("chat"); });
  $("modal-back").addEventListener("click", function () { showView("timeline"); });

  $("chat-send").addEventListener("click", function () { sendChat(); });
  $("chat-input").addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });
  $("chat-input").addEventListener("input", autoGrow);
})();
