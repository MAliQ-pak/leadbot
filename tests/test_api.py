"""The API end to end with the offline bot: chats become leads, preview chats do not, and no business
can ever see or change another business's data."""
from app import db, llm
from conftest import signup

OWNER_ROUTES = ["/api/me", "/api/leads", "/api/kb", "/api/audit"]


def chat(client, slug, sid, text, preview=False):
    r = client.post("/api/chat", json={"bot": slug, "session_id": sid, "message": text, "preview": preview})
    assert r.status_code == 200, r.text
    return r.json()["reply"]


def test_public_pages_and_owner_pages_are_locked(visitor):
    for path in ["/", "/signup", "/login", "/demo/brightpath-solar", "/demo/stride-shoes", "/static/widget.js",
                 "/api/bot/brightpath-solar", "/api/templates", "/api/health"]:
        assert visitor.get(path).status_code == 200, path
    for path in OWNER_ROUTES:
        assert visitor.get(path).status_code == 401, path
    assert visitor.get("/app", follow_redirects=False).headers["location"].endswith("/login")


def test_eight_templates_offered(visitor):
    keys = [t["key"] for t in visitor.get("/api/templates").json()]
    assert len(keys) == 8 and keys[-1] == "blank" and {"shoes", "clinic", "salon"} <= set(keys)


def test_signup_gives_a_working_bot(shop, visitor):
    client, biz = shop
    assert biz["setup_done"] == 0 and biz["settings"]["stage_names"]["site_visit"] == "Order confirmed"
    cfg = visitor.get(f"/api/bot/{biz['slug']}").json()
    assert cfg["bot_name"] == "Test Shoes Assistant" and cfg["quick_replies"]


def test_a_visitor_chat_becomes_a_scored_lead(shop, visitor):
    client, biz = shop
    chat(visitor, biz["slug"], "sess-lead-1", "My name is Sara, 03211234567, I need sneakers this week")
    lead = next(l for l in client.get("/api/leads").json() if l["session_id"] == "sess-lead-1")
    assert lead["phone"] == "03211234567" and lead["tier"] in ("hot", "warm") and lead["reason"]


def test_preview_chats_are_not_leads(shop):
    client, biz = shop
    chat(client, biz["slug"], "sess-preview-1", "My number is 03001112223", preview=True)
    assert all(l["session_id"] != "sess-preview-1" for l in client.get("/api/leads").json())


def test_a_visitor_cannot_fake_a_preview(shop, visitor):
    """Only the logged-in owner of this business can mark a chat as a test."""
    client, biz = shop
    chat(visitor, biz["slug"], "sess-fake-preview", "My number is 03004445556", preview=True)
    assert any(l["session_id"] == "sess-fake-preview" for l in client.get("/api/leads").json())


def test_businesses_never_see_each_other(visitor):
    a, biz_a = signup("Alpha Shoes")
    b, biz_b = signup("Beta Clinic", "clinic")
    chat(visitor, biz_a["slug"], "sess-alpha", "I am Ali 03001234567, need sneakers")
    assert any(l["session_id"] == "sess-alpha" for l in a.get("/api/leads").json())
    assert all(l["session_id"] != "sess-alpha" for l in b.get("/api/leads").json())
    # B cannot read, change or delete A's lead even with its session id
    assert b.get("/api/admin/conversations/sess-alpha").json() == []
    assert b.patch("/api/leads/sess-alpha", json={"status": "lost"}).status_code == 404
    assert b.delete("/api/leads/sess-alpha").status_code == 404
    lead = next(l for l in a.get("/api/leads").json() if l["session_id"] == "sess-alpha")
    assert lead["status"] == "new"
    assert not any(e["target"] == "sess-alpha" for e in b.get("/api/audit").json())
    # each knowledge base is its own
    assert "Beta Clinic" not in a.get("/api/kb").json()["text"]


def test_a_chat_id_cannot_move_between_businesses(visitor):
    _, biz_a = signup("Gamma Shoes")
    _, biz_b = signup("Delta Salon", "salon")
    chat(visitor, biz_a["slug"], "sess-shared", "hello, 03007778889")
    r = visitor.post("/api/chat", json={"bot": biz_b["slug"], "session_id": "sess-shared", "message": "hi"})
    assert r.status_code == 409


def test_owner_settings_and_stage_names(shop):
    client, biz = shop
    r = client.put("/api/business", json={"bot_name": "Kicks Helper", "stage_names": {"site_visit": "Packed"}})
    assert r.status_code == 200
    me = client.get("/api/me").json()["business"]
    assert me["bot_name"] == "Kicks Helper" and me["settings"]["stage_names"]["site_visit"] == "Packed"
    assert any(e["action"] == "Bot settings updated" for e in client.get("/api/audit").json())


def test_unanswered_question_is_logged_for_the_owner(shop, visitor):
    client, biz = shop
    chat(visitor, biz["slug"], "sess-unknown", "do you sell socks?")
    rows = db.unanswered_open(biz["id"])
    assert any("socks" in r["question"] for r in rows)


def test_new_visitor_has_empty_history(visitor):
    assert visitor.get("/api/conversations/brand-new-id?bot=brightpath-solar").json() == []


def test_unusable_ai_answer_falls_back_to_the_offline_bot(monkeypatch):
    """If the AI returns something that is not the JSON we asked for, the visitor never sees it."""
    monkeypatch.setattr(llm, "provider", lambda: "gemini")
    monkeypatch.setattr(llm, "_respond_gemini", lambda *a: (_ for _ in ()).throw(llm.BadOutput("my notes...")))
    biz = {"name": "Shop", "bot_name": "Shop Assistant",
           "settings": {"questions": {"need": "Which shoes?", "name": "Name?", "phone": "Phone?", "budget": "Budget?",
                                      "timeline": "When?"}, "need_keywords": ["sneakers"]}}
    reply, lead = llm.respond([{"role": "user", "content": "I am Sana 03124445566, want sneakers next week"}],
                              ["Sneakers: Rs 3,999"], {}, biz)
    assert "notes" not in reply and lead["phone"] == "03124445566"
    assert llm._cooldown_until == 0  # one bad answer does not switch the AI off for everyone


def test_whatsapp_click_is_logged_and_scoped(visitor):
    a, biz_a = signup("Wa Shoes")
    b, _ = signup("Other Shop")
    chat(visitor, biz_a["slug"], "sess-wa", "I am Sara, 03211234567, need sneakers")
    assert a.post("/api/leads/sess-wa/whatsapp").status_code == 200
    assert any(e["action"] == "WhatsApp opened" and e["target"] == "sess-wa" for e in a.get("/api/audit").json())
    assert b.post("/api/leads/sess-wa/whatsapp").status_code == 404  # not B's lead
    assert visitor.post("/api/leads/sess-wa/whatsapp").status_code == 401


def test_csv_export(visitor):
    import csv, io
    a, biz_a = signup("Csv Shoes")
    b, _ = signup("Csv Other")
    chat(visitor, biz_a["slug"], "sess-csv-1", "My name is Sara, 03211234567, I need sneakers this week")
    chat(visitor, biz_a["slug"], "sess-csv-2", "=HYPERLINK(\"http://evil.example\") my number is 03001112223")
    r = a.get("/api/leads.csv?tz=-300")  # Pakistan, UTC+5
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="leads-csv-shoes' in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")  # tells Excel it is UTF-8
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert len(rows) == 2 and rows[0].keys() >= {"Name", "Phone", "Tier", "Stage", "First seen", "Last message"}
    sara = next(x for x in rows if x["Phone"] == "03211234567")
    assert sara["Stage"] == "New" and sara["Tier"] in ("hot", "warm") and len(sara["First seen"]) == 16
    evil = next(x for x in rows if x["Phone"] == "03001112223")
    assert evil["Last message"].startswith("'=")  # a typed formula stays text in Excel
    assert len(list(csv.DictReader(io.StringIO(b.get("/api/leads.csv").content.decode("utf-8-sig"))))) == 0
    assert any(e["action"] == "Leads exported" for e in a.get("/api/audit").json())
    assert visitor.get("/api/leads.csv").status_code == 401


def test_csv_cells_guard_against_formulas():
    from app import main
    assert main._csv_cell("-5 discount") == "'-5 discount" and main._csv_cell("+92300") == "'+92300"
    assert main._csv_cell("Sara") == "Sara" and main._csv_cell(None) == "" and main._csv_cell(92) == "92"


def test_csv_times_follow_the_owners_timezone(visitor):
    import csv, io
    from datetime import datetime
    a, biz = signup("Tz Shoes")
    chat(visitor, biz["slug"], "sess-tz", "I am Ali 03001234567")
    seen = lambda tz: next(csv.DictReader(io.StringIO(a.get(f"/api/leads.csv?tz={tz}").content.decode("utf-8-sig"))))["First seen"]
    utc, pkt = (datetime.strptime(seen(tz), "%Y-%m-%d %H:%M") for tz in (0, -300))
    assert (pkt - utc).total_seconds() == 5 * 3600  # Pakistan is UTC+5


def test_pages_and_code_are_always_rechecked(shop, visitor):
    """After an update, a browser must never mix an old page with a new script."""
    client, _ = shop
    for c, path in [(visitor, "/"), (visitor, "/signup"), (visitor, "/bot/brightpath-solar"), (client, "/app"),
                    (visitor, "/static/admin.js"), (visitor, "/static/widget.js"), (visitor, "/static/admin.css")]:
        assert c.get(path).headers.get("cache-control") == "no-cache", path
