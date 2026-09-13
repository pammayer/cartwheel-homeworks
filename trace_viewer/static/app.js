// Cartwheel trace viewer — plain JS, no framework, no build step.

const traceListEl = document.getElementById("trace-list");
const detailEl = document.getElementById("detail");
let selectedId = null;

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function fmtLatency(seconds) {
  if (seconds === null || seconds === undefined) return "";
  return seconds < 1 ? `${Math.round(seconds * 1000)}ms` : `${seconds.toFixed(2)}s`;
}

function firstText(messages) {
  if (!Array.isArray(messages)) return null;
  for (const m of messages) {
    for (const part of m.parts || []) {
      if (part.type === "text" && part.content) return part.content;
    }
  }
  return null;
}

async function loadTraceList() {
  traceListEl.textContent = "Loading traces…";
  try {
    const res = await fetch("/api/traces");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const traces = await res.json();
    renderTraceList(traces);
  } catch (err) {
    traceListEl.innerHTML = `<div class="error-banner">Could not load traces: ${escapeHtml(err.message)}</div>`;
  }
}

function renderTraceList(traces) {
  if (traces.length === 0) {
    traceListEl.innerHTML = "<div>No traces yet. Send some requests through the agent server first.</div>";
    return;
  }
  traceListEl.innerHTML = "";
  for (const t of traces) {
    const row = document.createElement("div");
    row.className = "trace-row" + (t.id === selectedId ? " selected" : "");
    const roleClass = (t.user_role || "").toLowerCase();
    const toolChips = (t.tool_order || [])
      .map((name) => `<span class="tool-chip">${escapeHtml(name)}</span>`)
      .join("");
    row.innerHTML = `
      <div class="row-top">
        <span>${fmtTime(t.timestamp)}</span>
        <span class="role-badge ${roleClass}">${escapeHtml(t.user_role || "?")} #${escapeHtml(t.user_id || "?")}</span>
      </div>
      <div class="preview-in">${escapeHtml(t.preview_input || "(no input recorded)")}</div>
      <div class="row-status">
        <span class="status-badge ${t.has_error ? "warn" : "ok"}">${t.has_error ? "⚠ issue" : "✓ clean"}</span>
        ${toolChips || '<span class="tool-chip none">no tools called</span>'}
      </div>
    `;
    row.addEventListener("click", () => selectTrace(t.id));
    traceListEl.appendChild(row);
  }
}

async function selectTrace(id) {
  selectedId = id;
  document.querySelectorAll(".trace-row").forEach((el, i) => {});
  loadTraceList(); // cheap re-render to update the selected highlight
  detailEl.innerHTML = "<div id=\"empty-state\">Loading trace…</div>";
  try {
    const res = await fetch(`/api/traces/${id}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const trace = await res.json();
    renderTraceDetail(trace);
  } catch (err) {
    detailEl.innerHTML = `<div class="error-banner">Could not load trace ${escapeHtml(id)}: ${escapeHtml(err.message)}</div>`;
  }
}

function renderTraceDetail(trace) {
  const a = trace.attributes || {};
  const attrEntries = Object.entries(a)
    .map(([k, v]) => `<span><b>${escapeHtml(k)}:</b> ${escapeHtml(v)}</span>`)
    .join("");

  detailEl.innerHTML = `
    <div class="detail-header">
      <h2>${escapeHtml(trace.id)}</h2>
      <div class="attr-row">
        <span><b>When:</b> ${fmtTime(trace.timestamp)}</span>
        <span><b>Latency:</b> ${fmtLatency(trace.latency)}</span>
        <span><b>Cost:</b> $${(trace.total_cost || 0).toFixed(4)}</span>
        <span><b>Spans:</b> ${trace.observation_count}</span>
        ${attrEntries}
      </div>
      <div><a href="${escapeHtml(trace.langfuse_url)}" target="_blank" rel="noopener">Open in Langfuse &#8599;</a></div>
      ${trace.has_error ? `<div class="error-banner">&#9888; This trace contains at least one error, non-default level, or a tool call that returned ok:false — look for the highlighted spans below.</div>` : ""}
    </div>

    <div class="conversation">
      <h3>Conversation</h3>
      ${renderConversation(trace.messages)}
    </div>

    <div class="tree-section">
      <h3>Execution tree (root → leaves, click to expand)</h3>
      <div id="tree-root"></div>
    </div>
  `;

  const treeRoot = document.getElementById("tree-root");
  for (const node of trace.tree) {
    treeRoot.appendChild(renderNode(node));
  }
}

function renderConversation(messages) {
  const parts = [];
  for (const m of messages.input || []) {
    const text = (m.parts || []).map((p) => p.content).filter(Boolean).join("\n");
    parts.push(`<div class="msg user"><span class="msg-role">${escapeHtml(m.role)}</span>${escapeHtml(text)}</div>`);
  }
  for (const m of messages.output || []) {
    const text = (m.parts || []).map((p) => p.content).filter(Boolean).join("\n");
    parts.push(`<div class="msg assistant"><span class="msg-role">${escapeHtml(m.role)}</span>${escapeHtml(text)}</div>`);
  }
  return parts.join("") || "<div>(no top-level conversation recorded on this trace)</div>";
}

function renderJSON(label, value) {
  if (value === null || value === undefined) return "";
  return `<div class="field-label">${escapeHtml(label)}</div><pre class="raw">${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
}

function renderNode(node) {
  const details = document.createElement("details");
  details.className = "node" + (node.has_error ? " has-error" : "");

  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span class="type-badge ${escapeHtml(node.type || "")}">${escapeHtml(node.type || "?")}</span>
    <span class="node-name">${escapeHtml(node.name || "(unnamed)")}</span>
    <span class="node-latency">${fmtLatency(node.latency)}</span>
    ${node.has_error ? '<span class="node-error-flag">&#9888; issue</span>' : ""}
  `;
  details.appendChild(summary);

  const body = document.createElement("div");
  body.className = "node-body";

  let bodyHtml = "";

  if (node.status_message) {
    bodyHtml += `<div class="error-banner">${escapeHtml(node.status_message)}</div>`;
  }
  if (node.level && node.level !== "DEFAULT") {
    bodyHtml += `<div class="error-banner">Level: ${escapeHtml(node.level)}</div>`;
  }

  // Tool calls get a friendlier, prominent arguments/result box in addition
  // to the raw JSON further below.
  if (node.type === "TOOL") {
    bodyHtml += `
      <div class="tool-call-box">
        <div class="field-label">Arguments</div>
        <pre class="raw">${escapeHtml(JSON.stringify(node.input, null, 2))}</pre>
        <div class="field-label">Result</div>
        <pre class="raw">${escapeHtml(JSON.stringify(node.output, null, 2))}</pre>
      </div>
    `;
  }

  if (node.model) {
    bodyHtml += `<div class="field-label">Model</div><div>${escapeHtml(node.model)}</div>`;
  }
  if (node.usage && (node.usage.input || node.usage.output)) {
    bodyHtml += `<div class="field-label">Token usage</div><div>${node.usage.input || 0} in / ${node.usage.output || 0} out</div>`;
  }

  bodyHtml += renderJSON("Raw input", node.input);
  bodyHtml += renderJSON("Raw output", node.output);
  bodyHtml += renderJSON("Attributes", node.attributes);

  bodyHtml += `
    <div class="ids-row">
      id: ${escapeHtml(node.id)} &middot;
      parent: ${escapeHtml(node.parent_id || "(root)")} &middot;
      start: ${escapeHtml(node.start_time)} &middot;
      end: ${escapeHtml(node.end_time)}
    </div>
  `;

  body.innerHTML = bodyHtml;
  details.appendChild(body);

  if (node.children && node.children.length > 0) {
    const childrenWrap = document.createElement("div");
    childrenWrap.className = "node-children";
    for (const child of node.children) {
      childrenWrap.appendChild(renderNode(child));
    }
    details.appendChild(childrenWrap);
  }

  return details;
}

document.getElementById("refresh-btn").addEventListener("click", loadTraceList);
loadTraceList();
