/* LeadBot admin panel: overview and lead management. Pipeline board + audit log: admin-pipeline.js; knowledge base: admin-kb.js. */
const $ = id => document.getElementById(id);
const esc = s => (s == null ? "" : String(s)).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const FIELDS = ["name", "phone", "email", "need", "budget", "timeline"];
// Deal stages, left to right on the Pipeline board (same list as db.STATUSES on the server)
const STATUSES = ["new", "contacted", "site_visit", "quote_sent", "won", "lost"];
const STATUS_LABEL = { new: "New", contacted: "Contacted", site_visit: "Site visit booked", quote_sent: "Quote sent", won: "Won", lost: "Lost" };
const stageName = s => STATUS_LABEL[s] || s;
const OPEN = l => l.status !== "won" && l.status !== "lost";
const TABS = [
  ["all", "All", () => true],
  ["hot", "Hot", l => OPEN(l) && l.tier === "hot"],
  ["warm", "Warm", l => OPEN(l) && l.tier === "warm"],
  ["cold", "Cold", l => OPEN(l) && l.tier === "cold"],
  ["won", "Won", l => l.status === "won"],
  ["lost", "Lost", l => l.status === "lost"],
];

let leads = [];
let tab = "all";
let openSid = null;
let shownMsgCount = -1;

// ---------- helpers ----------
function ago(ts) {
  if (!ts) return "-";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + " min ago";
  if (s < 86400) return Math.floor(s / 3600) + " h ago";
  return Math.floor(s / 86400) + " d ago";
}
const displayName = l => l.name || "Anonymous visitor";
const contact = l => [l.phone, l.email].filter(Boolean).join(" · ") || "No contact yet";
const scoreCell = l => `<span class="badge ${esc(l.tier)}">${esc(l.tier)} ${l.score ?? 0}</span>` +
  (l.ml_score != null ? `<span class="sub">rules ${l.rule_score} · model ${l.ml_score}</span>` : "");
const cell = v => v ? `<td>${esc(v)}</td>` : `<td class="none">-</td>`;

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

// ---------- routing ----------
const TITLES = { overview: "Overview", pipeline: "Pipeline", leads: "Leads", audit: "Audit log", bot: "Bot & knowledge" };
function route() {
  const page = (location.hash || "#overview").slice(1);
  const name = TITLES[page] ? page : "overview";
  for (const p of Object.keys(TITLES)) $("page-" + p).hidden = p !== name;
  document.querySelectorAll(".side nav a").forEach(a => a.classList.toggle("active", a.dataset.page === name));
  $("page-title").textContent = TITLES[name];
  if (name === "bot") loadBot();
  if (name === "pipeline" && window.renderBoard) window.renderBoard();
  if (name === "audit" && window.loadAudit) window.loadAudit();
}
window.addEventListener("hashchange", route);

// ---------- data ----------
async function load() {
  try { leads = await api("/api/leads"); } catch (e) { return; }
  $("nav-count").textContent = leads.length;
  $("nav-open").textContent = leads.filter(l => OPEN(l) && (l.phone || l.email)).length;
  renderOverview();
  renderLeads();
  if (window.renderBoard) window.renderBoard();
  if (location.hash === "#audit" && window.loadAudit) window.loadAudit();
  if (openSid) refreshDrawer();
}

function renderOverview() {
  const n = f => leads.filter(f).length;
  $("k-total").textContent = leads.length;
  $("k-hot").textContent = n(l => OPEN(l) && l.tier === "hot");
  $("k-warm").textContent = n(l => OPEN(l) && l.tier === "warm");
  $("k-cold").textContent = n(l => OPEN(l) && l.tier === "cold");
  $("k-won").textContent = n(l => l.status === "won");
  $("k-lost").textContent = n(l => l.status === "lost");

  const hot = leads.filter(l => OPEN(l) && l.tier === "hot").sort((a, b) => b.score - a.score).slice(0, 6);
  $("hot-list").innerHTML = hot.map(l => miniItem(l, `<span class="badge hot">${l.score}</span>`)).join("")
    || '<div class="empty">No hot leads yet. Chat on the website to create some.</div>';

  const recent = leads.slice(0, 5);
  $("recent-list").innerHTML = recent.map(l => miniItem(l, `<span class="badge ${esc(l.tier)}">${esc(l.tier)}</span>`, l.last_message)).join("")
    || '<div class="empty">No conversations yet.</div>';

  const total = leads.length || 1;
  $("pipeline").innerHTML = STATUSES.map(s => {
    const c = n(l => l.status === s);
    return `<div class="pipe"><div class="bar-label"><span class="pill ${s}">${stageName(s)}</span><span>${c}</span></div>
      <div class="bar"><i style="width:${(c / total) * 100}%;background:var(--${s})"></i></div></div>`;
  }).join("");
}

function miniItem(l, right, subtitle) {
  return `<div class="item" data-sid="${esc(l.session_id)}">
    <div class="who"><b>${esc(displayName(l))}</b><small>${esc(subtitle || contact(l) + (l.need ? " · " + l.need : ""))}</small></div>
    ${right}<time>${ago(l.updated)}</time></div>`;
}

function renderLeads() {
  const q = $("search").value.trim().toLowerCase();
  const match = l => !q || [l.name, l.phone, l.email, l.need, l.budget, l.timeline, l.last_message, l.notes]
    .some(v => v && String(v).toLowerCase().includes(q));

  $("tabs").innerHTML = TABS.map(([key, label, f]) =>
    `<button data-tab="${key}" class="${key === tab ? "active" : ""}">${label}<span>${leads.filter(f).length}</span></button>`).join("");

  const filter = TABS.find(t => t[0] === tab)[2];
  const list = leads.filter(l => filter(l) && match(l));
  $("rows").innerHTML = list.map(l => `
    <tr data-sid="${esc(l.session_id)}">
      <td><b>${esc(displayName(l))}</b><span class="sub">${esc(contact(l))}</span></td>
      <td>${scoreCell(l)}</td>${cell(l.need)}${cell(l.budget)}${cell(l.timeline)}
      <td><span class="pill ${esc(l.status)}">${esc(stageName(l.status))}</span></td>
      <td>${ago(l.updated)}<span class="sub">${l.messages || 0} messages</span></td>
    </tr>`).join("") || `<tr><td colspan="7" class="empty">No leads here${q ? " match your search" : " yet"}.</td></tr>`;
}

// ---------- lead drawer ----------
function openDrawer(sid) {
  openSid = sid;
  shownMsgCount = -1;
  $("d-notes").dataset.dirty = "";
  $("d-notes-status").textContent = "";
  $("drawer").hidden = $("shade").hidden = false;
  refreshDrawer();
}

function closeDrawer() {
  openSid = null;
  $("drawer").hidden = $("shade").hidden = true;
}

async function refreshDrawer() {
  const l = leads.find(x => x.session_id === openSid);
  if (!l) return closeDrawer();
  $("d-name").textContent = displayName(l);
  $("d-sub").textContent = "First seen " + ago(l.created) + " · last active " + ago(l.updated);
  $("d-score").textContent = l.score ?? 0;
  $("d-tier").textContent = l.tier;
  $("d-tier").className = "badge " + l.tier;
  $("d-rule").textContent = l.rule_score ?? "-";
  $("d-rule-bar").style.width = (l.rule_score || 0) + "%";
  $("d-ml").textContent = l.ml_score != null ? l.ml_score + "%" : "not trained";
  $("d-ml-bar").style.width = (l.ml_score || 0) + "%";
  $("d-reason").textContent = "Why: " + (l.reason || "no buying signals yet");
  $("d-fields").innerHTML = FIELDS.map(f =>
    `<dt>${f}</dt><dd class="${l[f] ? "" : "none"}">${esc(l[f]) || "not shared"}</dd>`).join("");
  $("d-status").innerHTML = STATUSES.map(s =>
    `<button data-status="${s}" class="${s} ${l.status === s ? "active" : ""}">${stageName(s)}</button>`).join("");
  if (!$("d-notes").dataset.dirty) $("d-notes").value = l.notes || "";

  // only reload the transcript when new messages arrived
  if (shownMsgCount !== l.messages) {
    shownMsgCount = l.messages;
    const msgs = await api("/api/conversations/" + encodeURIComponent(l.session_id)).catch(() => []);
    $("d-chat").innerHTML = msgs.map(m => `<div class="m ${m.role}">${esc(m.content)}
      <time>${new Date(m.created * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div>`).join("")
      || '<div class="empty">No messages.</div>';
  }
}

async function setStatus(status) {
  await api("/api/leads/" + encodeURIComponent(openSid), {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }),
  });
  await load();
}

async function saveNotes() {
  await api("/api/leads/" + encodeURIComponent(openSid), {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ notes: $("d-notes").value }),
  });
  $("d-notes").dataset.dirty = "";
  $("d-notes-status").textContent = "Saved";
  await load();
}

async function deleteLead() {
  const l = leads.find(x => x.session_id === openSid);
  if (!l || !confirm(`Delete ${displayName(l)} and their conversation? This cannot be undone.`)) return;
  await api("/api/leads/" + encodeURIComponent(openSid), { method: "DELETE" });
  closeDrawer();
  await load();
}

// ---------- bot page (knowledge-base training lives in admin-kb.js) ----------
const MODE_LABEL = { claude: "Claude AI", gemini: "Gemini AI", mock: "Offline mock" };
async function loadBot() {
  const h = await api("/api/health").catch(() => null);
  if (h) {
    $("b-mode").textContent = MODE_LABEL[h.mode] || h.mode;
    $("b-mode-note").textContent = h.mode === "mock" ? "rule-based replies, no internet needed"
      : `${h.model}, answering from the knowledge base`;
    if (h.llm_error) {
      $("b-mode").textContent = (MODE_LABEL[h.mode] || h.mode) + " (failing)";
      $("b-mode-note").textContent = `Last call failed ${ago(h.llm_error.time)}, so the offline bot answered: ${h.llm_error.message}`;
      $("b-mode-note").classList.add("danger-text");
    } else {
      $("b-mode-note").classList.remove("danger-text");
    }
    $("b-clf").textContent = h.classifier ? "Rules + model" : "Rules only";
    $("b-clf-note").textContent = h.classifier ? `model weight ${Math.round(h.ml_weight * 100)}%` : "run train_classifier.py to add the model";
  }
  if (window.loadKb) window.loadKb();
}

// ---------- events ----------
document.addEventListener("click", e => {
  const row = e.target.closest("[data-sid]");
  if (row) return openDrawer(row.dataset.sid);
  const t = e.target.closest("[data-tab]");
  if (t) { tab = t.dataset.tab; renderLeads(); return; }
  const s = e.target.closest("[data-status]");
  if (s) setStatus(s.dataset.status);
});
$("search").addEventListener("input", renderLeads);
$("d-close").onclick = closeDrawer;
$("shade").onclick = closeDrawer;
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });
$("d-notes").addEventListener("input", () => { $("d-notes").dataset.dirty = "1"; $("d-notes-status").textContent = "Unsaved"; });
$("d-save-notes").onclick = saveNotes;
$("d-delete").onclick = deleteLead;

api("/api/health").then(h => {
  $("mode").textContent = "Bot mode: " + (MODE_LABEL[h.mode] || h.mode);
  $("biz").textContent = h.business + " admin";
}).catch(() => {});
route();
load();
setInterval(load, 5000);
