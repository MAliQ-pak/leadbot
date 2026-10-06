/* Embeddable LeadBot chat widget.
   Usage on any website:
     <script src="https://YOUR-HOST/static/widget.js" data-title="BrightPath Assistant" defer></script>
   Other scripts can open it with:  LeadBot.open()  or  LeadBot.open("How much is a 5 kW system?") */
(function () {
  var script = document.currentScript;
  var base = script && script.src ? new URL(script.src).origin : "";
  var title = (script && script.dataset.title) || "Chat with us";
  var GREETING = "Assalam o Alaikum! I can help with prices, installation, warranty, installments or booking a free site visit. You can write in English or Roman Urdu.";
  var QUICK = ["How much is a 5 kW system?", "5kw ki qeemat kitni hai?", "Book a free site visit", "Do you offer installments?"];

  function newId() { return "s" + Math.random().toString(36).slice(2) + Date.now().toString(36); }
  function store(kind, key, val) {  // storage can be blocked (private mode); the widget still works without it
    try { var s = window[kind]; if (val === undefined) return s.getItem(key); s.setItem(key, val); } catch (e) { return null; }
  }
  var sid = store("localStorage", "leadbot_sid") || newId();
  store("localStorage", "leadbot_sid", sid);

  var css = document.createElement("style");
  css.textContent = [
    "#lb-root{font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;--lb-green:#3E5C3F;--lb-green-d:#2D462F;--lb-ink:#1C1B18;--lb-line:#E7E0D4;--lb-cream:#F7F2EA}",
    "#lb-btn{position:fixed;right:22px;bottom:22px;width:62px;height:62px;border-radius:50%;border:0;background:var(--lb-green);color:#fff;cursor:pointer;box-shadow:0 10px 28px rgba(45,70,47,.35);z-index:99999;display:grid;place-items:center;transition:transform .2s,background .2s}",
    "#lb-btn:hover{transform:scale(1.06);background:var(--lb-green-d)}",
    "#lb-btn svg{width:28px;height:28px}",
    "#lb-teaser{position:fixed;right:96px;bottom:34px;background:#FFFDF8;color:var(--lb-ink);border:1px solid var(--lb-line);padding:10px 14px;border-radius:14px 14px 4px 14px;box-shadow:0 8px 28px rgba(31,35,25,.14);font-size:14px;max-width:230px;z-index:99999;cursor:pointer;animation:lb-pop .3s ease}",
    "#lb-panel{position:fixed;right:22px;bottom:96px;width:370px;max-width:calc(100vw - 32px);height:560px;max-height:calc(100vh - 120px);background:#FFFDF8;border:1px solid var(--lb-line);border-radius:22px;box-shadow:0 20px 60px rgba(31,35,25,.22);display:none;flex-direction:column;overflow:hidden;z-index:99999;animation:lb-pop .2s ease}",
    "#lb-panel.open{display:flex}",
    "@keyframes lb-pop{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}",
    "#lb-head{background:var(--lb-green-d);color:#fff;padding:14px 16px;display:flex;align-items:center;gap:11px}",
    "#lb-av{width:38px;height:38px;border-radius:50%;background:#FFFDF8;display:grid;place-items:center;flex:none}",
    "#lb-av svg{width:22px;height:22px}",
    "#lb-head b{display:block;font-family:Fraunces,Georgia,serif;font-weight:600;font-size:17px;letter-spacing:-.01em}",
    "#lb-head small{font-size:12px;color:#C9D6C6}",
    "#lb-head small::before{content:'';display:inline-block;width:7px;height:7px;border-radius:50%;background:#9FBE9A;margin-right:5px}",
    "#lb-x{margin-left:auto;background:none;border:0;color:#C9D6C6;font-size:24px;line-height:1;cursor:pointer;padding:4px}",
    "#lb-msgs{flex:1;overflow-y:auto;padding:16px;background:var(--lb-cream);display:flex;flex-direction:column;gap:9px}",
    ".lb-m{max-width:84%;padding:9px 13px;border-radius:16px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}",
    ".lb-u{align-self:flex-end;background:var(--lb-green);color:#fff;border-bottom-right-radius:4px}",
    ".lb-b{align-self:flex-start;background:#fff;color:var(--lb-ink);border:1px solid var(--lb-line);border-bottom-left-radius:4px}",
    ".lb-dots{display:inline-flex;gap:4px;padding:3px 0}",
    ".lb-dots i{width:7px;height:7px;border-radius:50%;background:#A39B8B;animation:lb-b 1s infinite}",
    ".lb-dots i:nth-child(2){animation-delay:.15s}.lb-dots i:nth-child(3){animation-delay:.3s}",
    "@keyframes lb-b{0%,60%,100%{opacity:.3;transform:none}30%{opacity:1;transform:translateY(-3px)}}",
    "#lb-quick{display:flex;flex-wrap:wrap;gap:6px;padding:0 16px 10px;background:var(--lb-cream)}",
    "#lb-quick button{border:1px solid #C9D8C4;background:#E8F0E4;color:var(--lb-green-d);border-radius:99px;padding:6px 11px;font-size:13px;font-weight:500;cursor:pointer;font-family:inherit}",
    "#lb-quick button:hover{background:#DEEBDB;border-color:var(--lb-green)}",
    "#lb-form{display:flex;gap:8px;padding:10px 12px;border-top:1px solid var(--lb-line);background:#FFFDF8}",
    "#lb-in{flex:1;min-width:0;border:1px solid var(--lb-line);border-radius:99px;padding:10px 14px;font-size:14px;outline:none;font-family:inherit;color:var(--lb-ink);background:#fff}",
    "#lb-in:focus{border-color:var(--lb-green)}",
    "#lb-send{width:40px;height:40px;flex:none;border:0;border-radius:50%;background:var(--lb-green);color:#fff;cursor:pointer;display:grid;place-items:center}",
    "#lb-send:hover{background:var(--lb-green-d)}",
    "#lb-send:disabled{opacity:.5;cursor:default}",
    "#lb-send svg{width:18px;height:18px}",
    "#lb-foot{text-align:center;font-size:11px;color:#A39B8B;padding:0 0 8px;background:#FFFDF8}",
    "@media(max-width:480px){#lb-panel{right:0;bottom:0;width:100vw;max-width:100vw;height:100%;max-height:100%;border-radius:0;border:0}#lb-teaser{display:none}}",
  ].join("");
  document.head.appendChild(css);

  var ICON_CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>';
  var ICON_X = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>';
  var ICON_SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="#3E5C3F" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4" fill="#3E5C3F"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  var ICON_SEND = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 20.5 21 12 3 3.5l.01 6.6L15 12 3.01 13.9z"/></svg>';

  var root = document.createElement("div");
  root.id = "lb-root";
  root.innerHTML =
    '<button id="lb-btn" aria-label="Open chat">' + ICON_CHAT + '</button>' +
    '<div id="lb-panel" role="dialog" aria-label="' + title.replace(/"/g, "") + '">' +
      '<div id="lb-head"><div id="lb-av">' + ICON_SUN + '</div><div><b></b><small>Online, replies instantly</small></div>' +
        '<button id="lb-x" aria-label="Close chat">&times;</button></div>' +
      '<div id="lb-msgs" aria-live="polite"></div>' +
      '<div id="lb-quick"></div>' +
      '<form id="lb-form"><input id="lb-in" placeholder="Type your message..." autocomplete="off" maxlength="1000">' +
        '<button id="lb-send" type="submit" aria-label="Send">' + ICON_SEND + '</button></form>' +
      '<div id="lb-foot">Powered by LeadBot</div>' +
    '</div>';
  document.body.appendChild(root);

  var $ = function (id) { return root.querySelector("#" + id); };
  var panel = $("lb-panel"), msgs = $("lb-msgs"), input = $("lb-in"), quick = $("lb-quick"), btn = $("lb-btn");
  root.querySelector("#lb-head b").textContent = title;
  var busy = false;

  function add(text, who) {
    var d = document.createElement("div");
    d.className = "lb-m " + (who === "u" ? "lb-u" : "lb-b");
    d.textContent = text;  // textContent, never innerHTML, so replies can't inject HTML
    msgs.appendChild(d); msgs.scrollTop = msgs.scrollHeight;
    return d;
  }

  function showQuick(on) {
    quick.innerHTML = "";
    if (!on) return;
    QUICK.forEach(function (q) {
      var b = document.createElement("button");
      b.type = "button"; b.textContent = q;
      b.onclick = function () { send(q); };
      quick.appendChild(b);
    });
  }

  function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    busy = true; $("lb-send").disabled = true;
    input.value = ""; showQuick(false); add(text, "u");
    var typing = add("", "b");
    typing.innerHTML = '<span class="lb-dots"><i></i><i></i><i></i></span>';
    fetch(base + "/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sid, message: text }) })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { typing.textContent = d.reply; })
      .catch(function () { typing.textContent = "Sorry, something went wrong. Please try again."; })
      .then(function () { busy = false; $("lb-send").disabled = false; msgs.scrollTop = msgs.scrollHeight; input.focus(); });
  }

  function setOpen(on) {
    panel.classList.toggle("open", on);
    btn.innerHTML = on ? ICON_X : ICON_CHAT;
    btn.setAttribute("aria-label", on ? "Close chat" : "Open chat");
    var t = document.getElementById("lb-teaser"); if (t) t.remove();
    store("sessionStorage", "leadbot_seen", "1");
    if (on) input.focus();
  }

  // Restore this visitor's earlier messages so a page reload doesn't lose the chat
  add(GREETING, "b");
  fetch(base + "/api/conversations/" + encodeURIComponent(sid))
    .then(function (r) { return r.ok ? r.json() : []; })
    .then(function (list) {
      list.forEach(function (m) { add(m.content, m.role === "user" ? "u" : "b"); });
      showQuick(!list.length && !busy);
    })
    .catch(function () { showQuick(true); });

  btn.onclick = function () { setOpen(!panel.classList.contains("open")); };
  $("lb-x").onclick = function () { setOpen(false); };
  $("lb-form").onsubmit = function (e) { e.preventDefault(); send(input.value); };

  // Friendly nudge after a few seconds, once per browser session
  if (!store("sessionStorage", "leadbot_seen")) {
    setTimeout(function () {
      if (panel.classList.contains("open") || document.getElementById("lb-teaser")) return;
      var t = document.createElement("div");
      t.id = "lb-teaser"; t.textContent = "Hi! Want a solar quote? Ask me anything.";
      t.onclick = function () { setOpen(true); };
      root.appendChild(t);
    }, 4000);
  }

  window.LeadBot = {
    open: function (text) { setOpen(true); if (text) send(text); },
    close: function () { setOpen(false); },
  };
})();
