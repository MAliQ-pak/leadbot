/* The agency (super admin) view: every business on LeadBot, with support view, suspend and delete. */
const $ = id => document.getElementById(id);
const esc = s => (s == null ? "" : String(s)).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let data = null;

function ago(ts) {
  if (!ts) return "never";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + " min ago";
  if (s < 86400) return Math.floor(s / 3600) + " h ago";
  return Math.floor(s / 86400) + " d ago";
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (r.status === 401) { location.href = "/login"; throw new Error("401"); }
  if (r.status === 403) { location.href = "/app"; throw new Error("403"); }  // not a super admin
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong.");
  return body;
}
const post = (path, body, method = "POST") =>
  api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

async function load() {
  try { data = await api("/api/agency/overview"); } catch (e) { return; }
  const t = data.totals;
  $("t-businesses").textContent = t.businesses; $("t-leads").textContent = t.leads; $("t-hot").textContent = t.hot;
  $("t-won").textContent = t.won; $("t-chats").textContent = t.chats_today; $("t-suspended").textContent = t.suspended;
  $("nav-biz").textContent = t.businesses;
  $("user").textContent = data.you;
  $("ai").textContent = "AI: " + (data.ai.mode === "mock" ? "offline bot" : data.ai.mode) + (data.ai.error ? " (failing)" : "");
  render();
  const events = await api("/api/agency/activity").catch(() => []);
  $("activity-rows").innerHTML = events.map(e => `<tr>
      <td>${ago(e.created)}</td><td>${esc(e.business || "Agency")}</td><td>${esc(e.actor)}</td>
      <td>${esc(e.action)}</td><td class="sub">${esc(e.detail)}</td></tr>`).join("")
    || '<tr><td colspan="5" class="empty">Nothing yet.</td></tr>';
}

function render() {
  const q = $("search").value.trim().toLowerCase();
  const list = data.businesses.filter(b => !q || [b.name, b.owner, b.industry, b.slug].some(v => v && v.toLowerCase().includes(q)));
  $("rows").innerHTML = list.map(b => {
    const paused = b.status === "suspended";
    return `<tr class="${paused ? "paused" : ""}">
      <td><b>${esc(b.name)}</b> <a class="sub-link" href="/bot/${esc(b.slug)}" target="_blank" title="Open this business's chat">chat &#8599;</a>
        <span class="sub">${esc(b.owner || "no owner")} · ${esc(b.industry)} template${b.setup_done ? "" : " · setup not finished"}</span></td>
      <td>${b.leads}</td><td>${b.hot ? `<span class="badge hot">${b.hot}</span>` : 0}</td><td>${b.chats_today}</td>
      <td>${ago(b.last_activity)}</td>
      <td><span class="pill ${paused ? "lost" : "won"}">${paused ? "Suspended" : "Active"}</span></td>
      <td class="actions">
        <button class="btn" data-view="${b.id}">Open dashboard</button>
        <button class="btn ghost" data-status="${b.id}" data-to="${paused ? "active" : "suspended"}">${paused ? "Reactivate" : "Suspend"}</button>
        <button class="btn danger" data-delete="${b.id}">Delete</button>
      </td></tr>`;
  }).join("") || '<tr><td colspan="7" class="empty">No businesses match.</td></tr>';
}

document.addEventListener("click", async e => {
  const v = e.target.closest("[data-view]"), s = e.target.closest("[data-status]"), d = e.target.closest("[data-delete]");
  try {
    if (v) location.href = (await post(`/api/agency/view/${v.dataset.view}`)).next;
    if (s) {
      const b = data.businesses.find(x => x.id == s.dataset.status);
      const pausing = s.dataset.to === "suspended";
      if (!confirm(pausing ? `Suspend ${b.name}? Its bot stops answering on its website and its owner cannot log in, until you reactivate it.`
                           : `Reactivate ${b.name}?`)) return;
      await post(`/api/agency/businesses/${b.id}/status`, { status: s.dataset.to });
      await load();
    }
    if (d) {
      const b = data.businesses.find(x => x.id == d.dataset.delete);
      const typed = prompt(`This permanently deletes ${b.name} with all its leads, chats, knowledge and accounts. It cannot be undone.\n\nType the business name to confirm:`);
      if (typed === null) return;
      await post(`/api/agency/businesses/${b.id}`, { confirm: typed }, "DELETE");
      await load();
    }
  } catch (err) { alert(err.message); }
});
$("search").addEventListener("input", () => data && render());
$("logout").onclick = async () => { await fetch("/api/auth/logout", { method: "POST" }); location.href = "/login"; };

load();
setInterval(load, 10000);
