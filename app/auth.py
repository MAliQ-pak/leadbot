"""Accounts and login for business owners.

- Passwords are stored as salted PBKDF2-SHA256 hashes (Python's hashlib), never as plain text.
- After login the browser gets a signed session cookie (HttpOnly, SameSite=Lax): it cannot be read by
  scripts and is not sent with requests that other websites start.
- 5 failed logins from one address within 15 minutes lock that address out for 15 minutes.
- Every admin request is scoped to the logged-in user's own business.
- Super admins (the agency running LeadBot, listed in SUPER_ADMINS) see every business on /agency and can
  open any business's dashboard in "support view": a second signed cookie names the business, and it is
  only honoured for the super admin it was issued to.
"""
import hashlib
import hmac
import os
import re
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request

from . import db

COOKIE = "lb_session"
VIEW_COOKIE = "lb_view"  # support view: which business a super admin is looking at
DEMO_AGENCY = "agency@leadbot.demo"
SESSION_DAYS = 7
ITERATIONS = 240_000
_KEY_FILE = Path(__file__).resolve().parent.parent / ".secret_key"
_fails = {}  # ip -> [timestamps of recent failed logins]


def _secret():
    """SECRET_KEY from the environment (set it on the host); locally, a random key kept in .secret_key."""
    key = os.getenv("SECRET_KEY", "").strip()
    if key:
        return key.encode()
    if not _KEY_FILE.exists():
        _KEY_FILE.write_text(secrets.token_hex(32))
    return _KEY_FILE.read_text().strip().encode()


# ---------- passwords ----------
def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt.hex()}${digest.hex()}"


def check_password(password, stored):
    try:
        _, iterations, salt, digest = stored.split("$")
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(test.hex(), digest)  # same time whatever the guess
    except (ValueError, AttributeError):
        return False


# ---------- sessions ----------
def make_session(user_id):
    expires = int(time.time()) + SESSION_DAYS * 86400
    body = f"{user_id}.{expires}"
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_session(token):
    try:
        user_id, expires, sig = (token or "").split(".")
        good = hmac.new(_secret(), f"{user_id}.{expires}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, good) and int(expires) > time.time():
            return int(user_id)
    except ValueError:
        pass
    return None


def set_cookie(response, request, user_id):
    response.set_cookie(COOKIE, make_session(user_id), max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https")


def client_ip(request):
    fwd = request.headers.get("x-forwarded-for", "")  # set by the host's proxy; for logs and lockout
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


# ---------- login lockout ----------
def check_lockout(request):
    ip, now = client_ip(request), time.time()
    _fails[ip] = [t for t in _fails.get(ip, []) if now - t < 900]
    if len(_fails[ip]) >= 5:
        raise HTTPException(429, "Too many failed logins. Please wait 15 minutes and try again.")


def record_failure(request):
    _fails.setdefault(client_ip(request), []).append(time.time())


# ---------- super admins (the agency) ----------
def super_admins():
    """Emails in SUPER_ADMINS (comma-separated). On a laptop with none set, the demo agency account."""
    raw = os.getenv("SUPER_ADMINS", "").strip()
    if not raw and not os.getenv("RENDER"):
        raw = DEMO_AGENCY
    # lenient: commas, semicolons, spaces or new lines between emails, and stray quotes, all work
    return {e.strip().strip("\"'").lower() for e in re.split(r"[,;\s]+", raw) if e.strip().strip("\"'")}


def is_super(user):
    return bool(user) and user["email"].lower() in super_admins()


def make_view(user_id, business_id):
    expires = int(time.time()) + 8 * 3600  # a support visit lasts a working day at most
    body = f"{user_id}.{business_id}.{expires}"
    return f"{body}.{hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()}"


def read_view(token, user_id):
    """The business id in a support-view cookie, if it was issued to this user and has not expired."""
    try:
        uid, bid, expires, sig = (token or "").split(".")
        good = hmac.new(_secret(), f"{uid}.{bid}.{expires}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, good) and int(uid) == user_id and int(expires) > time.time():
            return int(bid)
    except ValueError:
        pass
    return None


def logged_in_user(request):
    user_id = read_session(request.cookies.get(COOKIE))
    return db.get_user(user_id) if user_id else None


def agency(request: Request):
    """FastAPI dependency for /api/agency routes: the logged-in super admin, else 401/403."""
    user = logged_in_user(request)
    if not user:
        raise HTTPException(401, "Please log in.")
    if not is_super(user):
        raise HTTPException(403, "Only the LeadBot agency can open this page.")
    return user


# ---------- who is asking ----------
def current(request: Request):
    """FastAPI dependency for admin routes: {"user", "biz", "support"} of the logged-in owner, else 401.
    A super admin in support view gets the business they chose (support=True); a suspended business's
    own owner is refused."""
    user = logged_in_user(request)
    if not user:
        raise HTTPException(401, "Please log in.")
    if is_super(user):
        viewing = read_view(request.cookies.get(VIEW_COOKIE), user["id"])
        biz = db.get_business(viewing) if viewing else None
        if biz:
            return {"user": user, "biz": biz, "support": True}
    biz = db.get_business(user["business_id"]) if user["business_id"] else None
    if not biz:
        raise HTTPException(401, "Please log in.")
    if (biz.get("status") or "active") == "suspended" and not is_super(user):
        raise HTTPException(403, "This account is paused. Please contact LeadBot support.")
    return {"user": user, "biz": biz, "support": False}


def current_or_none(request):
    try:
        return current(request)
    except HTTPException:
        return None
