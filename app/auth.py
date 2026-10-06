"""Owner login for the admin panel, using HTTP Basic auth (the browser shows its own login box).

Set ADMIN_USER (default "admin") and ADMIN_PASSWORD. With no password set, the admin panel only
works from this computer (localhost), so a deployment can never be left open by accident.
Logins and failed logins are written to the audit log.
"""
import os
import secrets
import time

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import db

_basic = HTTPBasic(auto_error=False)
_LOCAL = {"127.0.0.1", "::1"}
# Basic auth sends the password with every request, so "logged in" is logged at most once per
# 30 minutes per user and address, and a failed login at most once a minute per address.
_last_login, _last_fail = {}, {}


def _client_ip(request):
    fwd = request.headers.get("x-forwarded-for", "")  # set by Render's proxy; for display only
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def require_admin(request: Request, creds: HTTPBasicCredentials | None = Depends(_basic)):
    """Returns the admin's name (used in the audit log) or refuses the request."""
    password = os.getenv("ADMIN_PASSWORD", "")
    if not password:
        if request.client and request.client.host in _LOCAL:
            return "owner (local)"  # local demo on your own laptop
        raise HTTPException(503, "Admin panel is locked: set ADMIN_PASSWORD on the server.")
    user = os.getenv("ADMIN_USER", "admin")
    # compare_digest takes the same time whether the guess is close or not (no timing hints)
    ok = creds is not None and \
        secrets.compare_digest(creds.username.encode(), user.encode()) and \
        secrets.compare_digest(creds.password.encode(), password.encode())
    ip, now = _client_ip(request), time.time()
    if not ok:
        if creds is not None and now - _last_fail.get(ip, 0) > 60:  # no creds = the browser's first ask
            _last_fail[ip] = now
            db.audit("auth", "Failed login", f"username '{creds.username[:40]}' from {ip}", actor="unknown")
        raise HTTPException(401, "Login required", headers={"WWW-Authenticate": 'Basic realm="LeadBot admin"'})
    if now - _last_login.get((user, ip), 0) > 1800:
        _last_login[(user, ip)] = now
        db.audit("auth", "Logged in", f"from {ip}", actor=user)
    return user


ADMIN = [Depends(require_admin)]  # use as: @app.get("/x", dependencies=auth.ADMIN)
