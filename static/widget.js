/* LeadBot embed loader. A business pastes ONE line into its website:
     <script src="https://YOUR-LEADBOT-HOST/static/widget.js" data-bot="your-business" data-color="#047857" defer></script>
   It adds a chat bubble; clicking it opens that business's bot (/bot/your-business) in an iframe.
   The iframe is served by LeadBot itself, so the chat works on any website without cross-site
   (CORS) set-up, and the host page's styles cannot break it.
   Other scripts on the page can open it with:  LeadBot.open()  or  LeadBot.open("How much is delivery?") */
(function () {
  var script = document.currentScript;
  var base = script && script.src ? new URL(script.src).origin : "";
  var bot = (script && script.dataset.bot) || "brightpath-solar";
  var color = (script && script.dataset.color) || "#047857";
  var teaser = script && script.dataset.teaser;  // optional nudge text, e.g. "Need help choosing?"

  var css = document.createElement("style");
  css.textContent = [
    "#lb-btn{position:fixed;right:22px;bottom:22px;width:62px;height:62px;border-radius:50%;border:0;background:" + color + ";color:#fff;cursor:pointer;box-shadow:0 10px 28px rgba(0,0,0,.25);z-index:2147483000;display:grid;place-items:center;transition:transform .2s}",
    "#lb-btn:hover{transform:scale(1.06)}",
    "#lb-btn svg{width:28px;height:28px}",
    "#lb-frame{position:fixed;right:22px;bottom:96px;width:370px;max-width:calc(100vw - 32px);height:560px;max-height:calc(100vh - 120px);border:1px solid #E2E8F0;border-radius:22px;box-shadow:0 20px 60px rgba(0,0,0,.22);background:#FFFFFF;z-index:2147483000;display:none;overflow:hidden}",
    "#lb-frame.open{display:block}",
    "#lb-teaser{position:fixed;right:96px;bottom:34px;background:#FFFFFF;color:#0F172A;border:1px solid #E2E8F0;padding:10px 14px;border-radius:14px 14px 4px 14px;box-shadow:0 8px 28px rgba(0,0,0,.14);font:14px Inter,system-ui,sans-serif;max-width:230px;z-index:2147483000;cursor:pointer}",
    "@media(max-width:480px){#lb-frame{right:0;bottom:0;width:100vw;max-width:100vw;height:100%;max-height:100%;border-radius:0;border:0}#lb-teaser{display:none}}",
  ].join("");
  document.head.appendChild(css);

  var ICON_CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>';
  var ICON_X = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>';

  var btn = document.createElement("button");
  btn.id = "lb-btn"; btn.type = "button"; btn.innerHTML = ICON_CHAT; btn.setAttribute("aria-label", "Open chat");
  var frame = document.createElement("iframe");
  frame.id = "lb-frame"; frame.title = "Chat";
  document.body.appendChild(btn);
  document.body.appendChild(frame);

  var ready = false, queued = [];
  function sendToBot(text) { frame.contentWindow.postMessage({ type: "leadbot:send", text: text }, base); }
  function load() {  // the iframe loads the first time the chat opens
    if (frame.src) return;
    frame.onload = function () { ready = true; queued.forEach(sendToBot); queued = []; };
    frame.src = base + "/bot/" + encodeURIComponent(bot);
  }
  function setOpen(on) {
    if (on) load();
    frame.classList.toggle("open", on);
    btn.innerHTML = on ? ICON_X : ICON_CHAT;
    btn.setAttribute("aria-label", on ? "Close chat" : "Open chat");
    var t = document.getElementById("lb-teaser"); if (t) t.remove();
  }

  btn.onclick = function () { setOpen(!frame.classList.contains("open")); };
  window.addEventListener("message", function (e) {  // the close button inside the chat window
    if (e.origin === base && e.data && e.data.type === "leadbot:close") setOpen(false);
  });

  if (teaser) {
    setTimeout(function () {
      if (frame.classList.contains("open")) return;
      var t = document.createElement("div");
      t.id = "lb-teaser"; t.textContent = teaser;
      t.onclick = function () { setOpen(true); };
      document.body.appendChild(t);
    }, 4000);
  }

  window.LeadBot = {
    open: function (text) {
      setOpen(true);
      if (text) { if (ready) sendToBot(text); else queued.push(text); }
    },
    close: function () { setOpen(false); },
  };
})();
