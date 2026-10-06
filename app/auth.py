"""Owner login for the admin panel, using HTTP Basic auth (the browser shows its own login box).

Set ADMIN_USER (default "admin") and ADMIN_PASSWORD. With no password set, the admin panel only
works from this computer (localhost), so a deployment can never be left open by accident.
"""
import os
import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_basic = HTTPBasic(auto_error=False)
_LOCAL = {"127.0.0.1", "::1"}


def require_admin(request: Request, creds: HTTPBasicCredentials | None = Depends(_basic)):
    password = os.getenv("ADMIN_PASSWORD", "")
    if not password:
        if request.client and request.client.host in _LOCAL:
            return  # local demo on your own laptop
        raise HTTPException(503, "Admin panel is locked: set ADMIN_PASSWORD on the server.")
    user = os.getenv("ADMIN_USER", "admin")
    # compare_digest takes the same time whether the guess is close or not (no timing hints)
    ok = creds is not None and \
        secrets.compare_digest(creds.username.encode(), user.encode()) and \
        secrets.compare_digest(creds.password.encode(), password.encode())
    if not ok:
        raise HTTPException(401, "Login required", headers={"WWW-Authenticate": 'Basic realm="LeadBot admin"'})


ADMIN = [Depends(require_admin)]  # use as: @app.get("/x", dependencies=auth.ADMIN)
