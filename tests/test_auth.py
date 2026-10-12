"""Passwords, sessions and the login lockout."""
from fastapi.testclient import TestClient

from app import auth, main
from conftest import PASSWORD, signup


def test_passwords_are_hashed_and_salted():
    a, b = auth.hash_password("secret123"), auth.hash_password("secret123")
    assert a != b and "secret123" not in a  # random salt: same password, different hash
    assert auth.check_password("secret123", a) and not auth.check_password("wrong", a)


def test_session_cookie_cannot_be_forged():
    token = auth.make_session(5)
    assert auth.read_session(token) == 5
    user_id, expires, sig = token.split(".")
    assert auth.read_session(f"6.{expires}.{sig}") is None  # changing the user id breaks the signature
    assert auth.read_session("garbage") is None


def test_login_logout():
    client, _ = signup("Login Shop")
    fresh = TestClient(main.app)
    assert fresh.post("/api/auth/login", json={"email": client.email, "password": "nope-nope"}).status_code == 401
    assert fresh.post("/api/auth/login", json={"email": client.email, "password": PASSWORD}).status_code == 200
    assert fresh.get("/api/leads").status_code == 200
    fresh.post("/api/auth/logout")
    assert fresh.get("/api/leads").status_code == 401


def test_five_failures_lock_the_address():
    client, _ = signup("Lockout Shop")
    fresh = TestClient(main.app)
    for _ in range(5):
        fresh.post("/api/auth/login", json={"email": client.email, "password": "wrong-pass"})
    r = fresh.post("/api/auth/login", json={"email": client.email, "password": PASSWORD})
    assert r.status_code == 429  # even the right password waits out the lockout


def test_duplicate_email_is_refused():
    client, _ = signup("First Shop")
    r = TestClient(main.app).post("/api/auth/signup", json={"business_name": "Second", "industry": "blank", "website": "",
                                                            "name": "Xavier", "email": client.email, "password": PASSWORD})
    assert r.status_code == 409
