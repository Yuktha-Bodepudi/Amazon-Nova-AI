/**
 * WarehouseIQ — Frontend
 * API base: backend at http://localhost:8000
 * Serve this folder on http://localhost:3000 (CORS is set for that origin).
 */

const API_BASE = "http://localhost:8000";

// ── Helpers ───────────────────────────────────────────────────────────────────

function get(id) {
  return document.getElementById(id);
}

async function api(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text || res.statusText}`);
  }
  if (res.headers.get("content-type")?.includes("application/json")) {
    return res.json();
  }
  return res.text();
}

// ── Health ────────────────────────────────────────────────────────────────────

async function checkHealth() {
  const el = get("health");
  try {
    const h = await api("/health");
    el.textContent = `Backend: ${h.status} | Graph: ${h.graph_compiled ? "ready" : "no"} | Tools: ${h.tools_available} | Models: ${(h.models || []).join(", ")}`;
    el.className = "health ok";
    get("runPipeline").disabled = false;
  } catch (e) {
    el.textContent = `Backend unreachable: ${e.message}. Start with: uvicorn main:app --reload --port 8000`;
    el.className = "health err";
    get("runPipeline").disabled = true;
  }
}

// ── Pipeline ──────────────────────────────────────────────────────────────────

let statusInterval = null;

async function runPipeline() {
  const btn = get("runPipeline");
  btn.disabled = true;
  get("errorText").textContent = "";
  try {
    await api("/pipeline/run", { method: "POST" });
    startStatusPolling();
  } catch (e) {
    get("statusText").textContent = "Error";
    get("errorText").textContent = e.message;
    btn.disabled = false;
  }
}

function startStatusPolling() {
  if (statusInterval) clearInterval(statusInterval);
  statusInterval = setInterval(pollStatus, 1500);
  pollStatus();
}

function stopStatusPolling() {
  if (statusInterval) {
    clearInterval(statusInterval);
    statusInterval = null;
  }
  get("runPipeline").disabled = false;
}

async function pollStatus() {
  try {
    const s = await api("/pipeline/status");
    get("statusText").textContent = s.running ? "Running" : (s.complete ? "Complete" : "Idle");
    get("stepText").textContent = s.step || "—";
    get("progressBar").style.width = `${s.progress ?? 0}%`;
    get("progressPct").textContent = s.progress ?? 0;
    get("errorText").textContent = s.error || "";

    if (s.complete || s.error) {
      stopStatusPolling();
      if (s.complete) loadResults();
    }
  } catch (_) {}
}

// ── Results ───────────────────────────────────────────────────────────────────

async function loadResults() {
  const hint = get("resultsHint");
  try {
    const data = await api("/results");
    hint.textContent = "Loaded. Use tabs below to view patterns, actions, alerts, stats, and records.";
    hint.classList.remove("err");
    renderPatterns(data.patterns || []);
    renderActions(data.action_items || []);
    renderAlerts(data.alerts || []);
    renderStats(data.stats || {});
    renderRecords(data.records || [], data.records_total ?? 0);
  } catch (e) {
    hint.textContent = "No results yet. Run the pipeline above and wait for it to complete, then click Refresh results.";
    hint.classList.add("err");
    renderPatterns([]);
    renderActions([]);
    renderAlerts([]);
    renderStats({});
    renderRecords([], 0);
  }
}

function renderPatterns(list) {
  const el = get("patternsContent");
  el.innerHTML = list.length === 0 ? "<p class='hint'>No patterns.</p>" : list.map((p) => {
    const sev = (p.severity || "").toLowerCase();
    return `
      <div class="item severity-${sev}">
        <div class="title">${escapeHtml(p.title || p.pattern_id || "—")}</div>
        <div class="meta">${escapeHtml([p.pattern_id, p.severity, (p.data_sources || []).join(", ")].filter(Boolean).join(" · "))}</div>
        <div class="body">${escapeHtml(p.description || p.root_cause || "")}</div>
      </div>`;
  }).join("");
}

function renderActions(list) {
  const el = get("actionsContent");
  el.innerHTML = list.length === 0 ? "<p class='hint'>No action items.</p>" : list.map((a) => `
    <div class="item">
      <div class="title">${escapeHtml(a.title || a.action_id || "—")}</div>
      <div class="meta">${escapeHtml([a.priority, a.owner, a.pattern_ref].filter(Boolean).join(" · "))}</div>
      <div class="body">${escapeHtml(a.description || "")}</div>
    </div>`).join("");
}

function renderAlerts(list) {
  const el = get("alertsContent");
  el.innerHTML = list.length === 0 ? "<p class='hint'>No alerts.</p>" : list.map((a) => `
    <div class="item">
      <div class="title">${escapeHtml(a.alert_id || "Alert")}</div>
      <div class="meta">${escapeHtml([a.severity, a.pattern_id].filter(Boolean).join(" · "))}</div>
      <div class="body">${escapeHtml(a.message || a.text || "")}</div>
    </div>`).join("");
}

function renderStats(stats) {
  const el = get("statsContent");
  const str = JSON.stringify(stats, null, 2);
  el.textContent = str || "{}";
}

function renderRecords(records, total) {
  const totalEl = get("recordsTotal");
  const el = get("recordsContent");
  if (!totalEl || !el) return;
  totalEl.textContent = total ?? records.length;
  el.innerHTML = records.length === 0 ? "<p class='hint'>No records. Run the pipeline first.</p>" : records.slice(0, 200).map((r) => {
    const title = r.record_id || r.id || r.type || "Record";
    const meta = [r.source_type || r.source, r.warehouse_id || r.warehouse, r.severity].filter(Boolean).join(" · ");
    const body = typeof r === "object" ? (r.text || JSON.stringify(r).slice(0, 300) + (JSON.stringify(r).length > 300 ? "…" : "")) : String(r);
    return `<div class="item"><div class="title">${escapeHtml(title)}</div><div class="meta">${escapeHtml(meta)}</div><div class="body">${escapeHtml(body)}</div></div>`;
  }).join("");
}

function escapeHtml(s) {
  if (s == null) return "";
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    const name = tab.dataset.tab;
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    const panel = get(`panel-${name}`);
    if (panel) panel.classList.add("active");
  });
});

// ── Query ─────────────────────────────────────────────────────────────────────

async function submitQuery() {
  const input = get("questionInput");
  const q = input.value.trim();
  if (!q) return;
  const wrap = get("answerWrap");
  const text = get("answerText");
  wrap.hidden = false;
  text.textContent = "…";
  try {
    const res = await api("/query", {
      method: "POST",
      body: JSON.stringify({ question: q }),
    });
    text.textContent = res.answer || res.response_text || "No answer.";
  } catch (e) {
    text.textContent = `Error: ${e.message}`;
  }
}

// ── Voice ─────────────────────────────────────────────────────────────────────

async function submitVoice() {
  const fileInput = get("audioFile");
  if (!fileInput.files?.length) return;
  const file = fileInput.files[0];
  const resultEl = get("voiceResult");
  get("transcriptText").textContent = "…";
  get("responseText").textContent = "…";
  resultEl.hidden = false;
  const audioEl = get("responseAudio");
  audioEl.src = "";
  try {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/voice/audio`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(await res.text() || res.statusText);
    const data = await res.json();
    get("transcriptText").textContent = data.transcript || "—";
    get("responseText").textContent = data.response_text || "—";
    if (data.audio_b64) {
      audioEl.src = `data:audio/mpeg;base64,${data.audio_b64}`;
    }
  } catch (e) {
    get("responseText").textContent = `Error: ${e.message}`;
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

get("runPipeline").addEventListener("click", runPipeline);
get("submitQuery").addEventListener("click", submitQuery);
get("questionInput").addEventListener("keydown", (e) => { if (e.key === "Enter") submitQuery(); });
get("submitVoice").addEventListener("click", submitVoice);
const refreshBtn = get("refreshResults");
if (refreshBtn) refreshBtn.addEventListener("click", () => loadResults());

checkHealth();
pollStatus(); // once to show current status
loadResults(); // show results if pipeline was run before
