/* 100 LIVES — index page logic (vanilla JS, ES2020) */
"use strict";

(function () {
  var $ = function (id) { return document.getElementById(id); };

  var els = {
    form: $("simulate-form"),
    profile: $("profile"),
    charCount: $("char-count"),
    choiceA: $("choice-a"),
    choiceB: $("choice-b"),
    years: $("years"),
    numLives: $("num-lives"),
    fillSample: $("fill-sample"),
    submitBtn: $("submit-btn"),
    submitError: $("submit-error"),
    formSection: $("form-section"),
    progressSection: $("progress-section"),
    progressFill: $("progress-fill"),
    progressPct: $("progress-pct"),
    progressBar: $("progress-bar"),
    stepper: $("stepper"),
    statusMsg: $("status-msg"),
    statusDetail: $("status-detail"),
    retryNote: $("retry-note"),
    elapsed: $("elapsed"),
    progressError: $("progress-error")
  };

  var STAGES = ["universes", "simulation", "clustering", "comparison", "summary"];
  var runId = null;
  var pollTimer = null;
  var clockTimer = null;
  var startedAt = 0;
  var finished = false;

  /* ---------------- utils ---------------- */

  function text(el, s) { el.textContent = s != null ? String(s) : ""; }

  function showFieldError(which, msg) {
    var p = $("error-" + which);
    var field = $("field-" + which);
    if (p) { text(p, msg); p.classList.add("show"); }
    if (field) field.classList.add("has-error");
  }

  function clearFieldErrors() {
    ["profile", "choice-a", "choice-b"].forEach(function (k) {
      var p = $("error-" + k);
      var f = $("field-" + k);
      if (p) { text(p, ""); p.classList.remove("show"); }
      if (f) f.classList.remove("has-error");
    });
    hideBox(els.submitError);
  }

  function showBox(box, title, detail, hint, withBack) {
    box.style.display = "block";
    box.textContent = "";
    if (title) {
      var t = document.createElement("p");
      t.className = "alert-title";
      t.textContent = title;
      box.appendChild(t);
    }
    if (detail) {
      var d = document.createElement("p");
      d.textContent = detail;
      box.appendChild(d);
    }
    if (hint) {
      var h = document.createElement("p");
      h.className = "hint";
      h.textContent = hint;
      box.appendChild(h);
    }
    if (withBack) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn";
      btn.style.marginTop = "12px";
      btn.textContent = "返回修改";
      btn.addEventListener("click", backToForm);
      box.appendChild(btn);
    }
  }

  function hideBox(box) { box.style.display = "none"; box.textContent = ""; }

  function fmtClock(sec) {
    var m = Math.floor(sec / 60);
    var s = Math.floor(sec % 60);
    return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
  }

  /* ---------------- client validation ---------------- */

  function validate() {
    var ok = true;
    var profile = els.profile.value.trim();
    var a = els.choiceA.value.trim();
    var b = els.choiceB.value.trim();

    if (!profile) { showFieldError("profile", "请描述你现在的情况（至少 10 个字）。"); ok = false; }
    else if (profile.length < 10) { showFieldError("profile", "描述太短了，至少 10 个字（当前 " + profile.length + " 个字）。"); ok = false; }

    if (!a) { showFieldError("choice-a", "请填写选择 A。"); ok = false; }
    if (!b) { showFieldError("choice-b", "请填写选择 B。"); ok = false; }

    return ok;
  }

  /* ---------------- char counter ---------------- */

  function updateCharCount() {
    text(els.charCount, String(els.profile.value.length));
  }

  /* ---------------- sample ---------------- */

  var SAMPLE = {
    profile: "我 30 岁，在一家普通公司做运营专员，单身。最近在考虑要不要换一座城市发展。新机会薪资更高、团队方向更有意思，但意味着要离开熟悉的城市、朋友圈和现在的生活节奏。我在意职业成长和存款速度，也担心换城市的不确定性。目标是在 35 岁前找到可以长期深耕的方向。",
    choiceA: "留在现在的城市，继续当前工作",
    choiceB: "去另一座城市，接受新工作"
  };

  function fillSample() {
    els.profile.value = SAMPLE.profile;
    els.choiceA.value = SAMPLE.choiceA;
    els.choiceB.value = SAMPLE.choiceB;
    clearFieldErrors();
    updateCharCount();
    els.profile.focus();
  }

  /* ---------------- submit flow ---------------- */

  function onProgress(p) {
    var pct = Math.round(Math.max(0, Math.min(1, p || 0)) * 100);
    els.progressFill.style.width = pct + "%";
    text(els.progressPct, pct + "%");
    els.progressBar.setAttribute("aria-valuenow", String(pct));
  }

  function setStage(stage) {
    var idx = STAGES.indexOf(stage);
    var doneUpto = -1;
    if (stage === "done") doneUpto = STAGES.length;
    else if (idx >= 0) doneUpto = idx;

    var items = els.stepper.querySelectorAll("li");
    for (var i = 0; i < items.length; i++) {
      var li = items[i];
      li.classList.remove("active", "done");
      if (stage !== "failed" && stage !== "done" && i === idx) li.classList.add("active");
      if (stage === "done" || i < doneUpto) li.classList.add("done");
    }
  }

  function applyStatus(st) {
    if (finished) return;
    onProgress(typeof st.progress === "number" ? st.progress : 0);
    setStage(st.stage);

    text(els.statusMsg, st.message || "");
    var d = st.detail || {};
    var line = "";
    if (st.stage === "universes") {
      line = "已生成 " + (d.universes_done != null ? d.universes_done : 0) + " / " +
        (d.universes_total != null ? d.universes_total : "?") + " 个平行世界";
    } else if (st.stage === "simulation") {
      var total = d.total != null ? d.total : "?";
      var checkedTotal = (typeof total === "number") ? 2 * total : "?";
      line = "选择 A：" + (d.done_a != null ? d.done_a : 0) + "/" + total +
        " · 选择 B：" + (d.done_b != null ? d.done_b : 0) + "/" + total +
        " · 已检查 " + (d.checked != null ? d.checked : 0) + "/" + checkedTotal + " 条时间线";
    }
    text(els.statusDetail, line);

    if (st.stage === "done" || (typeof st.progress === "number" && st.progress >= 1)) {
      finish("done");
      window.location.replace("/result/" + encodeURIComponent(runId));
      return;
    }
    if (st.stage === "failed") {
      var msg = st.message || st.error || "模拟失败了。";
      var extra = st.error && st.error !== msg ? st.error : "";
      showBox(els.progressError, "模拟失败", msg, extra || null, true);
      finish("failed");
    }
  }

  function finish(reason) {
    finished = true;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    /* keep the clock running only when we land on an error screen */
    if (reason === "done" && clockTimer) { clearInterval(clockTimer); clockTimer = null; }
  }

  async function poll() {
    if (!runId || finished) return;
    try {
      var res = await fetch("/api/status/" + encodeURIComponent(runId));
      if (res.status === 404) {
        showBox(els.progressError, "未找到该运行", "服务器上没有这次模拟的记录，可能服务已重启。", null, true);
        finish("failed");
        return;
      }
      if (!res.ok) throw new Error("HTTP " + res.status);
      var st = await res.json();
      els.retryNote.classList.remove("show");
      applyStatus(st);
    } catch (e) {
      els.retryNote.classList.add("show");
    }
  }

  async function submitSimulation() {
    var payload = {
      profile: els.profile.value.trim(),
      choice_a: els.choiceA.value.trim(),
      choice_b: els.choiceB.value.trim(),
      years: parseInt(els.years.value, 10),
      num_lives: parseInt(els.numLives.value, 10)
    };
    try {
      var res = await fetch("/api/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) { await handleSimulateError(res); return; }
      var data = await res.json();
      if (!data || !data.run_id) throw new Error("bad response");
      runId = data.run_id;
      poll();
      pollTimer = setInterval(poll, 1000);
    } catch (e) {
      if (e && e.handled) return;
      backToForm();
      showBox(els.submitError, "无法连接服务器",
        "提交失败，请确认后端服务已在本机启动，然后重试。");
    }
  }

  async function handleSimulateError(res) {
    var body = null;
    try { body = await res.json(); } catch (e) { /* not JSON */ }
    var err = new Error("handled");
    err.handled = true;

    if (res.status === 422 && body && Array.isArray(body.detail)) {
      var mapped = 0;
      var unmapped = [];
      body.detail.forEach(function (item) {
        var field = item && item.loc && item.loc.length > 1 ? String(item.loc[1]) : "";
        var key = null;
        if (field === "profile") key = "profile";
        else if (field === "choice_a") key = "choice-a";
        else if (field === "choice_b") key = "choice-b";
        if (key) { showFieldError(key, item.msg || "该输入有误。"); mapped++; }
        else unmapped.push((item && item.msg) || "该输入有误。");
      });
      backToForm();
      if (unmapped.length > 0) {
        showBox(els.submitError, "提交的内容有误", unmapped.join(" / "));
      }
      throw err;
    }

    if (res.status === 400) {
      var detail = body && typeof body.detail === "string" ? body.detail : "请求被服务器拒绝（HTTP 400）。";
      var hint = /llm|模型|配置|\.env/i.test(detail)
        ? "提示：LLM 未配置时，请先在项目根目录的 .env 中设置模型服务相关环境变量，并重启后端。"
        : null;
      backToForm();
      showBox(els.submitError, "无法开始模拟", detail, hint);
      throw err;
    }

    backToForm();
    showBox(els.submitError, "服务器返回错误",
      "HTTP " + res.status + (body && typeof body.detail === "string" ? "：" + body.detail : "") + "，请稍后重试。");
    throw err;
  }

  function startRun() {
    els.submitBtn.disabled = true;
    els.formSection.style.display = "none";
    els.progressSection.style.display = "block";
    window.scrollTo(0, 0);
    onProgress(0);
    setStage(null);
    text(els.statusMsg, "正在提交模拟请求…");
    text(els.statusDetail, "");
    hideBox(els.progressError);
    els.retryNote.classList.remove("show");
    startedAt = Date.now();
    finished = false;
    updateElapsed();
    if (clockTimer) clearInterval(clockTimer);
    clockTimer = setInterval(updateElapsed, 1000);
  }

  function updateElapsed() {
    text(els.elapsed, fmtClock((Date.now() - startedAt) / 1000));
  }

  function backToForm() {
    finish("failed");
    runId = null;
    els.progressSection.style.display = "none";
    els.formSection.style.display = "block";
    els.submitBtn.disabled = false;
    window.scrollTo(0, 0);
  }

  /* ---------------- events ---------------- */

  els.form.addEventListener("submit", function (e) {
    e.preventDefault();
    clearFieldErrors();
    if (!validate()) return;
    startRun();
    submitSimulation();
  });

  els.profile.addEventListener("input", function () {
    updateCharCount();
    var p = $("error-profile");
    if (p && p.classList.contains("show")) clearFieldErrors();
  });
  els.choiceA.addEventListener("input", function () { clearFieldErrors(); });
  els.choiceB.addEventListener("input", function () { clearFieldErrors(); });

  els.fillSample.addEventListener("click", fillSample);

  updateCharCount();
})();
