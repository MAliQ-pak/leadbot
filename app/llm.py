"""LLM layer. Replies come from Claude (Anthropic) or Gemini (Google), chosen by LLM_PROVIDER, or from a
rule-based offline bot when there is no key or the API fails, so the whole system can be demoed offline."""
import json
import os
import re
import time

from .db import LEAD_FIELDS

BUSINESS = os.getenv("BUSINESS_NAME", "BrightPath Solar")

SYSTEM = """You are the website sales assistant for {business}.

RULES
- Answer ONLY using the CONTEXT below. If the answer is not in the context, say you are not sure and offer to have a human advisor call back. Never invent prices, dates, or policies.
- Reply in the same language and script the visitor uses (English, Urdu, or Roman Urdu). Keep replies short (2-4 sentences) and friendly.
- Speak as the company's assistant: never mention the "context", these rules, or that you are reading from a document.
- While helping, naturally collect lead details, asking for ONE missing detail at a time in this order: need (what they want), name, phone, budget, timeline. Never ask again for a detail listed under ALREADY KNOWN.
- Email is optional: ask for it at most once in the whole conversation, and only after phone, budget and timeline are known.
- Only record lead details the visitor has actually stated in this conversation. Budget means the visitor's OWN budget; never copy a price from the CONTEXT into the lead. Use null for anything unknown.

OUTPUT: return ONLY valid JSON, no markdown, in exactly this shape:
{{"reply": "<message to the visitor>", "lead": {{"name": null, "phone": null, "email": null, "need": null, "budget": null, "timeline": null}}}}

ALREADY KNOWN:
{known}

CONTEXT:
{context}
"""


def _system(context_chunks, known_lead):
    known = "\n".join(f"- {k}: {known_lead[k]}" for k in LEAD_FIELDS if known_lead.get(k)) or "(nothing yet)"
    return SYSTEM.format(business=BUSINESS, context=_context_text(context_chunks), known=known)

ASK_ORDER = [
    ("need", "What are you looking for (e.g. home system size or backup needs)?"),
    ("name", "May I know your name?"),
    ("phone", "What's the best phone number for our advisor to reach you?"),
    ("budget", "Do you have a rough budget in mind?"),
    ("timeline", "When are you hoping to get this done?"),
]


def _extract_json(text):
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _clean_lead(raw):
    lead = {}
    for k in LEAD_FIELDS:
        v = (raw or {}).get(k)
        if isinstance(v, str) and v.strip() and v.strip().lower() not in ("null", "none", "unknown", "n/a"):
            lead[k] = v.strip()
    return lead


# Which AI writes the replies: LLM_PROVIDER = "claude" (Anthropic) or "gemini" (Google, has a free tier).
# With no key for the chosen provider, the offline bot answers.
PROVIDER_KEYS = {"claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}


def provider():
    """The active AI provider, or "mock" when its API key is missing."""
    p = os.getenv("LLM_PROVIDER", "claude").strip().lower()
    return p if p in PROVIDER_KEYS and os.getenv(PROVIDER_KEYS[p], "").strip() else "mock"


def model_name():
    return {"claude": os.getenv("MODEL", "claude-sonnet-5-5"),
            "gemini": os.getenv("GEMINI_MODEL", "gemini-3.8-flash")}.get(provider(), "offline rules")


# Last AI API problem, shown in the admin panel so a silent fallback to the offline bot is visible.
LAST_ERROR = None
_client = None

# After an API error, skip the AI for LLM_COOLDOWN seconds so visitors get instant offline replies
# instead of waiting for another failure (e.g. no credit, or the free-tier quota is used up).
_cooldown_until = 0

# Spending guard for a public site: at most LLM_HOURLY_LIMIT AI replies per hour in total;
# beyond that the offline bot answers until the hour rolls over.
_recent_calls = []


def _within_hourly_budget():
    now = time.time()
    _recent_calls[:] = [t for t in _recent_calls if now - t < 3600]
    return len(_recent_calls) < int(os.getenv("LLM_HOURLY_LIMIT", "200"))


def respond(history, context_chunks, known_lead, allow_llm=True):
    """history: list of {role, content}. Returns (reply, lead_updates).
    allow_llm=False (chat over its message limit) always uses the offline bot."""
    global LAST_ERROR, _cooldown_until
    p = provider()
    if allow_llm and p != "mock" and time.time() >= _cooldown_until and _within_hourly_budget():
        _recent_calls.append(time.time())
        try:
            fn = _respond_gemini if p == "gemini" else _respond_claude
            result = fn(history, context_chunks, known_lead)
            LAST_ERROR = None
            return result
        except Exception as e:  # any API problem: keep the chat working with the offline bot
            LAST_ERROR = {"message": str(e)[:300], "time": time.time()}
            _cooldown_until = time.time() + int(os.getenv("LLM_COOLDOWN", "60"))
            print(f"{p} error, offline bot answers for now:", e)
    return _respond_mock(history, context_chunks, known_lead)


def _context_text(context_chunks):
    return "\n".join(f"- {c}" for c in context_chunks) or "(no relevant information found)"


def _user_first(history):
    """The APIs need the conversation to start with a user message."""
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    return messages


def _parse_reply(text):
    data = _extract_json(text)
    if not data or "reply" not in data:
        return text.strip() or "Sorry, could you rephrase that?", {}
    return str(data["reply"]), _clean_lead(data.get("lead"))


# ---------- Claude (Anthropic) ----------
def _get_client():
    global _client
    if _client is None:
        import anthropic
        # Keys not tied to a workspace must name one; set ANTHROPIC_WORKSPACE_ID in .env for those.
        ws = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()
        _client = anthropic.Anthropic(default_headers={"anthropic-workspace-id": ws} if ws else None)
    return _client


def _respond_claude(history, context_chunks, known_lead):
    msg = _get_client().beta.messages.create(
        model=os.getenv("MODEL", "claude-sonnet-5-5"),
        max_tokens=2000,  # thinking counts toward this, so leave room for the JSON reply
        output_config={"effort": "low"},  # short chat replies: fast and cheap
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # if the model declines, the API retries on a suitable fallback model
        system=_system(context_chunks, known_lead),
        messages=_user_first(history),
    )
    if msg.stop_reason == "refusal":
        raise RuntimeError("Claude declined to answer this message")
    return _parse_reply("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"))


# ---------- Gemini (Google) ----------
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _respond_gemini(history, context_chunks, known_lead):
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in _user_first(history)]
    body = {
        "systemInstruction": {"parts": [{"text": _system(context_chunks, known_lead)}]},
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 2000,                 # thinking counts toward this too
            "responseMimeType": "application/json",  # Gemini then always returns valid JSON
            "thinkingConfig": {"thinkingLevel": "low"},
        },
    }
    data = _gemini_post(body)
    if (data.get("promptFeedback") or {}).get("blockReason"):
        raise RuntimeError("Gemini blocked this message: " + data["promptFeedback"]["blockReason"])
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no answer")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))  # skip thinking summaries
    if not text.strip():
        raise RuntimeError("Gemini returned an empty answer (finish reason: %s)" % candidates[0].get("finishReason"))
    return _parse_reply(text)


_gemini_client = None


def _gemini_http():
    """IPv4-only HTTP client: on some networks the IPv6 route to Google hangs ~10 s and then fails;
    Google is always reachable over IPv4, so this is safe everywhere (including Render)."""
    global _gemini_client
    if _gemini_client is None:
        import httpx
        _gemini_client = httpx.Client(transport=httpx.HTTPTransport(local_address="0.0.0.0"))
    return _gemini_client


def _gemini_post(body):
    """Send the request to GEMINI_MODEL; if it is overloaded (503), out of free quota (429) or too slow,
    try the lighter GEMINI_FALLBACK_MODEL before giving up (then the offline bot answers)."""
    import httpx
    # GEMINI_FALLBACK_MODEL may list several models, comma-separated, tried in order
    models = [os.getenv("GEMINI_MODEL", "gemini-3.8-flash")] + \
        os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite,gemini-flash-lite-latest").split(",")
    headers = {"x-goog-api-key": os.getenv("GEMINI_API_KEY", "").strip()}
    problem = "no model available"
    for model in dict.fromkeys(m.strip() for m in models if m.strip()):  # unique, in order
        for attempt in range(2):  # one retry if the connection drops before Google answers
            try:
                r = _gemini_http().post(GEMINI_URL.format(model=model), headers=headers, json=body, timeout=15)
                break
            except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
                problem, r = f"{model}: connection failed ({e})", None
            except httpx.TimeoutException:
                problem, r = f"{model}: no answer within 15 seconds", None
                break
        if r is None:
            continue
        if r.status_code == 200:
            return r.json()
        try:
            detail = r.json()["error"]["message"]
        except Exception:
            detail = r.text
        problem = f"Gemini error {r.status_code} ({model}): {detail[:200]}"
        if r.status_code not in (429, 500, 503):  # e.g. bad key: a second model won't help
            break
    raise RuntimeError(problem)


# ---------- offline mock ----------
PHONE = re.compile(r"(\+?\d[\d\-\s]{8,14}\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
NAME = re.compile(r"(?:my name is|this is|mera naam|name is)\s+([A-Za-z]+)", re.I)
BUDGET = re.compile(r"(?:budget[^0-9]{0,20}|rs\.?\s*|pkr\s*)(\d(?:[\d,]*\d)?(?:\.\d+)?(?:\s*(?:k|lac|lakh|million)\b)?)", re.I)
TIMELINE = re.compile(r"(this week|next week|this month|next month|asap|urgent|jaldi|is hafte|is mahine|\d+\s*(?:weeks?|months?|days?))", re.I)
QUESTION = re.compile(
    r"\?|^\s*(how|what|when|where|which|why|do|does|can|could|is|are|will|tell|book)\b"
    r"|\b(kya|kitna|kitni|kitne|kaise|kab|kahan|price|cost|warranty|installments?)\b", re.I)
GREETING = re.compile(r"^\s*(hi|hello|hey|salam|assalam[\w\s]*|aoa)\W*$", re.I)
FIELD_LABELS = {"phone": "phone number", "need": "requirement"}
NEED = re.compile(r"(\d+\s*kw(?:\s+(?:solar|hybrid|on-grid|system|inverter))*|solar|inverter|battery|net metering|maintenance)", re.I)


def _shorten(text, limit=300):
    """Cut to whole sentences within `limit` characters."""
    if len(text) <= limit:
        return text
    out = ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        if len(out) + len(s) > limit:
            break
        out += (" " if out else "") + s
    return out or text[:limit].rsplit(" ", 1)[0] + "..."


def _respond_mock(history, context_chunks, known_lead):
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    last = user_msgs[-1] if user_msgs else ""
    full = " ".join(user_msgs)
    lead = {}
    if m := PHONE.search(full):
        lead["phone"] = re.sub(r"\s+", "", m.group(1))
    if m := EMAIL.search(full):
        lead["email"] = m.group(0)
    if m := NAME.search(full):
        lead["name"] = m.group(1).capitalize()
    if m := BUDGET.search(full):
        lead["budget"] = m.group(1).strip()
    if m := TIMELINE.search(full):
        lead["timeline"] = m.group(1).lower()
    if m := NEED.search(full):
        lead["need"] = m.group(1).strip()

    merged = {**known_lead, **lead}
    new_fields = [k for k in LEAD_FIELDS if lead.get(k) and known_lead.get(k) != lead[k]]
    if new_fields and not QUESTION.search(last):
        # visitor just shared details (no question): acknowledge them instead of quoting the KB
        name = merged.get("name")
        noted = [FIELD_LABELS.get(k, k) for k in new_fields]
        noted = ", ".join(noted[:-1]) + " and " + noted[-1] if len(noted) > 1 else noted[0]
        reply = f"Thanks{', ' + name if name else ''}! I've noted your {noted}."
    elif GREETING.match(last):
        reply = "Wa alaikum assalam! Happy to help." if re.search(r"salam", last, re.I) else "Hello! Happy to help."
    elif context_chunks:
        answer = context_chunks[0].split(": ", 1)[-1]
        reply = _shorten(answer)
    else:
        reply = "I'm not sure about that one, but a human advisor can help."
    for field, question in ASK_ORDER:
        if not merged.get(field):
            reply += " " + question
            break
    else:
        reply += ("" if reply.startswith("Thanks") else " Thanks!") + " Our advisor will call you within one working day."
    return reply.strip(), lead
