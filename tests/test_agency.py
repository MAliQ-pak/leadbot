"""The agency (super admin) view: only super admins get in, support view is scoped and logged,
suspend really stops the bot and the owner, and delete removes everything."""
from fastapi.testclient import TestClient

from app import auth, db, main
from conftest import PASSWORD, signup


def agency_client(monkeypatch):
    """A logged-in super admin with no business of their own, like agency@leadbot.demo."""
    email = f"boss.{len(db.rows('SELECT id FROM users'))}@agency.test"
    db.create_user(email, auth.hash_password(PASSWORD), "Agency", None)
    monkeypatch.setenv("SUPER_ADMINS", email)
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200 and r.json()["next"] == "/agency"
    return c


def test_only_super_admins_get_in(monkeypatch, shop, visitor):
    owner, _ = shop
    monkeypatch.setenv("SUPER_ADMINS", "someone-else@agency.test")
    assert visitor.get("/api/agency/overview").status_code == 401
    assert owner.get("/api/agency/overview").status_code == 403  # a business owner is not the agency
    assert owner.post("/api/agency/view/1").status_code == 403
    assert owner.get("/agency", follow_redirects=False).headers["location"] == "/app"


def test_overview_lists_every_business(monkeypatch, visitor):
    _, biz = signup("Agency Listed Shoes")
    visitor.post("/api/chat", json={"bot": biz["slug"], "session_id": "sess-ag-1", "message": "I am Ali 03001234567"})
    data = agency_client(monkeypatch).get("/api/agency/overview").json()
    row = next(b for b in data["businesses"] if b["id"] == biz["id"])
    assert row["owner"].startswith("agency.listed.shoes") and row["leads"] == 1 and row["status"] == "active"
    assert data["totals"]["businesses"] == len(data["businesses"])


def test_support_view_opens_that_business_and_is_logged(monkeypatch, visitor):
    owner, biz = signup("Support Shoes")
    visitor.post("/api/chat", json={"bot": biz["slug"], "session_id": "sess-ag-2", "message": "I am Sara 03211234567"})
    ag = agency_client(monkeypatch)
    assert ag.get("/api/leads").status_code == 401  # no business of its own until it opens one
    assert ag.post(f"/api/agency/view/{biz['id']}").status_code == 200
    me = ag.get("/api/me").json()
    assert me["support"] and me["agency"] and me["business"]["id"] == biz["id"]
    assert any(l["session_id"] == "sess-ag-2" for l in ag.get("/api/leads").json())
    assert any(e["action"] == "Agency support view opened" for e in owner.get("/api/audit").json())  # the owner can see it
    ag.post("/api/agency/view-exit")
    assert ag.get("/api/leads").status_code == 401


def test_support_view_cookie_cannot_be_reused_by_an_owner(monkeypatch, shop):
    owner, _ = shop
    _, other = signup("Victim Clinic", "clinic")
    agency_client(monkeypatch)
    token = auth.make_view(999999, other["id"])  # issued to a different user
    owner.cookies.set(auth.VIEW_COOKIE, token)
    assert owner.get("/api/me").json()["business"]["id"] != other["id"]


def test_suspend_stops_the_bot_and_the_owner(monkeypatch, visitor):
    owner, biz = signup("Paused Salon", "salon")
    ag = agency_client(monkeypatch)
    assert ag.post(f"/api/agency/businesses/{biz['id']}/status", json={"status": "suspended"}).status_code == 200
    assert visitor.get(f"/api/bot/{biz['slug']}").status_code == 403
    assert visitor.post("/api/chat", json={"bot": biz["slug"], "session_id": "sess-ag-3", "message": "hi"}).status_code == 403
    assert owner.get("/api/leads").status_code == 403  # the owner's open session stops working
    assert TestClient(main.app).post("/api/auth/login", json={"email": owner.email, "password": PASSWORD}).status_code == 403
    assert ag.post(f"/api/agency/businesses/{biz['id']}/status", json={"status": "active"}).status_code == 200
    assert visitor.get(f"/api/bot/{biz['slug']}").status_code == 200 and owner.get("/api/leads").status_code == 200
    assert ag.post(f"/api/agency/businesses/{biz['id']}/status", json={"status": "gone"}).status_code == 422


def test_delete_needs_the_exact_name_and_removes_everything(monkeypatch, visitor):
    owner, biz = signup("Doomed Academy", "academy")
    visitor.post("/api/chat", json={"bot": biz["slug"], "session_id": "sess-ag-4", "message": "I am Hina 03331234567"})
    ag = agency_client(monkeypatch)
    url = f"/api/agency/businesses/{biz['id']}/delete"
    assert ag.post(url, json={"confirm": "doomed academy"}).status_code == 400  # must match exactly
    assert ag.post(url, json={"confirm": "Doomed Academy"}).status_code == 200
    assert db.get_business(biz["id"]) is None and db.user_by_email(owner.email) is None
    for table in ("leads", "messages", "audit"):
        assert not db.rows(f"SELECT 1 AS x FROM {table} WHERE business_id=?", (biz["id"],))
    assert visitor.get(f"/api/bot/{biz['slug']}").status_code == 404
    assert any(e["action"] == "Business deleted by the agency" for e in ag.get("/api/agency/activity").json())


def test_super_admins_list_is_read_leniently(monkeypatch):
    monkeypatch.setenv("SUPER_ADMINS", ' "Agency@LeadBot.demo" ; ali@example.com,  sara@example.com\nhamza@example.com ')
    assert auth.super_admins() == {"agency@leadbot.demo", "ali@example.com", "sara@example.com", "hamza@example.com"}


def test_agency_account_not_on_the_list_gets_a_clear_message(monkeypatch):
    """Regression: this used to crash the server (500) instead of explaining what is wrong."""
    email = "orphan@agency.test"
    db.create_user(email, auth.hash_password(PASSWORD), "Agency", None)
    monkeypatch.setenv("SUPER_ADMINS", "someone-else@agency.test")
    r = TestClient(main.app).post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 403 and "SUPER_ADMINS" in r.json()["detail"]



def test_agency_events_stay_out_of_business_audit_logs(monkeypatch):
    """Regression: start-up used to hand every audit row with no business to BrightPath, so the agency's
    own log-ins appeared in BrightPath's audit log."""
    ag = agency_client(monkeypatch)
    db.adopt_orphans(1)  # what start-up runs
    assert db.rows("SELECT 1 AS x FROM audit WHERE business_id IS NULL AND action='Logged in'")


def test_unexpected_errors_are_recorded_for_the_agency(monkeypatch, shop):
    owner, _ = shop
    monkeypatch.setattr(main.db, "all_leads", lambda *a, **k: 1 / 0)
    quiet = TestClient(main.app, raise_server_exceptions=False, cookies=dict(owner.cookies))
    r = quiet.get("/api/leads")
    assert r.status_code == 500 and "LeadBot team" in r.json()["detail"]
    assert any(e["action"] == "Server error" and "ZeroDivisionError" in e["detail"]
               for e in db.rows("SELECT action, detail FROM audit WHERE business_id IS NULL"))
