import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "leadbot.db"

LEAD_FIELDS = ["name", "phone", "email", "need", "budget", "timeline"]
# Deal stage set by the business owner on the admin Pipeline board (separate from the hot/warm/cold score).
# Order = left to right on the board; won and lost close the deal.
STATUSES = ["new", "contacted", "site_visit", "quote_sent", "won", "lost"]
STATUS_NAMES = {"new": "New", "contacted": "Contacted", "site_visit": "Site visit booked",
                "quote_sent": "Quote sent", "won": "Won", "lost": "Lost"}


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT, role TEXT, content TEXT, created REAL)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS leads(
                session_id TEXT PRIMARY KEY,
                name TEXT, phone TEXT, email TEXT, need TEXT, budget TEXT, timeline TEXT,
                score INTEGER DEFAULT 0, tier TEXT DEFAULT 'cold', reason TEXT DEFAULT '',
                synced_at REAL, updated REAL)"""
        )
        # columns added later; ALTER so existing leadbot.db files keep working
        for col in ("rule_score INTEGER", "ml_score INTEGER", "status TEXT DEFAULT 'new'",
                    "notes TEXT DEFAULT ''", "created REAL"):
            try:
                c.execute(f"ALTER TABLE leads ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass  # column already exists
        # Knowledge sources added from the admin panel (kb/business.md stays the main text)
        c.execute(
            """CREATE TABLE IF NOT EXISTS kb_faq(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT, variants TEXT DEFAULT '', answer TEXT, source TEXT DEFAULT 'manual', created REAL)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS kb_docs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, kind TEXT, origin TEXT, text TEXT, created REAL)"""
        )
        c.execute(  # audit log: who did what, when (owner actions + key system events)
            """CREATE TABLE IF NOT EXISTS audit(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created REAL, actor TEXT, kind TEXT, action TEXT, target TEXT, detail TEXT)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS unanswered(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT, question TEXT, score REAL, created REAL, status TEXT DEFAULT 'open')"""
        )
        c.execute(  # older leads: "first seen" = time of their first message
            """UPDATE leads SET created=(SELECT MIN(m.created) FROM messages m WHERE m.session_id=leads.session_id)
               WHERE created IS NULL"""
        )


def add_message(session_id, role, content):
    with conn() as c:
        c.execute(
            "INSERT INTO messages(session_id, role, content, created) VALUES (?,?,?,?)",
            (session_id, role, content, time.time()),
        )


def history(session_id, limit=12):
    with conn() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def count_user_messages(session_id):
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM messages WHERE session_id=? AND role='user'", (session_id,)).fetchone()[0]


def get_lead(session_id):
    with conn() as c:
        row = c.execute("SELECT * FROM leads WHERE session_id=?", (session_id,)).fetchone()
    return dict(row) if row else {"session_id": session_id}


def save_lead(lead):
    lead = dict(lead)
    lead["updated"] = time.time()
    lead["created"] = lead.get("created") or lead["updated"]
    lead["status"] = lead.get("status") or "new"
    lead["notes"] = lead.get("notes") or ""
    cols = ["session_id"] + LEAD_FIELDS + ["score", "rule_score", "ml_score", "tier", "reason",
                                           "synced_at", "updated", "status", "notes", "created"]
    vals = [lead.get(k) for k in cols]
    with conn() as c:
        c.execute(
            f"INSERT OR REPLACE INTO leads({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            vals,
        )


def update_lead(session_id, status=None, notes=None):
    """Owner edits from the admin panel. Returns False if the lead doesn't exist."""
    with conn() as c:
        if status is not None:
            c.execute("UPDATE leads SET status=? WHERE session_id=?", (status, session_id))
        if notes is not None:
            c.execute("UPDATE leads SET notes=? WHERE session_id=?", (notes, session_id))
        return c.execute("SELECT 1 FROM leads WHERE session_id=?", (session_id,)).fetchone() is not None


def delete_lead(session_id):
    with conn() as c:
        c.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        c.execute("DELETE FROM leads WHERE session_id=?", (session_id,))


def all_leads():
    # message count and last visitor message make the admin list readable at a glance
    with conn() as c:
        rows = c.execute(
            """SELECT l.*,
                 (SELECT COUNT(*) FROM messages m WHERE m.session_id=l.session_id AND m.role='user') AS messages,
                 (SELECT content FROM messages m WHERE m.session_id=l.session_id AND m.role='user'
                  ORDER BY id DESC LIMIT 1) AS last_message
               FROM leads l ORDER BY updated DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def rows(sql, args=()):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def execute(sql, args=()):
    """Run one write statement; returns the new row id (for INSERTs)."""
    with conn() as c:
        return c.execute(sql, args).lastrowid


# ---------- audit log ----------
AUDIT_KINDS = ["lead", "kb", "auth", "system"]


def audit(kind, action, detail="", target=None, actor="owner"):
    """kind: lead | kb | auth | system. Never raises: a failed log line must not break the request."""
    try:
        execute("INSERT INTO audit(created, actor, kind, action, target, detail) VALUES (?,?,?,?,?,?)",
                (time.time(), actor, kind, action, target, str(detail)[:500]))
    except sqlite3.Error as e:
        print("audit log failed:", e)


def audit_list(kind=None, limit=300):
    if kind in AUDIT_KINDS:
        return rows("SELECT * FROM audit WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, limit))
    return rows("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))


# ---------- knowledge base sources ----------
def faqs():
    return rows("SELECT * FROM kb_faq ORDER BY id DESC")


def docs(with_text=False):
    cols = "*" if with_text else "id, name, kind, origin, created, length(text) AS chars"
    return rows(f"SELECT {cols} FROM kb_docs ORDER BY id DESC")


def add_unanswered(session_id, question, score):
    execute("INSERT INTO unanswered(session_id, question, score, created) VALUES (?,?,?,?)",
            (session_id, question, score, time.time()))


def unanswered_open():
    """Open questions grouped by text, so the same question asked 5 times shows once."""
    return rows(
        """SELECT MAX(id) AS id, question, COUNT(*) AS times, MAX(created) AS last, MIN(score) AS score
           FROM unanswered WHERE status='open'
           GROUP BY lower(trim(question)) ORDER BY times DESC, last DESC"""
    )


def close_unanswered(item_id, status):
    """Mark every open copy of the same question as answered or dismissed."""
    execute(
        """UPDATE unanswered SET status=? WHERE status='open' AND lower(trim(question))=
           (SELECT lower(trim(question)) FROM unanswered WHERE id=?)""",
        (status, item_id),
    )


def conversation(session_id):
    with conn() as c:
        rows = c.execute(
            "SELECT role, content, created FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]
