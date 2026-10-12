"""LeadBot web server: the product site, sign-up and login, each business's admin API, and the public
chat API that every business's embedded bot talks to."""
import base64
import csv
import io
import json
import os
import re
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from datetime import datetime, timedelta, timezone

from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

# Load .env if present (simple parser, no extra dependency); before importing modules that read settings
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from . import auth, business, classifier, crm, db, ingest, llm, rag  # noqa: E402
from .scoring import score_lead, tier_for  # noqa: E402

# CRM sync is off by default; leads live in the admin panel. Set CRM_ENABLED=true to turn it back on.
CRM_ENABLED = os.getenv("CRM_ENABLED", "false").lower() == "true"

app = FastAPI(title="LeadBot")
db.init()
business.bootstrap()
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    """Any crash: record it in the agency's activity feed (the live server's logs are not always at hand)
    and answer with a readable message instead of a bare "Internal Server Error"."""
    detail = f"{request.method} {request.url.path}: {type(exc).__name__}: {str(exc)[:200]}"
    print("Server error:", detail)
    db.audit(None, "system", "Server error", detail, actor="server")
    return JSONResponse({"detail": "Something went wrong on the server. The LeadBot team can see the details."},
                        status_code=500)


@app.middleware("http")
async def revalidate_code(request: Request, call_next):
    """Browsers re-check pages, scripts and styles on each load, so an update reaches every website that
    embeds the widget straight away, and a dashboard never mixes an old page with a new script
    (unchanged files still come back as a cheap 304)."""
    response = await call_next(request)
    code = request.url.path.startswith("/static/") and request.url.path.endswith((".js", ".css", ".html"))
    if code or response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response

Owner = Depends(auth.current)  # admin routes: {"user", "biz"} of the logged-in owner


# ---------- request bodies ----------
class ChatIn(BaseModel):
    bot: str = Field(default="brightpath-solar", max_length=60)  # which business's bot
    session_id: str = Field(min_length=4, max_length=64)
    message: str = Field(min_length=1, max_length=1000)
    preview: bool = False  # sent by the live preview in the admin panel; kept out of the real leads


class SignupIn(BaseModel):
    business_name: str = Field(min_length=2, max_length=80)
    industry: str = Field(default="blank", max_length=30)
    website: str = Field(default="", max_length=200)
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class JoinIn(BaseModel):  # an agency team member creating their own agency login
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class BotSettingsIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    website: str | None = Field(default=None, max_length=200)
    bot_name: str | None = Field(default=None, min_length=2, max_length=40)
    greeting: str | None = Field(default=None, min_length=2, max_length=400)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    quick_replies: list[str] | None = Field(default=None, max_length=6)
    questions: dict[str, str] | None = None
    stage_names: dict[str, str] | None = None
    need_keywords: list[str] | None = Field(default=None, max_length=60)
    intent_words: list[str] | None = Field(default=None, max_length=60)
    setup_done: bool | None = None


class TemplateIn(BaseModel):
    industry: str = Field(max_length=30)


class LeadUpdate(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class KbIn(BaseModel):
    text: str = Field(min_length=1, max_length=50000)


class FaqIn(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    variants: str = Field(default="", max_length=1000)  # other ways to ask, one per line
    answer: str = Field(min_length=2, max_length=2000)
    unanswered_id: int | None = None  # set when answering a question from the Unanswered list


class UploadIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    data: str = Field(max_length=7_000_000)  # base64 file content (5 MB file ~ 6.7 MB base64)


class UrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    mode: str = Field(default="exact", pattern="^(exact|path|domain)$")  # one page, a folder, or the whole site


# ---------- the public chat API (used by every business's bot) ----------
def _bot(slug):
    biz = db.business_by_slug(slug or "")
    if not biz:
        raise HTTPException(404, "No such bot.")
    if (biz.get("status") or "active") == "suspended":  # paused by the agency
        raise HTTPException(403, "This chat is not available right now.")
    return biz


def _llm_biz(biz):
    return {"name": biz["name"], "bot_name": biz["bot_name"], "settings": business.settings(biz)}


@app.get("/api/bot/{slug}")
def bot_config(slug: str):
    return business.public_config(_bot(slug))


@app.get("/api/templates")
def templates():
    """The industry templates offered at sign-up and in the setup wizard."""
    return [{"key": k, "label": t["label"], "blurb": t.get("blurb", "")} for k, t in business.TEMPLATES.items()]


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    biz = _bot(body.bot)
    bid, sid, text = biz["id"], body.session_id, body.message.strip()
    owner = auth.current_or_none(request)
    is_test = body.preview and owner is not None and owner["biz"]["id"] == bid  # only the owner's preview
    other = db.one("SELECT business_id FROM leads WHERE session_id=?", (sid,))
    if other and other["business_id"] != bid:  # a chat id belongs to one business; never move a lead to another
        raise HTTPException(409, "This chat belongs to another bot. Please start a new chat.")
    db.add_message(bid, sid, "user", text)
    hist = db.history(bid, sid)

    kb = rag.get_kb(bid)
    found = kb.search_scored(text)
    best = found[0]["score"] if found else 0
    if best < rag.CONFIDENT and len(text.split()) <= 3:
        # short follow-up ("and the warranty?"): retry with the last two user turns
        user_turns = [m["content"] for m in hist if m["role"] == "user"]
        retry = kb.search_scored(" ".join(user_turns[-2:]))
        if retry and retry[0]["score"] > best:
            found, best = retry, retry[0]["score"]
    context = [c["text"] for c in found if c["score"] >= 0.12]

    # A question the knowledge base can't confidently answer: don't guess, and show it to the
    # owner under "Unanswered" so they can teach the bot the answer.
    if best < rag.CONFIDENT and llm.QUESTION.search(text) and not llm.GREETING.match(text):
        db.add_unanswered(bid, sid, text, round(best, 3))
        context = []

    lead = db.get_lead(bid, sid)
    is_new, was_tier = "created" not in lead, lead.get("tier")
    lead["is_test"] = lead.get("is_test") or is_test
    # one visitor can't run up the AI bill: long chats continue with the offline bot
    within_limit = db.count_user_messages(bid, sid) <= int(os.getenv("MAX_CLAUDE_MESSAGES_PER_CHAT", "30"))
    llm_biz = _llm_biz(biz)
    reply, updates = llm.respond(hist, context, lead, llm_biz, allow_llm=within_limit)
    _audit_ai_failure(bid)
    updates = {k: v for k, v in updates.items() if lead.get(k) != v}  # only genuinely new/changed
    lead.update(updates)

    all_user_text = " ".join(m["content"] for m in hist if m["role"] == "user")
    score_and_tier(lead, all_user_text, llm_biz["settings"])

    # Optional CRM sync when qualified; re-sync if new details arrived since last sync
    if CRM_ENABLED and not lead["is_test"] and crm.should_sync(lead) and (not lead.get("synced_at") or updates):
        if crm.sync(lead):
            lead["synced_at"] = time.time()

    db.add_message(bid, sid, "assistant", reply)
    db.save_lead(lead)
    if is_new and not lead["is_test"]:
        db.audit(bid, "lead", "New lead", f"first message: {text[:80]}", target=sid, actor="visitor")
    if lead["tier"] == "hot" and was_tier != "hot" and not lead["is_test"]:
        db.audit(bid, "lead", "Lead turned hot", f"{_who_is(lead)} scored {lead['score']}", target=sid, actor="system")
    return {"reply": reply, "score": lead["score"], "tier": lead["tier"],
            "rule_score": lead["rule_score"], "ml_score": lead["ml_score"], "reason": lead["reason"],
            "lead": {k: lead.get(k) for k in db.LEAD_FIELDS}}


@app.get("/api/conversations/{session_id}")
def conversation(session_id: str, bot: str = "brightpath-solar"):
    return db.conversation(_bot(bot)["id"], session_id) or []  # a new visitor simply has no history yet


_logged_error = None


def _audit_ai_failure(business_id):
    """Log an AI failure once (the 60 s cool-down means at most one entry a minute)."""
    global _logged_error
    if llm.LAST_ERROR is not None and llm.LAST_ERROR is not _logged_error:
        _logged_error = llm.LAST_ERROR
        db.audit(business_id, "system", "AI failed, offline bot answered", llm.LAST_ERROR["message"], actor="system")


def _who_is(lead):
    return lead.get("name") or lead.get("phone") or "Anonymous visitor"


def score_and_tier(lead, user_text, settings=None):
    """Rules plus classifier: final score is a weighted blend of both (rules only if no model)."""
    rule_score, _, reason = score_lead(lead, user_text, (settings or {}).get("intent_words") or ())
    prob = classifier.predict(lead, user_text)
    lead["rule_score"] = rule_score
    if prob is None:
        lead["ml_score"], final = None, rule_score
    else:
        w = float(os.getenv("ML_WEIGHT", "0.5"))
        lead["ml_score"] = round(prob * 100)
        final = round((1 - w) * rule_score + w * lead["ml_score"])
        reason += f"; model: {lead['ml_score']}% likely qualified"
    lead["score"], lead["tier"], lead["reason"] = final, tier_for(final), reason


# ---------- sign-up and login ----------
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.post("/api/auth/signup")
def signup(body: SignupIn, request: Request):
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(400, "Please enter a valid email address.")
    if db.user_by_email(email):
        raise HTTPException(409, "An account with this email already exists. Please log in.")
    bid = business.create_from_template(body.business_name.strip(), body.industry, body.website.strip())
    uid = db.create_user(email, auth.hash_password(body.password), body.name.strip(), bid)
    db.audit(bid, "auth", "Account created", f"{body.name.strip()} ({email}), template: {body.industry}", actor=email)
    response = JSONResponse({"ok": True, "next": "/app/setup"})
    auth.set_cookie(response, request, uid)
    return response


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request):
    auth.check_lockout(request)
    user = db.user_by_email(body.email)
    if not user or not auth.check_password(body.password, user["password_hash"]):
        auth.record_failure(request)
        if user:
            db.audit(user["business_id"], "auth", "Failed login", f"from {auth.client_ip(request)}", actor="unknown")
        raise HTTPException(401, "Wrong email or password.")
    biz = db.get_business(user["business_id"]) if user["business_id"] else None
    if not biz and not auth.is_super(user):  # an agency-only account whose email is not in SUPER_ADMINS
        raise HTTPException(403, "This is an agency account, but its email is not in the SUPER_ADMINS setting on the server.")
    if biz and (biz.get("status") or "active") == "suspended" and not auth.is_super(user):
        raise HTTPException(403, "This account is paused. Please contact LeadBot support.")
    db.audit(biz["id"] if biz else None, "auth", "Logged in", f"from {auth.client_ip(request)}", actor=user["email"])
    nxt = "/agency" if auth.is_super(user) else "/app" if biz["setup_done"] else "/app/setup"
    response = JSONResponse({"ok": True, "next": nxt})
    auth.set_cookie(response, request, user["id"])
    response.delete_cookie(auth.VIEW_COOKIE)  # every log-in starts outside support view
    return response


@app.post("/api/auth/join")
def join_agency(body: JoinIn, request: Request):
    """An email listed in SUPER_ADMINS can create its own agency login (no business attached), once.
    Every other email is refused, so this cannot be used to make yourself an admin."""
    email = body.email.strip().lower()
    if email not in auth.super_admins():
        raise HTTPException(403, "This email is not on the LeadBot agency list. Ask the agency to add it to SUPER_ADMINS.")
    if db.user_by_email(email):
        raise HTTPException(409, "This email already has an account. Please log in.")
    uid = db.create_user(email, auth.hash_password(body.password), body.name.strip(), None)
    db.audit(None, "auth", "Agency member joined", f"{body.name.strip()} ({email})", actor=email)
    response = JSONResponse({"ok": True, "next": "/agency"})
    auth.set_cookie(response, request, uid)
    return response


@app.post("/api/auth/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE)
    response.delete_cookie(auth.VIEW_COOKIE)
    return response


# ---------- the business: who am I, bot settings, templates ----------
@app.get("/api/me")
def me(ctx=Owner):
    biz, user = ctx["biz"], ctx["user"]
    return {"user": {"name": user["name"], "email": user["email"]},
            "agency": auth.is_super(user), "support": bool(ctx.get("support")),
            "business": {**{k: biz[k] for k in ("id", "slug", "name", "industry", "website", "bot_name", "greeting",
                                                "color", "setup_done")},
                         "settings": business.settings(biz)},
            "templates": {k: t["label"] for k, t in business.TEMPLATES.items()},
            "template_blurbs": {k: t.get("blurb", "") for k, t in business.TEMPLATES.items()}}


@app.put("/api/business")
def update_bot(body: BotSettingsIn, ctx=Owner):
    biz = ctx["biz"]
    fields = {k: v for k, v in body.model_dump().items()
              if v is not None and k in ("name", "website", "bot_name", "greeting", "color")}
    s = business.settings(biz)
    for k in ("quick_replies", "questions", "need_keywords", "intent_words", "stage_names"):
        value = getattr(body, k)
        if value is not None:
            s[k] = [x.strip() for x in value if x.strip()] if isinstance(value, list) else \
                {f: q.strip() for f, q in value.items() if f in (db.STATUSES if k == "stage_names" else db.LEAD_FIELDS) and q.strip()}
    fields["settings"] = json.dumps(s)
    if body.setup_done is not None:
        fields["setup_done"] = 1 if body.setup_done else 0
    db.update_business(biz["id"], **fields)
    db.audit(biz["id"], "kb", "Bot settings updated", ", ".join(k for k in body.model_dump(exclude_none=True)), actor=ctx["user"]["email"])
    return me({"user": ctx["user"], "biz": db.get_business(biz["id"])})


@app.post("/api/business/template")
def apply_template(body: TemplateIn, ctx=Owner):
    """Replace the bot's settings and main text with an industry template (Q&A and documents stay)."""
    if body.industry not in business.TEMPLATES:
        raise HTTPException(400, "Unknown template.")
    biz, t = ctx["biz"], business.template(body.industry)
    db.update_business(biz["id"], industry=body.industry, bot_name=business.template_bot_name(body.industry, biz["name"]),
                       greeting=t["greeting"], color=t["color"],
                       settings=json.dumps(business.settings_from_template(body.industry)),
                       kb_text=business.template_kb(body.industry, biz["name"]))
    rag.reload_kb(biz["id"])
    db.audit(biz["id"], "kb", "Template applied", t["label"], actor=ctx["user"]["email"])
    return me({"user": ctx["user"], "biz": db.get_business(biz["id"])})


@app.delete("/api/preview-chats")
def clear_preview(ctx=Owner):
    db.delete_test_leads(ctx["biz"]["id"])
    return {"ok": True}


# ---------- leads ----------
@app.get("/api/leads")
def leads(ctx=Owner):
    return db.all_leads(ctx["biz"]["id"])


@app.patch("/api/leads/{session_id}")
def update_lead(session_id: str, body: LeadUpdate, ctx=Owner):
    bid, who = ctx["biz"]["id"], ctx["user"]["email"]
    if body.status is not None and body.status not in db.STATUSES:
        raise HTTPException(400, f"status must be one of {db.STATUSES}")
    before = db.get_lead(bid, session_id)
    if not db.update_lead(bid, session_id, body.status, body.notes):
        raise HTTPException(404, "not found")
    if body.status is not None and body.status != before.get("status"):
        names = business.settings(ctx["biz"])["stage_names"]
        db.audit(bid, "lead", "Stage changed", f"{_who_is(before)}: {names.get(before.get('status'), before.get('status'))} → {names[body.status]}", session_id, who)
    if body.notes is not None and body.notes != (before.get("notes") or ""):
        db.audit(bid, "lead", "Notes edited", _who_is(before), session_id, who)
    return db.get_lead(bid, session_id)


CSV_COLUMNS = [  # (header, how to get it from a lead)
    ("Name", "name"), ("Phone", "phone"), ("Email", "email"), ("Need", "need"), ("Budget", "budget"),
    ("Timeline", "timeline"), ("Tier", "tier"), ("Score", "score"), ("Rules score", "rule_score"),
    ("Model score", "ml_score"), ("Why", "reason"), ("Stage", "status"), ("Notes", "notes"), ("Messages", "messages"),
    ("First seen", "created"), ("Last active", "updated"), ("Last message", "last_message"),
]


def _csv_cell(value):
    """Text a visitor typed must stay text: a cell starting with = + - @ would run as a formula in Excel."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@app.get("/api/leads.csv")
def export_leads(tz: int = 0, ctx=Owner):
    """All of this business's leads as a spreadsheet. tz = the browser's getTimezoneOffset() in minutes,
    so times appear in the owner's own clock (Pakistan is -300, i.e. UTC+5)."""
    biz = ctx["biz"]
    stages = business.settings(biz)["stage_names"]
    zone = timezone(timedelta(minutes=-max(-840, min(840, tz))))
    when = lambda ts: datetime.fromtimestamp(ts, zone).strftime("%Y-%m-%d %H:%M") if ts else ""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([h for h, _ in CSV_COLUMNS])
    leads = db.all_leads(biz["id"])
    for lead in leads:
        row = []
        for _, key in CSV_COLUMNS:
            v = lead.get(key)
            if key == "status":
                v = stages.get(v or "new", v)
            elif key in ("created", "updated"):
                v = when(v)
            row.append(_csv_cell(v))
        writer.writerow(row)
    db.audit(biz["id"], "lead", "Leads exported", f"{len(leads)} leads as CSV", actor=ctx["user"]["email"])
    name = f"leads-{biz['slug']}-{datetime.now(zone).strftime('%Y-%m-%d')}.csv"
    # the byte-order mark tells Excel the file is UTF-8, so Urdu text and "Rs" amounts show correctly
    return Response("\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/leads/{session_id}/whatsapp")
def log_whatsapp(session_id: str, ctx=Owner):
    """The owner opened WhatsApp to message this lead (the message itself is sent from WhatsApp)."""
    bid = ctx["biz"]["id"]
    lead = db.get_lead(bid, session_id)
    if "created" not in lead:
        raise HTTPException(404, "not found")
    db.audit(bid, "lead", "WhatsApp opened", _who_is(lead), session_id, ctx["user"]["email"])
    return {"ok": True}


@app.delete("/api/leads/{session_id}")
def delete_lead(session_id: str, ctx=Owner):
    bid = ctx["biz"]["id"]
    before = db.get_lead(bid, session_id)
    if "created" not in before:  # not a lead of this business (get_lead returns a stub for unknown ids)
        raise HTTPException(404, "not found")
    db.delete_lead(bid, session_id)
    db.audit(bid, "lead", "Lead deleted", _who_is(before), session_id, ctx["user"]["email"])
    return {"ok": True}


@app.get("/api/admin/conversations/{session_id}")
def admin_conversation(session_id: str, ctx=Owner):
    return db.conversation(ctx["biz"]["id"], session_id)


# ---------- knowledge base: main text, Q&A, documents, websites, unanswered ----------
# Every change calls rag.reload_kb(), so the bot uses the new knowledge on the very next message.
@app.get("/api/kb")
def get_kb_text(ctx=Owner):
    bid = ctx["biz"]["id"]
    kb = rag.get_kb(bid)
    counts = {}
    for c in kb.chunks:
        counts[c["source"]] = counts.get(c["source"], 0) + 1
    return {
        "text": db.get_business(bid)["kb_text"] or "",
        "sections": [c["section"] for c in kb.chunks if c["source"] == "text"],
        "topics": len(kb.chunks), "by_source": counts,
        "faqs": db.faqs(bid), "docs": db.docs(bid), "unanswered": db.unanswered_open(bid),
    }


@app.put("/api/kb")
def save_kb_text(body: KbIn, ctx=Owner):
    bid = ctx["biz"]["id"]
    db.update_business(bid, kb_text=body.text.replace("\r\n", "\n"))
    rag.reload_kb(bid)
    db.audit(bid, "kb", "Main text edited", f"{len(body.text)} characters", "main text", ctx["user"]["email"])
    return get_kb_text(ctx)


@app.get("/api/kb/test")
def test_kb(q: str, ctx=Owner):
    """What would the bot retrieve for this question? Shows the matching topics and scores."""
    found = rag.get_kb(ctx["biz"]["id"]).search_scored(q[:500])
    return {
        "confident": bool(found) and found[0]["score"] >= rag.CONFIDENT, "threshold": rag.CONFIDENT,
        "matches": [{"section": c["section"], "source": c["source"], "score": round(c["score"], 3),
                     "text": c["text"]} for c in found],
    }


@app.post("/api/kb/faq")
def add_faq(body: FaqIn, ctx=Owner):
    bid, who = ctx["biz"]["id"], ctx["user"]["email"]
    db.execute("INSERT INTO kb_faq(business_id, question, variants, answer, source, created) VALUES (?,?,?,?,?,?)",
               (bid, body.question.strip(), body.variants.strip(), body.answer.strip(),
                "unanswered" if body.unanswered_id else "manual", time.time()))
    if body.unanswered_id:
        db.close_unanswered(bid, body.unanswered_id, "answered")
    db.audit(bid, "kb", "Answered a visitor question" if body.unanswered_id else "Q&A added", body.question.strip(), actor=who)
    rag.reload_kb(bid)
    return get_kb_text(ctx)


@app.put("/api/kb/faq/{faq_id}")
def edit_faq(faq_id: int, body: FaqIn, ctx=Owner):
    bid = ctx["biz"]["id"]
    db.execute("UPDATE kb_faq SET question=?, variants=?, answer=? WHERE id=? AND business_id=?",
               (body.question.strip(), body.variants.strip(), body.answer.strip(), faq_id, bid))
    db.audit(bid, "kb", "Q&A edited", body.question.strip(), str(faq_id), ctx["user"]["email"])
    rag.reload_kb(bid)
    return get_kb_text(ctx)


@app.delete("/api/kb/faq/{faq_id}")
def delete_faq(faq_id: int, ctx=Owner):
    bid = ctx["biz"]["id"]
    old = db.one("SELECT question FROM kb_faq WHERE id=? AND business_id=?", (faq_id, bid))
    db.execute("DELETE FROM kb_faq WHERE id=? AND business_id=?", (faq_id, bid))
    db.audit(bid, "kb", "Q&A deleted", old["question"] if old else f"id {faq_id}", str(faq_id), ctx["user"]["email"])
    rag.reload_kb(bid)
    return get_kb_text(ctx)


@app.post("/api/kb/upload")
def upload_doc(body: UploadIn, ctx=Owner):
    try:
        data = base64.b64decode(body.data, validate=True)
    except ValueError:
        raise HTTPException(400, "The file could not be read.")
    try:
        text = ingest.extract_file(body.name, data)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    result = _add_doc(ctx, body.name, "file", body.name, text)
    db.audit(ctx["biz"]["id"], "kb", "Document uploaded", f"{body.name} ({len(text)} characters)", actor=ctx["user"]["email"])
    return result


@app.post("/api/kb/url")
def import_url(body: UrlIn, ctx=Owner):
    """Import one page, every page under its folder, or the whole website (up to 30 pages, 60 seconds).
    Each page is stored as its own document; importing a page again replaces the old copy."""
    bid, url = ctx["biz"]["id"], body.url.strip()
    try:
        pages, notes = ingest.crawl(url, body.mode)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    imported = []
    for page_url, title, text in pages:
        if not ingest.chunk(title, text):
            continue
        db.execute("DELETE FROM kb_docs WHERE business_id=? AND kind='url' AND origin=?", (bid, page_url))
        db.execute("INSERT INTO kb_docs(business_id, name, kind, origin, text, created) VALUES (?,?,?,?,?,?)",
                   (bid, title[:120], "url", page_url, text, time.time()))
        imported.append({"url": page_url, "title": title[:120]})
    if not imported:
        raise HTTPException(400, "No usable text found.")
    rag.reload_kb(bid)
    what = {"exact": "Web page imported", "path": "Website section imported", "domain": "Website imported"}[body.mode]
    db.audit(bid, "kb", what, f"{url} ({len(imported)} page{'s' if len(imported) != 1 else ''})", actor=ctx["user"]["email"])
    return {**get_kb_text(ctx), "imported": imported, "notes": notes}


def _add_doc(ctx, name, kind, origin, text):
    bid = ctx["biz"]["id"]
    if not ingest.chunk(name, text):
        raise HTTPException(400, "No usable text found.")
    db.execute("INSERT INTO kb_docs(business_id, name, kind, origin, text, created) VALUES (?,?,?,?,?,?)",
               (bid, name, kind, origin, text, time.time()))
    rag.reload_kb(bid)
    return get_kb_text(ctx)


@app.get("/api/kb/docs/{doc_id}")
def get_doc(doc_id: int, ctx=Owner):
    d = db.one("SELECT * FROM kb_docs WHERE id=? AND business_id=?", (doc_id, ctx["biz"]["id"]))
    if not d:
        raise HTTPException(404, "not found")
    return {**d, "topics": [{"section": s, "text": t} for s, t in ingest.chunk(d["name"], d["text"])]}


@app.delete("/api/kb/docs/{doc_id}")
def delete_doc(doc_id: int, ctx=Owner):
    bid = ctx["biz"]["id"]
    old = db.one("SELECT name FROM kb_docs WHERE id=? AND business_id=?", (doc_id, bid))
    db.execute("DELETE FROM kb_docs WHERE id=? AND business_id=?", (doc_id, bid))
    db.audit(bid, "kb", "Document deleted", old["name"] if old else f"id {doc_id}", str(doc_id), ctx["user"]["email"])
    rag.reload_kb(bid)
    return get_kb_text(ctx)


@app.post("/api/kb/unanswered/{item_id}/dismiss")
def dismiss_unanswered(item_id: int, ctx=Owner):
    bid = ctx["biz"]["id"]
    old = db.one("SELECT question FROM unanswered WHERE id=? AND business_id=?", (item_id, bid))
    db.close_unanswered(bid, item_id, "dismissed")
    db.audit(bid, "kb", "Unanswered question dismissed", old["question"] if old else "", str(item_id), ctx["user"]["email"])
    return get_kb_text(ctx)


@app.get("/api/audit")
def audit_log(kind: str | None = None, ctx=Owner):
    return db.audit_list(ctx["biz"]["id"], kind)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mode": llm.provider(),  # "claude", "gemini" or "mock" (offline bot)
        "model": llm.model_name(),
        "classifier": classifier.MODEL_PATH.exists(),
        "ml_weight": float(os.getenv("ML_WEIGHT", "0.5")),
        "crm": CRM_ENABLED,
        "database": "postgres" if db.is_postgres() else "sqlite",
        "llm_error": llm.LAST_ERROR,  # set when the last AI call failed and the bot fell back to mock
    }


# ---------- pages ----------
def _page(name):
    return FileResponse(STATIC / name)


@app.get("/")
def landing():
    return _page("landing.html")


@app.get("/signup")
def signup_page():
    return _page("auth.html")


@app.get("/login")
def login_page():
    return _page("auth.html")


@app.get("/join")
def join_page():
    return _page("auth.html")


# ---------- the agency: every business at once (super admins only) ----------
Agency = Depends(auth.agency)


class StatusIn(BaseModel):
    status: str = Field(pattern="^(active|suspended)$")


class ConfirmIn(BaseModel):
    confirm: str = Field(max_length=120)  # the business's name, typed by the super admin


def _agency_business(bid):
    biz = db.get_business(bid)
    if not biz:
        raise HTTPException(404, "No such business.")
    return biz


@app.get("/api/agency/overview")
def agency_overview(user=Agency):
    day = datetime.now(timezone(timedelta(hours=5))).replace(hour=0, minute=0, second=0, microsecond=0)  # Pakistan
    rows = db.business_summaries(day.timestamp())
    totals = {k: sum(r[k] or 0 for r in rows) for k in ("leads", "hot", "won", "chats_today")}
    totals.update(businesses=len(rows), suspended=sum(r["status"] == "suspended" for r in rows))
    return {"you": user["email"], "totals": totals, "businesses": rows,
            "ai": {"mode": llm.provider(), "error": llm.LAST_ERROR}}


@app.get("/api/agency/activity")
def agency_activity(user=Agency):
    return db.audit_all()


@app.post("/api/agency/view/{bid}")
def agency_view(bid: int, request: Request, user=Agency):
    """Open a business's dashboard as its owner sees it ("support view"). Logged in that business's audit."""
    biz = _agency_business(bid)
    db.audit(bid, "auth", "Agency support view opened", f"by {user['email']}", actor=user["email"])
    response = JSONResponse({"ok": True, "next": "/app" if biz["setup_done"] else "/app/setup"})
    response.set_cookie(auth.VIEW_COOKIE, auth.make_view(user["id"], bid), max_age=8 * 3600, httponly=True,
                        samesite="lax", secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https")
    return response


@app.post("/api/agency/view-exit")
def agency_view_exit(user=Agency):
    response = JSONResponse({"ok": True, "next": "/agency"})
    response.delete_cookie(auth.VIEW_COOKIE)
    return response


@app.post("/api/agency/businesses/{bid}/status")
def agency_set_status(bid: int, body: StatusIn, user=Agency):
    """Suspend: the bot stops answering and the owner cannot log in. Reactivate undoes it. Nothing is deleted."""
    biz = _agency_business(bid)
    db.update_business(bid, status=body.status)
    action = "Business suspended by the agency" if body.status == "suspended" else "Business reactivated by the agency"
    db.audit(bid, "system", action, biz["name"], actor=user["email"])
    return {"ok": True, "status": body.status}


@app.post("/api/agency/businesses/{bid}/delete")  # POST, not DELETE: some proxies drop a DELETE's body
def agency_delete(bid: int, body: ConfirmIn, user=Agency):
    """Permanently delete a business and all its data. The exact business name must be typed to confirm."""
    biz = _agency_business(bid)
    if body.confirm.strip() != biz["name"]:
        raise HTTPException(400, "Type the business name exactly to confirm.")
    if user["business_id"] == bid:
        raise HTTPException(400, "You cannot delete the business your own account belongs to.")
    db.delete_business(bid)
    rag._kbs.pop(bid, None)  # forget its search index
    db.audit(None, "system", "Business deleted by the agency", f"{biz['name']} ({biz['slug']})", actor=user["email"])
    return {"ok": True}


@app.get("/agency")
def agency_page(request: Request):
    user = auth.logged_in_user(request)
    if not user:
        return RedirectResponse("/login")
    return _page("agency.html") if auth.is_super(user) else RedirectResponse("/app")


@app.get("/app")
def admin_page(request: Request):
    ctx = auth.current_or_none(request)
    if not ctx:
        user = auth.logged_in_user(request)  # an agency account with no business of its own
        return RedirectResponse("/agency" if auth.is_super(user) else "/login")
    return _page("admin.html") if ctx["biz"]["setup_done"] else RedirectResponse("/app/setup")


@app.get("/app/setup")
def setup_page(request: Request):
    return _page("setup.html") if auth.current_or_none(request) else RedirectResponse("/login")


@app.get("/admin")
def old_admin():
    return RedirectResponse("/app")


@app.get("/bot/{slug}")
def bot_page(slug: str):
    _bot(slug)
    return _page("bot.html")  # the chat window that runs inside the iframe on a business's website


@app.get("/demo/{slug}")
def demo_site(slug: str):
    pages = {"brightpath-solar": "demo/brightpath.html", "stride-shoes": "demo/stride.html"}
    if slug not in pages:
        raise HTTPException(404, "not found")
    return _page(pages[slug])


# Demo data for presentations: with SEED_DEMO=true an empty database is filled with fictional
# businesses and leads at start-up (Render's free tier starts empty after every restart). See app/seed.py.
if os.getenv("SEED_DEMO", "false").lower() == "true":
    from . import seed as _seed
    _seed.seed_if_empty()
