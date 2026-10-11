"""Storage. Every row belongs to one business (business_id), so each company sees only its own data.

SQLite (leadbot.db) by default, which needs no setup and works offline; set DATABASE_URL to a
PostgreSQL connection string (e.g. a free Neon database) for a live site whose data must survive
restarts. All SQL here is written once with ? placeholders and runs on both.
"""
import os
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "leadbot.db"

LEAD_FIELDS = ["name", "phone", "email", "need", "budget", "timeline"]
# Deal stage set by the business owner on the admin Pipeline board (separate from the hot/warm/cold score).
# Order = left to right on the board; won and lost close the deal.
STATUSES = ["new", "contacted", "site_visit", "quote_sent", "won", "lost"]
STATUS_NAMES = {"new": "New", "contacted": "Contacted", "site_visit": "Site visit booked",
                "quote_sent": "Quote sent", "won": "Won", "lost": "Lost"}
AUDIT_KINDS = ["lead", "kb", "auth", "system"]


# ---------- connection: SQLite or PostgreSQL ----------
def _pg_url():
    return os.getenv("DATABASE_URL", "").strip()


def is_postgres():
    return _pg_url().startswith(("postgres://", "postgresql://"))


# One shared PostgreSQL connection: opening a new one per query to a hosted database costs a network
# round trip and TLS handshake each time, which would make every chat reply seconds slower.
_pg = {"conn": None}
_pg_lock = threading.Lock()


def _pg_run(sql, args, fetch):
    import psycopg
    from psycopg.rows import dict_row
    with _pg_lock:
        for attempt in (1, 2):
            if _pg["conn"] is None or _pg["conn"].closed:
                _pg["conn"] = psycopg.connect(_pg_url(), autocommit=True, row_factory=dict_row)
            try:
                with _pg["conn"].cursor() as cur:
                    cur.execute(sql.replace("?", "%s"), args)
                    return fetch(cur) if fetch else None
            except psycopg.OperationalError:
                _pg["conn"] = None  # connection dropped (a free database sleeps when idle): reconnect once
                if attempt == 2:
                    raise


class _Conn:
    """A small wrapper so the rest of the code uses one API for both databases."""

    def __init__(self):
        self.pg = is_postgres()
        if not self.pg:
            self.c = sqlite3.connect(DB_PATH)
            self.c.row_factory = sqlite3.Row

    def run(self, sql, args=(), fetch=None):
        if self.pg:
            return _pg_run(sql, args, fetch)
        cur = self.c.cursor()
        cur.execute(sql, args)
        return fetch(cur) if fetch else cur

    def close(self):
        if not self.pg:
            self.c.commit()
            self.c.close()


def rows(sql, args=()):
    c = _Conn()
    try:
        return c.run(sql, args, lambda cur: [dict(r) for r in cur.fetchall()])
    finally:
        c.close()


def one(sql, args=()):
    found = rows(sql, args)
    return found[0] if found else None


def execute(sql, args=(), returning_id=False):
    """Run one write statement. With returning_id, returns the new row's id."""
    c = _Conn()
    try:
        if returning_id and c.pg:
            return c.run(sql + " RETURNING id", args, lambda cur: cur.fetchone()["id"])
        return c.run(sql, args, lambda cur: cur.lastrowid if returning_id else None)
    finally:
        c.close()


# ---------- schema ----------
def init():
    c = _Conn()
    pk = "SERIAL PRIMARY KEY" if c.pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    num = "DOUBLE PRECISION" if c.pg else "REAL"  # timestamps: Postgres REAL would lose seconds
    try:
        tables = [
            f"""businesses(id {pk}, slug TEXT UNIQUE, name TEXT, industry TEXT, website TEXT, bot_name TEXT,
                greeting TEXT, color TEXT, settings TEXT DEFAULT '{{}}', kb_text TEXT DEFAULT '',
                setup_done INTEGER DEFAULT 0, created {num})""",
            f"""users(id {pk}, email TEXT UNIQUE, password_hash TEXT, name TEXT, business_id INTEGER, created {num})""",
            f"""messages(id {pk}, session_id TEXT, role TEXT, content TEXT, created {num})""",
            f"""leads(session_id TEXT PRIMARY KEY, name TEXT, phone TEXT, email TEXT, need TEXT, budget TEXT, timeline TEXT,
                score INTEGER DEFAULT 0, tier TEXT DEFAULT 'cold', reason TEXT DEFAULT '', synced_at {num}, updated {num})""",
            f"""kb_faq(id {pk}, question TEXT, variants TEXT DEFAULT '', answer TEXT, source TEXT DEFAULT 'manual', created {num})""",
            f"""kb_docs(id {pk}, name TEXT, kind TEXT, origin TEXT, text TEXT, created {num})""",
            f"""audit(id {pk}, created {num}, actor TEXT, kind TEXT, action TEXT, target TEXT, detail TEXT)""",
            f"""unanswered(id {pk}, session_id TEXT, question TEXT, score {num}, created {num}, status TEXT DEFAULT 'open')""",
        ]
        for t in tables:
            c.run("CREATE TABLE IF NOT EXISTS " + t)
        # columns added after the first version; ALTER so existing databases keep working
        added = {
            "leads": ["rule_score INTEGER", "ml_score INTEGER", "status TEXT DEFAULT 'new'", "notes TEXT DEFAULT ''",
                      f"created {num}", "business_id INTEGER", "is_test INTEGER DEFAULT 0"],
            "messages": ["business_id INTEGER"], "kb_faq": ["business_id INTEGER"], "kb_docs": ["business_id INTEGER"],
            "audit": ["business_id INTEGER"], "unanswered": ["business_id INTEGER"],
        }
        for table, cols in added.items():
            for col in cols:
                if c.pg:
                    c.run(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col}")
                else:
                    try:
                        c.run(f"ALTER TABLE {table} ADD COLUMN {col}")
                    except sqlite3.OperationalError:
                        pass  # column already exists
        c.run("""UPDATE leads SET created=(SELECT MIN(m.created) FROM messages m WHERE m.session_id=leads.session_id)
                 WHERE created IS NULL""")
    finally:
        c.close()


def adopt_orphans(business_id):
    """Rows from before businesses existed belong to the first business (the original solar demo)."""
    for table in ("messages", "leads", "kb_faq", "kb_docs", "audit", "unanswered"):
        execute(f"UPDATE {table} SET business_id=? WHERE business_id IS NULL", (business_id,))


# ---------- businesses and users ----------
BUSINESS_FIELDS = ["name", "industry", "website", "bot_name", "greeting", "color", "settings", "kb_text", "setup_done"]


def create_business(slug, **fields):
    cols = ["slug", "created"] + [k for k in BUSINESS_FIELDS if k in fields]
    vals = [slug, time.time()] + [fields[k] for k in BUSINESS_FIELDS if k in fields]
    return execute(f"INSERT INTO businesses({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals, returning_id=True)


def update_business(business_id, **fields):
    for k, v in fields.items():
        if k in BUSINESS_FIELDS:
            execute(f"UPDATE businesses SET {k}=? WHERE id=?", (v, business_id))


def get_business(business_id):
    return one("SELECT * FROM businesses WHERE id=?", (business_id,))


def business_by_slug(slug):
    return one("SELECT * FROM businesses WHERE slug=?", (slug,))


def all_businesses():
    return rows("SELECT * FROM businesses ORDER BY id")


def create_user(email, password_hash, name, business_id):
    return execute("INSERT INTO users(email, password_hash, name, business_id, created) VALUES (?,?,?,?,?)",
                   (email.lower().strip(), password_hash, name, business_id, time.time()), returning_id=True)


def user_by_email(email):
    return one("SELECT * FROM users WHERE email=?", (email.lower().strip(),))


def get_user(user_id):
    return one("SELECT * FROM users WHERE id=?", (user_id,))


# ---------- chats and leads ----------
def add_message(business_id, session_id, role, content, created=None):
    execute("INSERT INTO messages(business_id, session_id, role, content, created) VALUES (?,?,?,?,?)",
            (business_id, session_id, role, content, created or time.time()))


def history(business_id, session_id, limit=12):
    found = rows("SELECT role, content FROM messages WHERE business_id=? AND session_id=? ORDER BY id DESC LIMIT ?",
                 (business_id, session_id, limit))
    return list(reversed(found))


def count_user_messages(business_id, session_id):
    return one("SELECT COUNT(*) AS n FROM messages WHERE business_id=? AND session_id=? AND role='user'",
               (business_id, session_id))["n"]


def get_lead(business_id, session_id):
    return one("SELECT * FROM leads WHERE business_id=? AND session_id=?", (business_id, session_id)) or \
        {"session_id": session_id, "business_id": business_id}


LEAD_COLS = ["session_id", "business_id"] + LEAD_FIELDS + ["score", "rule_score", "ml_score", "tier", "reason",
                                                           "synced_at", "updated", "status", "notes", "created", "is_test"]


def save_lead(lead):
    lead = dict(lead)
    lead["updated"] = lead.get("updated_override") or time.time()
    lead["created"] = lead.get("created") or lead["updated"]
    lead["status"] = lead.get("status") or "new"
    lead["notes"] = lead.get("notes") or ""
    lead["is_test"] = 1 if lead.get("is_test") else 0
    vals = [lead.get(k) for k in LEAD_COLS]
    updates = ",".join(f"{k}=excluded.{k}" for k in LEAD_COLS[1:])
    execute(f"""INSERT INTO leads({','.join(LEAD_COLS)}) VALUES ({','.join('?' * len(LEAD_COLS))})
                ON CONFLICT(session_id) DO UPDATE SET {updates}""", vals)


def update_lead(business_id, session_id, status=None, notes=None):
    """Owner edits from the admin panel. Returns False if the lead doesn't exist."""
    if status is not None:
        execute("UPDATE leads SET status=? WHERE business_id=? AND session_id=?", (status, business_id, session_id))
    if notes is not None:
        execute("UPDATE leads SET notes=? WHERE business_id=? AND session_id=?", (notes, business_id, session_id))
    return one("SELECT 1 AS ok FROM leads WHERE business_id=? AND session_id=?", (business_id, session_id)) is not None


def delete_lead(business_id, session_id):
    execute("DELETE FROM messages WHERE business_id=? AND session_id=?", (business_id, session_id))
    execute("DELETE FROM leads WHERE business_id=? AND session_id=?", (business_id, session_id))


def all_leads(business_id, include_test=False):
    # message count and last visitor message make the admin list readable at a glance
    return rows(
        f"""SELECT l.*,
             (SELECT COUNT(*) FROM messages m WHERE m.session_id=l.session_id AND m.role='user') AS messages,
             (SELECT content FROM messages m WHERE m.session_id=l.session_id AND m.role='user'
              ORDER BY id DESC LIMIT 1) AS last_message
           FROM leads l WHERE l.business_id=? {'' if include_test else 'AND COALESCE(l.is_test, 0)=0'}
           ORDER BY updated DESC""", (business_id,))


def conversation(business_id, session_id):
    return rows("SELECT role, content, created FROM messages WHERE business_id=? AND session_id=? ORDER BY id",
                (business_id, session_id))


def delete_test_leads(business_id):
    """Chats from the live preview are marked is_test; this clears them."""
    for sid in [r["session_id"] for r in rows("SELECT session_id FROM leads WHERE business_id=? AND is_test=1", (business_id,))]:
        delete_lead(business_id, sid)


# ---------- audit log ----------
def audit(business_id, kind, action, detail="", target=None, actor="owner"):
    """kind: lead | kb | auth | system. Never raises: a failed log line must not break the request."""
    try:
        execute("INSERT INTO audit(business_id, created, actor, kind, action, target, detail) VALUES (?,?,?,?,?,?,?)",
                (business_id, time.time(), actor, kind, action, target, str(detail)[:500]))
    except Exception as e:
        print("audit log failed:", e)


def audit_list(business_id, kind=None, limit=300):
    if kind in AUDIT_KINDS:
        return rows("SELECT * FROM audit WHERE business_id=? AND kind=? ORDER BY id DESC LIMIT ?", (business_id, kind, limit))
    return rows("SELECT * FROM audit WHERE business_id=? ORDER BY id DESC LIMIT ?", (business_id, limit))


# ---------- knowledge base sources ----------
def faqs(business_id):
    return rows("SELECT * FROM kb_faq WHERE business_id=? ORDER BY id DESC", (business_id,))


def docs(business_id, with_text=False):
    cols = "*" if with_text else "id, name, kind, origin, created, length(text) AS chars"
    return rows(f"SELECT {cols} FROM kb_docs WHERE business_id=? ORDER BY id DESC", (business_id,))


def add_unanswered(business_id, session_id, question, score, created=None):
    execute("INSERT INTO unanswered(business_id, session_id, question, score, created) VALUES (?,?,?,?,?)",
            (business_id, session_id, question, score, created or time.time()))


def unanswered_open(business_id):
    """Open questions grouped by text, so the same question asked 5 times shows once."""
    return rows(
        """SELECT MAX(id) AS id, MIN(question) AS question, COUNT(*) AS times, MAX(created) AS last, MIN(score) AS score
           FROM unanswered WHERE business_id=? AND status='open'
           GROUP BY lower(trim(question)) ORDER BY times DESC, last DESC""", (business_id,))


def close_unanswered(business_id, item_id, status):
    """Mark every open copy of the same question as answered or dismissed."""
    execute(
        """UPDATE unanswered SET status=? WHERE business_id=? AND status='open' AND lower(trim(question))=
           (SELECT lower(trim(question)) FROM unanswered WHERE id=?)""",
        (status, business_id, item_id),
    )
