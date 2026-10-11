"""Accounts and login for business owners.

- Passwords are stored as salted PBKDF2-SHA256 hashes (Python's hashlib), never as plain text.
- After login the browser gets a signed session cookie (HttpOnly, SameSite=Lax): it cannot be read by
  scripts and is not sent with requests that other websites start.
- 5 failed logins from one address within 15 minutes lock that address out for 15 minutes.
- Every admin request is scoped to the logged-in user's own business.
"""
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request

from . import db

COOKIE = "lb_session"
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


# ---------- who is asking ----------
def current(request: Request):
    """FastAPI dependency for admin routes: {"user", "biz"} of the logged-in owner, else 401."""
    user_id = read_session(request.cookies.get(COOKIE))
    user = db.get_user(user_id) if user_id else None
    biz = db.get_business(user["business_id"]) if user else None
    if not user or not biz:
        raise HTTPException(401, "Please log in.")
    return {"user": user, "biz": biz}


def current_or_none(request):
    try:
        return current(request)
    except HTTPException:
        return None
