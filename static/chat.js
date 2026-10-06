/* Full-page LeadBot chat: sends messages to /api/chat and shows the live lead score. */
const FIELDS = ["name", "phone", "email", "need", "budget", "timeline"];
const $ = id => document.getElementById(id);
let sid = newSessionId();

function newSessionId() {
  return "c" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function addMessage(text, who) {
  const div = document.createElement("div");
  div.className = "m " + who;
  div.textContent = text;  // textContent, never innerHTML, so replies can't inject HTML
  $("msgs").appendChild(div);
  $("msgs").scrollTop = $("msgs").scrollHeight;
  return div;
}

function showLead(d) {
  $("score").textContent = d.score;
  $("tier").textContent = d.tier;
  $("tier").className = "badge " + d.tier;
  $("rule-val").textContent = d.rule_score;
  $("rule-bar").style.width = d.rule_score + "%";
  const hasModel = d.ml_score != null;
  $("ml-val").textContent = hasModel ? d.ml_score + "%" : "not trained";
  $("ml-bar").style.width = (hasModel ? d.ml_score : 0) + "%";
  $("reason").textContent = d.reason;
  renderFields(d.lead || {});
}

function renderFields(lead) {
  $("fields").innerHTML = "";
  for (const f of FIELDS) {
    const li = document.createElement("li");
    li.className = lead[f] ? "have" : "";
    const label = document.createElement("span");
    const value = document.createElement("span");
    label.textContent = f;
    value.textContent = lead[f] || "-";
    li.append(label, value);
    $("fields").appendChild(li);
  }
}

async function send(text) {
  text = text.trim();
  if (!text) return;
  $("input").value = "";
  $("chips").classList.add("hidden");
  $("send").disabled = true;
  addMessage(text, "user");
  const typing = addMessage("typing...", "bot typing");
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sid, message: text }),
    });
    if (!r.ok) throw new Error(r.status);
    const d = await r.json();
    typing.textContent = d.reply;
    typing.className = "m bot";
    showLead(d);
  } catch (e) {
    typing.textContent = "Sorry, something went wrong. Please try again.";
    typing.className = "m bot";
  }
  $("send").disabled = false;
  $("input").focus();
  $("msgs").scrollTop = $("msgs").scrollHeight;
}

function reset() {
  sid = newSessionId();
  $("msgs").innerHTML = "";
  $("chips").classList.remove("hidden");
  addMessage("Assalam o Alaikum! How can I help you today? You can ask in English or Roman Urdu.", "bot");
  showLead({ score: 0, tier: "cold", rule_score: 0, ml_score: null, reason: "No buying signals yet.", lead: {} });
  $("ml-val").textContent = "-";
  $("input").focus();
}

$("form").onsubmit = e => { e.preventDefault(); send($("input").value); };
$("chips").querySelectorAll("button").forEach(b => b.onclick = () => send(b.textContent));
$("new-chat").onclick = reset;
fetch("/api/health").then(r => r.json()).then(h => $("mode").textContent = "mode: " + h.mode).catch(() => {});
reset();
