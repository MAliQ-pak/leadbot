"""Shared test set-up. Runs before the app is imported, so the tests:
- use a throwaway SQLite file, never leadbot.db or the live PostgreSQL database;
- use the offline bot (no AI key), so they need no internet and cost nothing;
- sign cookies with a test key, so they never create the local .secret_key file.
app/main.py loads .env with setdefault, so the values set here win."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.update({
    "DATABASE_URL": "", "LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": "",
    "SEED_DEMO": "false", "CRM_ENABLED": "false", "SECRET_KEY": "test-secret-key", "ALLOW_LOCAL_URLS": "false",
})

from app import db  # noqa: E402

db.DB_PATH = Path(tempfile.mkdtemp(prefix="leadbot-tests-")) / "test.db"

from fastapi.testclient import TestClient  # noqa: E402

from app import auth, main  # noqa: E402  (creates the tables and the BrightPath business)

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def _fresh_lockout():
    auth._fails.clear()  # one test's failed logins must not lock out the next test
    yield
    auth._fails.clear()


def signup(name, industry="shoes"):
    """A logged-in client for a brand-new business. Returns (client, business)."""
    client = TestClient(main.app)
    email = f"{name.lower().replace(' ', '.')}.{os.urandom(3).hex()}@example.test"
    r = client.post("/api/auth/signup", json={"business_name": name, "industry": industry, "website": "",
                                              "name": "Owner", "email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    client.email = email
    return client, client.get("/api/me").json()["business"]


@pytest.fixture
def shop():
    return signup("Test Shoes")


@pytest.fixture
def visitor():
    return TestClient(main.app)
