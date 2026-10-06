/* Admin panel: training the knowledge base.
   Four ways to teach the bot: Q&A pairs, answering unanswered questions, uploading documents or
   importing web pages, and editing the main text. Every change is live on the next chat message.
   Uses $, esc, api and ago from admin.js. */
const SOURCE_LABEL = { text: "Main text", qa: "Q&A", file: "Document", url: "Website" };
let kb = null;
const rendered = {};

async function loadKb() {
  try { showKb(await api("/api/kb")); } catch (e) { /* server busy; next poll retries */ }
}
window.loadKb = loadKb;

function showKb(data) {
  kb = data;
  const src = data.by_source;
  $("b-sections").textContent = data.topics;
  $("b-sources").textContent = Object.keys(src).map(k => `${src[k]} ${SOURCE_LABEL[k] || k}`).join(" · ") || "no topics yet";
  $("c-qa").textContent = data.faqs.length;
  $("c-docs").textContent = data.docs.length;
  $("c-un").textContent = data.unanswered.length;
  $("c-un").hidden = !data.unanswered.length;
  $("nav-un").textContent = data.unanswered.length;
  $("nav-un").hidden = !data.unanswered.length;
  // re-render a list only when it changed, so open previews don't collapse on every refresh
  for (const [key, render] of [["faqs", renderQa], ["unanswered", renderUnanswered], ["docs", renderDocs]]) {
    const sig = JSON.stringify(data[key]);
    if (rendered[key] !== sig) { rendered[key] = sig; render(); }
  }
  if (!$("kb-text").dataset.dirty) $("kb-text").value = data.text;
  $("kb-chips").innerHTML = data.sections.map(s => `<span>${esc(s)}</span>`).join("");
}

async function send(path, method, body) {
  return api(path, { method, headers: { "Content-Type": "application/json" }, body: body && JSON.stringify(body) });
}

// fetch() errors carry only the status; read FastAPI's {"detail": "..."} message for the admin
async function sendWithMessage(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Something went wrong.");
  return data;
}

// ---------- tabs ----------
const PANES = { qa: "kb-qa", unanswered: "kb-unanswered", docs: "kb-docs", text: "kb-text-pane" };
function showKbTab(name) {
  document.querySelectorAll("[data-kbtab]").forEach(b => b.classList.toggle("active", b.dataset.kbtab === name));
  for (const [key, id] of Object.entries(PANES)) $(id).hidden = key !== name;
}

// ---------- test the knowledge ----------
$("kt-form").onsubmit = async e => {
  e.preventDefault();
  const q = $("kt-q").value.trim();
  if (!q) return;
  const r = await api("/api/kb/test?q=" + encodeURIComponent(q)).catch(() => null);
  if (!r) return;
  const verdict = r.confident
    ? `<p class="verdict ok">The bot can answer this from <b>${esc(r.matches[0].section)}</b>.</p>`
    : `<p class="verdict bad">The bot is not confident (best match below ${Math.round(r.threshold * 100)}%). It will say it is not sure and log the question under Unanswered.
       <button class="btn small" type="button" id="kt-add">Add a Q&amp;A for this</button></p>`;
  $("kt-out").innerHTML = verdict + r.matches.map((m, i) => `
    <div class="match ${i === 0 ? "top" : ""}">
      <div class="match-head"><b>${esc(m.section)}</b><span class="src ${esc(m.source)}">${SOURCE_LABEL[m.source] || esc(m.source)}</span>
        <span class="pct">${Math.round(Math.min(m.score, 1) * 100)}% match</span></div>
      <div class="bar"><i style="width:${Math.min(m.score, 1) * 100}%"></i></div>
      <p>${esc(m.text.split(": ").slice(1).join(": ") || m.text)}</p>
    </div>`).join("");
  const add = $("kt-add");
  if (add) add.onclick = () => startQa({ question: q });
};

// ---------- Q&A ----------
function renderQa() {
  $("qa-list").innerHTML = kb.faqs.map(f => `
    <div class="kb-item">
      <div class="kb-main">
        <b>${esc(f.question)}</b>
        ${f.variants ? `<small>Also: ${esc(f.variants.split("\n").filter(Boolean).join(" · "))}</small>` : ""}
        <p>${esc(f.answer)}</p>
        ${f.source === "unanswered" ? '<span class="src qa">learned from a visitor question</span>' : ""}
      </div>
      <div class="kb-actions">
        <button class="btn ghost small" data-qa-edit="${f.id}">Edit</button>
        <button class="btn ghost small danger-text" data-qa-del="${f.id}">Delete</button>
      </div>
    </div>`).join("") || '<div class="empty">No Q&amp;A yet. Add the questions customers ask most.</div>';
}

function startQa({ id = "", question = "", variants = "", answer = "", unansweredId = "" }) {
  showKbTab("qa");
  $("qa-id").value = id;
  $("qa-unanswered").value = unansweredId;
  $("qa-q").value = question;
  $("qa-v").value = variants;
  $("qa-a").value = answer;
  $("qa-submit").textContent = id ? "Save changes" : "Add Q&A";
  $("qa-cancel").hidden = !(id || unansweredId);
  $("qa-status").textContent = unansweredId ? "Answering a visitor's question" : "";
  $("qa-form").scrollIntoView({ behavior: "smooth", block: "center" });
  $(question ? "qa-a" : "qa-q").focus();
}

function resetQa() { startQa({}); $("qa-status").textContent = ""; }

$("qa-form").onsubmit = async e => {
  e.preventDefault();
  const id = $("qa-id").value;
  const body = { question: $("qa-q").value, variants: $("qa-v").value, answer: $("qa-a").value,
                 unanswered_id: $("qa-unanswered").value ? Number($("qa-unanswered").value) : null };
  try {
    showKb(await send(id ? "/api/kb/faq/" + id : "/api/kb/faq", id ? "PUT" : "POST", body));
    resetQa();
    $("qa-status").textContent = "Saved. The bot knows this now.";
  } catch (err) {
    $("qa-status").textContent = "Could not save. Check the question and answer are filled in.";
  }
};
$("qa-cancel").onclick = resetQa;

// ---------- unanswered ----------
function renderUnanswered() {
  $("un-list").innerHTML = kb.unanswered.map(u => `
    <div class="kb-item">
      <div class="kb-main">
        <b>"${esc(u.question)}"</b>
        <small>Asked ${u.times} time${u.times > 1 ? "s" : ""} · last ${ago(u.last)} · best match ${Math.round(Math.min(u.score, 1) * 100)}%</small>
      </div>
      <div class="kb-actions">
        <button class="btn small" data-un-answer="${u.id}">Answer</button>
        <button class="btn ghost small" data-un-dismiss="${u.id}">Dismiss</button>
      </div>
    </div>`).join("") || '<div class="empty">Nothing waiting. Every question visitors asked was answered from the knowledge base.</div>';
}

// ---------- documents & websites ----------
function renderDocs() {
  $("doc-list").innerHTML = kb.docs.map(d => `
    <div class="kb-item">
      <div class="kb-main">
        <b>${esc(d.name)}</b>
        <small><span class="src ${esc(d.kind)}">${SOURCE_LABEL[d.kind]}</span> ${d.kind === "url" ? esc(d.origin) + " · " : ""}${d.chars.toLocaleString()} characters · added ${ago(d.created)}</small>
        <div class="preview" id="pv-${d.id}" hidden></div>
      </div>
      <div class="kb-actions">
        <button class="btn ghost small" data-doc-view="${d.id}">Topics</button>
        <button class="btn ghost small danger-text" data-doc-del="${d.id}">Delete</button>
      </div>
    </div>`).join("") || '<div class="empty">No documents or web pages yet.</div>';
}

async function toggleTopics(id) {
  const box = $("pv-" + id);
  if (!box.hidden) { box.hidden = true; return; }
  const d = await api("/api/kb/docs/" + id).catch(() => null);
  if (!d) return;
  box.innerHTML = `<small>${d.topics.length} topic${d.topics.length === 1 ? "" : "s"} the bot learned:</small>` +
    d.topics.map(t => `<div class="topic"><b>${esc(t.section)}</b> ${esc(t.text.slice(0, 220))}${t.text.length > 220 ? "..." : ""}</div>`).join("");
  box.hidden = false;
}

async function uploadFile(file) {
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { $("doc-status").textContent = "That file is larger than 5 MB."; return; }
  $("doc-status").textContent = `Reading ${file.name}...`;
  const data = await new Promise((ok, fail) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] || "");  // strip "data:...;base64,"
    r.onerror = fail;
    r.readAsDataURL(file);
  });
  try {
    showKb(await sendWithMessage("/api/kb/upload", { name: file.name, data }));
    $("doc-status").textContent = `Added ${file.name}. The bot can now answer from it.`;
  } catch (err) {
    $("doc-status").textContent = err.message;
  }
  $("file-in").value = "";
}

$("file-in").onchange = e => uploadFile(e.target.files[0]);
const drop = $("drop");
drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", e => { e.preventDefault(); drop.classList.remove("over"); uploadFile(e.dataTransfer.files[0]); });

$("url-form").onsubmit = async e => {
  e.preventDefault();
  const btn = e.target.querySelector("button");
  btn.disabled = true;
  $("doc-status").textContent = "Fetching the page...";
  try {
    showKb(await sendWithMessage("/api/kb/url", { url: $("url-in").value }));
    $("doc-status").textContent = "Page imported. The bot can now answer from it.";
    $("url-in").value = "";
  } catch (err) {
    $("doc-status").textContent = err.message;
  }
  btn.disabled = false;
};

// ---------- main text ----------
$("kb-text").addEventListener("input", () => { $("kb-text").dataset.dirty = "1"; $("kb-status").textContent = "Unsaved changes"; });
$("kb-save").onclick = async () => {
  $("kb-save").disabled = true;
  try {
    showKb(await send("/api/kb", "PUT", { text: $("kb-text").value }));
    $("kb-text").dataset.dirty = "";
    $("kb-status").textContent = "Saved. The bot uses the new text from the next message.";
  } catch (e) {
    $("kb-status").textContent = "Could not save. Please try again.";
  }
  $("kb-save").disabled = false;
};

// ---------- clicks on list buttons ----------
document.addEventListener("click", async e => {
  const b = e.target.closest("button");
  if (!b) return;
  const d = b.dataset;
  if (d.kbtab) return showKbTab(d.kbtab);
  if (d.qaEdit) {
    const f = kb.faqs.find(x => x.id === Number(d.qaEdit));
    return startQa({ id: f.id, question: f.question, variants: f.variants, answer: f.answer });
  }
  if (d.qaDel && confirm("Delete this Q&A? The bot will stop using it.")) return showKb(await send("/api/kb/faq/" + d.qaDel, "DELETE"));
  if (d.unAnswer) {
    const u = kb.unanswered.find(x => x.id === Number(d.unAnswer));
    return startQa({ question: u.question, unansweredId: u.id });
  }
  if (d.unDismiss) return showKb(await send(`/api/kb/unanswered/${d.unDismiss}/dismiss`, "POST"));
  if (d.docView) return toggleTopics(d.docView);
  if (d.docDel && confirm("Delete this document? The bot will forget what it learned from it.")) return showKb(await send("/api/kb/docs/" + d.docDel, "DELETE"));
});

// The Unanswered badge stays current on every page; full data refreshes on the Bot page
loadKb();
setInterval(() => {
  const editing = document.activeElement && ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName);
  if (!editing) loadKb();
}, 8000);
