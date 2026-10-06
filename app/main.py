import base64
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, classifier, crm, db, ingest, llm, rag
from .scoring import score_lead, tier_for

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
KB_FILE = rag.KB_DIR / "business.md"

# Load .env if present (simple parser, no extra dependency)
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# CRM sync is off by default; leads live in the admin panel. Set CRM_ENABLED=true to turn it back on.
CRM_ENABLED = os.getenv("CRM_ENABLED", "false").lower() == "true"

app = FastAPI(title="LeadBot")
db.init()
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class ChatIn(BaseModel):
    session_id: str = Field(min_length=4, max_length=64)
    message: str = Field(min_length=1, max_length=1000)


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


@app.post("/api/chat")
def chat(body: ChatIn):
    sid, text = body.session_id, body.message.strip()
    db.add_message(sid, "user", text)
    hist = db.history(sid)

    kb = rag.get_kb()
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
        db.add_unanswered(sid, text, round(best, 3))
        context = []

    lead = db.get_lead(sid)
    # one visitor can't run up the Claude bill: long chats continue with the offline bot
    within_limit = db.count_user_messages(sid) <= int(os.getenv("MAX_CLAUDE_MESSAGES_PER_CHAT", "30"))
    reply, updates = llm.respond(hist, context, lead, allow_llm=within_limit)
    updates = {k: v for k, v in updates.items() if lead.get(k) != v}  # only genuinely new/changed
    lead.update(updates)

    all_user_text = " ".join(m["content"] for m in hist if m["role"] == "user")
    score_and_tier(lead, all_user_text)

    # Optional CRM sync when qualified; re-sync if new details arrived since last sync
    if CRM_ENABLED and crm.should_sync(lead) and (not lead.get("synced_at") or updates):
        if crm.sync(lead):
            lead["synced_at"] = time.time()

    db.add_message(sid, "assistant", reply)
    db.save_lead(lead)
    return {"reply": reply, "score": lead["score"], "tier": lead["tier"],
            "rule_score": lead["rule_score"], "ml_score": lead["ml_score"], "reason": lead["reason"],
            "lead": {k: lead.get(k) for k in db.LEAD_FIELDS}}


def score_and_tier(lead, user_text):
    """Rules plus classifier: final score is a weighted blend of both (rules only if no model)."""
    rule_score, _, reason = score_lead(lead, user_text)
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


# ---------- admin panel API ----------
@app.get("/api/leads", dependencies=auth.ADMIN)
def leads():
    return db.all_leads()


@app.patch("/api/leads/{session_id}", dependencies=auth.ADMIN)
def update_lead(session_id: str, body: LeadUpdate):
    if body.status is not None and body.status not in db.STATUSES:
        raise HTTPException(400, f"status must be one of {db.STATUSES}")
    if not db.update_lead(session_id, body.status, body.notes):
        raise HTTPException(404, "not found")
    return db.get_lead(session_id)


@app.delete("/api/leads/{session_id}", dependencies=auth.ADMIN)
def delete_lead(session_id: str):
    db.delete_lead(session_id)
    return {"ok": True}


@app.get("/api/conversations/{session_id}")
def conversation(session_id: str):
    msgs = db.conversation(session_id)
    if not msgs:
        raise HTTPException(404, "not found")
    return msgs


# ---------- knowledge base: main text, Q&A, documents, websites, unanswered ----------
# Every change calls rag.reload_kb(), so the bot uses the new knowledge on the very next message.
@app.get("/api/kb", dependencies=auth.ADMIN)
def get_kb_text():
    kb = rag.get_kb()
    counts = {}
    for c in kb.chunks:
        counts[c["source"]] = counts.get(c["source"], 0) + 1
    return {
        "text": KB_FILE.read_text(encoding="utf-8"),
        "sections": [c["section"] for c in kb.chunks if c["source"] == "text"],
        "topics": len(kb.chunks), "by_source": counts,
        "faqs": db.faqs(), "docs": db.docs(), "unanswered": db.unanswered_open(),
    }


@app.put("/api/kb", dependencies=auth.ADMIN)
def save_kb_text(body: KbIn):
    # newline="\n" keeps the file's Unix line endings on Windows too
    KB_FILE.write_text(body.text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    rag.reload_kb()
    return get_kb_text()


@app.get("/api/kb/test", dependencies=auth.ADMIN)
def test_kb(q: str):
    """What would the bot retrieve for this question? Shows the matching topics and scores."""
    found = rag.get_kb().search_scored(q[:500])
    return {
        "confident": bool(found) and found[0]["score"] >= rag.CONFIDENT, "threshold": rag.CONFIDENT,
        "matches": [{"section": c["section"], "source": c["source"], "score": round(c["score"], 3),
                     "text": c["text"]} for c in found],
    }


@app.post("/api/kb/faq", dependencies=auth.ADMIN)
def add_faq(body: FaqIn):
    db.execute("INSERT INTO kb_faq(question, variants, answer, source, created) VALUES (?,?,?,?,?)",
               (body.question.strip(), body.variants.strip(), body.answer.strip(),
                "unanswered" if body.unanswered_id else "manual", time.time()))
    if body.unanswered_id:
        db.close_unanswered(body.unanswered_id, "answered")
    rag.reload_kb()
    return get_kb_text()


@app.put("/api/kb/faq/{faq_id}", dependencies=auth.ADMIN)
def edit_faq(faq_id: int, body: FaqIn):
    db.execute("UPDATE kb_faq SET question=?, variants=?, answer=? WHERE id=?",
               (body.question.strip(), body.variants.strip(), body.answer.strip(), faq_id))
    rag.reload_kb()
    return get_kb_text()


@app.delete("/api/kb/faq/{faq_id}", dependencies=auth.ADMIN)
def delete_faq(faq_id: int):
    db.execute("DELETE FROM kb_faq WHERE id=?", (faq_id,))
    rag.reload_kb()
    return get_kb_text()


@app.post("/api/kb/upload", dependencies=auth.ADMIN)
def upload_doc(body: UploadIn):
    try:
        data = base64.b64decode(body.data, validate=True)
    except ValueError:
        raise HTTPException(400, "The file could not be read.")
    try:
        text = ingest.extract_file(body.name, data)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    return _add_doc(body.name, "file", body.name, text)


@app.post("/api/kb/url", dependencies=auth.ADMIN)
def import_url(body: UrlIn):
    try:
        title, text = ingest.fetch_url(body.url.strip())
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    return _add_doc(title[:120], "url", body.url.strip(), text)


def _add_doc(name, kind, origin, text):
    if not ingest.chunk(name, text):
        raise HTTPException(400, "No usable text found.")
    db.execute("INSERT INTO kb_docs(name, kind, origin, text, created) VALUES (?,?,?,?,?)",
               (name, kind, origin, text, time.time()))
    rag.reload_kb()
    return get_kb_text()


@app.get("/api/kb/docs/{doc_id}", dependencies=auth.ADMIN)
def get_doc(doc_id: int):
    d = db.rows("SELECT * FROM kb_docs WHERE id=?", (doc_id,))
    if not d:
        raise HTTPException(404, "not found")
    return {**d[0], "topics": [{"section": s, "text": t} for s, t in ingest.chunk(d[0]["name"], d[0]["text"])]}


@app.delete("/api/kb/docs/{doc_id}", dependencies=auth.ADMIN)
def delete_doc(doc_id: int):
    db.execute("DELETE FROM kb_docs WHERE id=?", (doc_id,))
    rag.reload_kb()
    return get_kb_text()


@app.post("/api/kb/unanswered/{item_id}/dismiss", dependencies=auth.ADMIN)
def dismiss_unanswered(item_id: int):
    db.close_unanswered(item_id, "dismissed")
    return get_kb_text()


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mode": llm.provider(),  # "claude", "gemini" or "mock" (offline bot)
        "model": llm.model_name(),
        "business": llm.BUSINESS,
        "classifier": classifier.MODEL_PATH.exists(),
        "ml_weight": float(os.getenv("ML_WEIGHT", "0.5")),
        "crm": CRM_ENABLED,
        "llm_error": llm.LAST_ERROR,  # set when the last Claude call failed and the bot fell back to mock
    }


# ---------- pages ----------
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/chat", dependencies=auth.ADMIN)
def chat_page():
    return FileResponse(STATIC / "chat.html")


@app.get("/admin", dependencies=auth.ADMIN)
def admin():
    return FileResponse(STATIC / "admin.html")
