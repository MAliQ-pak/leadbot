/* Admin panel: Pipeline board (deals by stage, drag to move) and Audit log.
   Uses leads, $, esc, api, ago, displayName, STATUSES, stageName and load from admin.js. */
const TIERS = [["all", "All"], ["hot", "Hot"], ["warm", "Warm"], ["cold", "Cold"]];
let boardTier = "all";
let dragging = null;  // session id of the card being dragged (the 5 s refresh waits until the drop)

// ---------- pipeline board ----------
function renderBoard() {
  if (dragging) return;
  const showAnon = $("p-anon").checked;
  // a deal needs a way to reach the visitor; anonymous chats stay in Leads unless switched on
  const deals = leads.filter(l => (showAnon || l.phone || l.email) && (boardTier === "all" || l.tier === boardTier));

  $("p-tiers").innerHTML = TIERS.map(([key, label]) => {
    const n = leads.filter(l => (showAnon || l.phone || l.email) && (key === "all" || l.tier === key)).length;
    return `<button data-ptier="${key}" class="${key === boardTier ? "active" : ""}">${label}<span>${n}</span></button>`;
  }).join("");

  $("board").innerHTML = STATUSES.map(stage => {
    const cards = deals.filter(l => l.status === stage).sort((a, b) => b.score - a.score);
    return `<div class="col ${stage}" data-stage="${stage}">
      <div class="col-head"><b>${stageName(stage)}</b><span class="col-count">${cards.length}</span></div>
      <div class="col-body">${cards.map(card).join("") || '<div class="col-empty">No deals</div>'}</div>
    </div>`;
  }).join("");
}
window.renderBoard = renderBoard;

function card(l) {
  const facts = [l.need, l.budget && "Budget " + l.budget, l.timeline].filter(Boolean).map(esc).join(" · ");
  return `<div class="deal" draggable="true" data-sid="${esc(l.session_id)}" title="Drag to move, click to open">
    <div class="deal-top"><b>${esc(displayName(l))}</b><span class="badge ${esc(l.tier)}">${esc(l.tier)} ${l.score ?? 0}</span></div>
    ${facts ? `<div class="deal-facts">${facts}</div>` : ""}
    <div class="deal-foot"><span>${esc(l.phone || l.email || "No contact yet")}</span><time>${ago(l.updated)}</time></div>
  </div>`;
}

async function moveDeal(sid, stage) {
  const l = leads.find(x => x.session_id === sid);
  if (!l || l.status === stage) return;
  l.status = stage;  // move it on screen at once; the server confirms below
  renderBoard();
  try {
    await api("/api/leads/" + encodeURIComponent(sid), {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: stage }),
    });
  } catch (e) {
    alert("Could not move the deal. Please try again.");
  }
  load();
}

const board = $("board");
board.addEventListener("dragstart", e => {
  const d = e.target.closest(".deal");
  if (!d) return;
  dragging = d.dataset.sid;
  e.dataTransfer.setData("text/plain", dragging);
  e.dataTransfer.effectAllowed = "move";
  d.classList.add("lifted");
});
board.addEventListener("dragend", () => {
  dragging = null;
  document.querySelectorAll(".col.over").forEach(c => c.classList.remove("over"));
  renderBoard();
});
board.addEventListener("dragover", e => {
  const col = e.target.closest(".col");
  if (!col || !dragging) return;
  e.preventDefault();  // allows the drop
  document.querySelectorAll(".col.over").forEach(c => c !== col && c.classList.remove("over"));
  col.classList.add("over");
});
board.addEventListener("drop", e => {
  const col = e.target.closest(".col");
  if (!col) return;
  e.preventDefault();
  const sid = e.dataTransfer.getData("text/plain") || dragging;
  dragging = null;
  moveDeal(sid, col.dataset.stage);
});
$("p-anon").addEventListener("change", renderBoard);

// ---------- audit log ----------
const AUDIT_TABS = [["", "All"], ["lead", "Leads"], ["kb", "Knowledge base"], ["auth", "Logins"], ["system", "System"]];
const AUDIT_KIND = { lead: "Lead", kb: "Knowledge", auth: "Login", system: "System" };
let auditKind = "";

async function loadAudit() {
  $("a-tabs").innerHTML = AUDIT_TABS.map(([key, label]) =>
    `<button data-akind="${key}" class="${key === auditKind ? "active" : ""}">${label}</button>`).join("");
  const list = await api("/api/audit" + (auditKind ? "?kind=" + auditKind : "")).catch(() => null);
  if (!list) return;
  $("a-rows").innerHTML = list.map(a => {
    const when = new Date(a.created * 1000);
    // a log line about a lead that still exists links to it
    const lead = a.kind === "lead" && leads.find(l => l.session_id === a.target);
    return `<tr class="${lead ? "linked" : ""}" ${lead ? `data-sid="${esc(a.target)}"` : ""}>
      <td><b>${when.toLocaleDateString([], { day: "numeric", month: "short" })} ${when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</b><span class="sub">${ago(a.created)}</span></td>
      <td>${esc(a.actor)}</td>
      <td><span class="src ${esc(a.kind)}">${AUDIT_KIND[a.kind] || esc(a.kind)}</span> ${esc(a.action)}</td>
      <td class="detail">${esc(a.detail) || "-"}</td>
    </tr>`;
  }).join("") || '<tr><td colspan="4" class="empty">Nothing logged yet.</td></tr>';
}
window.loadAudit = loadAudit;

// tier tabs on the board, kind tabs on the audit log (lead cards and linked rows open via admin.js)
document.addEventListener("click", e => {
  const t = e.target.closest("[data-ptier]");
  if (t) { boardTier = t.dataset.ptier; renderBoard(); return; }
  const k = e.target.closest("[data-akind]");
  if (k) { auditKind = k.dataset.akind; loadAudit(); }
});

if (location.hash === "#audit") loadAudit();
