/* The chat window for one business's bot: /bot/<business>, shown in an iframe on that business's
   website (widget.js) or as the live preview in the admin panel (?preview=1). */
(function () {
  const $ = id => document.getElementById(id);
  const slug = decodeURIComponent(location.pathname.split("/").filter(Boolean)[1] || "");
  const params = new URLSearchParams(location.search);
  const preview = params.get("preview") === "1";
  const inFrame = window.parent !== window;
  let busy = false;

  // one chat per visitor per business; preview chats use their own id so they never mix with real ones
  const key = "leadbot_sid_" + slug + (preview ? "_preview" : "");
  const newId = () => "s" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  let sid;
  try { sid = localStorage.getItem(key) || newId(); localStorage.setItem(key, sid); } catch (e) { sid = newId(); }

  function add(text, who) {
    const d = document.createElement("div");
    d.className = "m " + who;
    d.textContent = text;  // textContent, never innerHTML, so replies can't inject HTML
    $("msgs").appendChild(d);
    $("msgs").scrollTop = $("msgs").scrollHeight;
    return d;
  }

  function showQuick(list) {
    $("quick").innerHTML = "";
    (list || []).forEach(q => {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = q;
      b.onclick = () => send(q);
      $("quick").appendChild(b);
    });
  }

  async function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    busy = true; $("send").disabled = true;
    $("input").value = ""; showQuick([]); add(text, "u");
    const typing = add("", "b");
    typing.innerHTML = '<span class="dots"><i></i><i></i><i></i></span>';
    try {
      const r = await fetch("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot: slug, session_id: sid, message: text, preview }),
      });
      if (!r.ok) throw new Error(r.status);
      typing.textContent = (await r.json()).reply;
      if (preview && inFrame) window.parent.postMessage({ type: "leadbot:replied" }, location.origin);
    } catch (e) {
      typing.textContent = "Sorry, something went wrong. Please try again.";
    }
    busy = false; $("send").disabled = false;
    $("msgs").scrollTop = $("msgs").scrollHeight;
    $("input").focus();
  }

  async function start() {
    let cfg;
    try {
      const r = await fetch("/api/bot/" + encodeURIComponent(slug));
      if (!r.ok) throw new Error(r.status);
      cfg = await r.json();
    } catch (e) {
      add("This chat is not available right now.", "b");
      return;
    }
    document.documentElement.style.setProperty("--brand", cfg.color || "#3E5C3F");
    $("bot-name").textContent = cfg.bot_name;
    document.title = cfg.bot_name + " | " + cfg.name;
    if (preview) { const t = document.createElement("div"); t.className = "preview-tag"; t.textContent = "Live preview: test chats are not saved as leads"; $("msgs").appendChild(t); }
    add(cfg.greeting, "b");
    let past = [];
    try {
      const r = await fetch(`/api/conversations/${encodeURIComponent(sid)}?bot=${encodeURIComponent(slug)}`);
      if (r.ok) past = await r.json();
    } catch (e) { /* first visit */ }
    past.forEach(m => add(m.content, m.role === "user" ? "u" : "b"));
    if (!past.length) showQuick(cfg.quick_replies);
  }

  $("form").onsubmit = e => { e.preventDefault(); send($("input").value); };
  if (inFrame && !preview) {
    $("close").hidden = false;
    $("close").onclick = () => window.parent.postMessage({ type: "leadbot:close" }, "*");
  }
  // "New chat" in the preview
  if (params.get("fresh") === "1") { try { localStorage.removeItem(key); } catch (e) {} sid = newId(); try { localStorage.setItem(key, sid); } catch (e) {} }
  const started = start();
  // The page around the iframe (widget.js) can ask the bot a question, e.g. an "Ask about this" button.
  // It waits for the greeting and history first, so the question is not shown twice.
  window.addEventListener("message", e => {
    if (e.source === window.parent && e.data && e.data.type === "leadbot:send") started.then(() => send(String(e.data.text || "")));
  });
})();
