/* Setup wizard: five steps that configure one business's bot, with a live preview beside them. */
const $ = id => document.getElementById(id);
const COLORS = ["#3E5C3F", "#2E3A6E", "#2B5CE6", "#7A5A2A", "#5E3A6E", "#1C1B18"];
const FIELDS = ["need", "name", "phone", "budget", "timeline"];
let me = null, step = 1, color = "#3E5C3F";

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (r.status === 401) { location.href = "/login"; throw new Error("401"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Something went wrong.");
  return data;
}
const json = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const list = s => s.split(/[,\n]/).map(x => x.trim()).filter(Boolean);

function show(n) {
  step = n;
  document.querySelectorAll("[data-pane]").forEach(p => p.hidden = Number(p.dataset.pane) !== n);
  document.querySelectorAll("#stepnav button").forEach(b => {
    b.classList.toggle("active", Number(b.dataset.step) === n);
    b.classList.toggle("done", Number(b.dataset.step) < n);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function reloadPreview(fresh) {
  $("preview").src = `/bot/${me.business.slug}?preview=1${fresh ? "&fresh=1" : ""}&t=${Date.now()}`;
}

function fill() {
  const b = me.business, s = b.settings;
  $("biz-name").textContent = b.name;
  $("f-name").value = b.name; $("f-website").value = b.website || "";
  $("tpl").innerHTML = Object.entries(me.templates).map(([k, label]) =>
    `<button type="button" data-tpl="${k}" class="${k === b.industry ? "active" : ""}"><b>${label}</b><span>${(me.template_blurbs || {})[k] || ""}</span></button>`).join("");
  $("f-bot").value = b.bot_name; $("f-greet").value = b.greeting;
  color = b.color || COLORS[0];
  $("colors").innerHTML = COLORS.map(c => `<span class="swatch ${c === color ? "active" : ""}" data-color="${c}" style="background:${c}"></span>`).join("")
    + `<input type="color" id="f-color" value="${color}" title="Any colour">`;
  $("f-quick").value = (s.quick_replies || []).join("\n");
  FIELDS.forEach(f => $("q-" + f).value = s.questions[f] || "");
  $("f-need").value = (s.need_keywords || []).join(", ");
  $("f-intent").value = (s.intent_words || []).join(", ");
  $("s-3").value = s.stage_names.site_visit; $("s-4").value = s.stage_names.quote_sent;
  const origin = location.origin;
  const script = `<script src="${origin}/static/widget.js" data-bot="${b.slug}" data-color="${color}" defer></script>`;
  const iframe = `<iframe src="${origin}/bot/${b.slug}" title="${b.name} chat" style="width:380px;height:560px;border:1px solid #E7E0D4;border-radius:18px"></iframe>`;
  $("code-script").querySelector("span").textContent = script;
  $("code-iframe").querySelector("span").textContent = iframe;
  $("direct-link").href = $("direct-link").textContent = `${origin}/bot/${b.slug}`;
}

async function loadKb() {
  const kb = await api("/api/kb");
  $("f-kb").value = kb.text;
  $("topic-count").textContent = `(${kb.topics} topics the bot can answer from)`;
}

async function saveSettings(body, msgId) {
  me = await api("/api/business", json("PUT", body));
  fill();
  reloadPreview();
  $(msgId).textContent = "Saved";
  setTimeout(() => $(msgId).textContent = "", 2500);
}

async function guarded(btn, fn) {
  btn.disabled = true;
  try { await fn(); } catch (e) { alert(e.message); }
  btn.disabled = false;
}

// ---------- step actions ----------
$("save-1").onclick = e => guarded(e.target, async () => {
  await saveSettings({ name: $("f-name").value.trim(), website: $("f-website").value.trim() }, "msg-1");
  show(2);
});
$("tpl").onclick = e => {
  const t = e.target.closest("[data-tpl]");
  if (!t || t.classList.contains("active")) return;
  if (!confirm("Switch to the " + me.templates[t.dataset.tpl] + " template? This replaces the bot's main text and settings.")) return;
  guarded(t, async () => {
    me = await api("/api/business/template", json("POST", { industry: t.dataset.tpl }));
    fill(); await loadKb(); reloadPreview(true);
  });
};
$("save-2").onclick = e => guarded(e.target, async () => {
  await api("/api/kb", json("PUT", { text: $("f-kb").value }));
  await loadKb(); reloadPreview();
  show(3);
});
$("url-go").onclick = e => guarded(e.target, async () => {
  $("import-msg").textContent = "Fetching the page...";
  const kb = await api("/api/kb/url", json("POST", { url: $("url-in").value.trim() }));
  $("import-msg").textContent = `Imported. The bot now knows ${kb.topics} topics.`;
  $("topic-count").textContent = `(${kb.topics} topics the bot can answer from)`;
  reloadPreview();
});
$("file-in").onchange = async e => {
  const file = e.target.files[0];
  if (!file) return;
  $("import-msg").textContent = `Reading ${file.name}...`;
  const data = await new Promise(ok => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(",")[1] || ""); r.readAsDataURL(file); });
  try {
    const kb = await api("/api/kb/upload", json("POST", { name: file.name, data }));
    $("import-msg").textContent = `Added ${file.name}. The bot now knows ${kb.topics} topics.`;
    $("topic-count").textContent = `(${kb.topics} topics the bot can answer from)`;
    reloadPreview();
  } catch (err) { $("import-msg").textContent = err.message; }
  e.target.value = "";
};
$("colors").onclick = e => {
  const sw = e.target.closest("[data-color]");
  if (!sw) return;
  color = sw.dataset.color;
  document.querySelectorAll(".swatch").forEach(x => x.classList.toggle("active", x === sw));
  $("f-color").value = color;
};
$("colors").oninput = e => { if (e.target.id === "f-color") { color = e.target.value.toUpperCase(); document.querySelectorAll(".swatch").forEach(x => x.classList.remove("active")); } };
$("save-3").onclick = e => guarded(e.target, async () => {
  await saveSettings({ bot_name: $("f-bot").value.trim(), greeting: $("f-greet").value.trim(), color,
                       quick_replies: list($("f-quick").value).slice(0, 6) }, "msg-3");
  show(4);
});
$("save-4").onclick = e => guarded(e.target, async () => {
  const questions = Object.fromEntries(FIELDS.map(f => [f, $("q-" + f).value.trim()]));
  await saveSettings({ questions, need_keywords: list($("f-need").value), intent_words: list($("f-intent").value),
                       stage_names: { site_visit: $("s-3").value.trim(), quote_sent: $("s-4").value.trim() } }, "msg-4");
  show(5);
});
document.addEventListener("click", e => {
  const c = e.target.closest("[data-copy]");
  if (!c) return;
  navigator.clipboard.writeText($(c.dataset.copy).querySelector("span").textContent).then(() => {
    c.textContent = "Copied"; setTimeout(() => c.textContent = "Copy", 1500);
  });
});
$("finish").onclick = e => guarded(e.target, async () => {
  await api("/api/business", json("PUT", { setup_done: true }));
  location.href = "/app";
});
$("stepnav").onclick = e => { const b = e.target.closest("[data-step]"); if (b) show(Number(b.dataset.step)); };
$("new-chat").onclick = () => reloadPreview(true);
$("clear-tests").onclick = e => guarded(e.target, async () => { await api("/api/preview-chats", { method: "DELETE" }); reloadPreview(true); });

(async () => {
  me = await api("/api/me");
  fill();
  await loadKb();
  reloadPreview();
  show(1);
})();
