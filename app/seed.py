"""Demo data for presentations: fictional BrightPath Solar leads, chats, Q&A pairs, unanswered
questions and audit history, spread over the last ten days.

    python -m app.seed            # replace everything with fresh demo data
    SEED_DEMO=true (in .env)      # the server seeds by itself whenever the database has no leads,
                                  # e.g. after every restart on Render's free tier

Scores are not typed in: every lead is scored by the real rules and classifier (main.score_and_tier).
All names and phone numbers are made up.
"""
import time

from . import db

DAY, HOUR, MIN = 86400, 3600, 60
STAGE_PATH = ["new", "contacted", "site_visit", "quote_sent"]  # the usual road before won or lost

# (session id, name, phone, email, need, budget, timeline, stage, notes, first seen (days ago), chat)
# chat = visitor and bot turns, alternating, starting with the visitor
LEADS = [
    ("demo-hassan", "Hassan Raza", "0345-1234567", None, "10 kW hybrid with battery", "20 lac", "this month", "new", "",
     0.1, ["How much is a 10kw hybrid system?",
           "A 10 kW hybrid system with battery backup starts from about Rs 1,900,000. Final price depends on roof size, panel brand and battery choice. May I know your name?",
           "My name is Hassan Raza, 0345-1234567",
           "Thanks, Hassan! Do you have a rough budget in mind?",
           "budget around 20 lac, need it this month",
           "Thanks, Hassan! I've noted your budget and timeline. Our advisor will call you within one working day."]),
    ("demo-noman", "Noman Javed", "0300-7654321", None, "5 kW on-grid", "7 lac", "next week", "new", "",
     0.4, ["5kw ki qeemat kitni hai?",
           "5 kW on-grid system takreeban Rs 650,000 se shuru hota hai. Kya main aap ka naam jaan sakta hoon?",
           "mera naam Noman hai, 0300-7654321. budget 7 lac hai aur agle hafte chahiye",
           "Shukriya Noman! Hamara advisor ek working day mein aap ko call karega."]),
    ("demo-hira", "Hira Malik", "0312-1234567", None, "yearly maintenance plan", None, None, "new", "",
     1.2, ["What does the yearly maintenance plan include?",
           "Yearly maintenance includes panel cleaning, inverter check, wiring inspection and a performance report. The plan costs Rs 15,000 per year for homes. May I know your name?",
           "I'm Hira Malik, my number is 0312-1234567",
           "Thanks, Hira! When would you like the maintenance visit?"]),
    ("demo-rabia", "Rabia Anwar", "0321-5550199", None, "solar for home", None, None, "new", "",
     2.3, ["just looking for now, what brands of panels do you use?",
           "I'm not sure about that one, but a human advisor can help. May I know your name?",
           "Rabia Anwar, 0321-5550199. maybe later this year",
           "Thanks, Rabia! An advisor can share panel options whenever you're ready."]),
    ("demo-ayesha", "Ayesha Khan", "0321-1234567", "ayesha.khan@example.com", "5 kW on-grid", "7 lac", "next week", "contacted",
     "Called Monday. Wants the site visit on Saturday morning.",
     3.1, ["Hi, I want a 5kw on-grid system for my house. How much?",
           "A 5 kW on-grid system starts from about Rs 650,000. We give a free written quote after a site visit. May I know your name?",
           "Ayesha Khan, 0321-1234567, ayesha.khan@example.com",
           "Thanks, Ayesha! Do you have a rough budget in mind?",
           "around 7 lac, next week if possible",
           "Thanks, Ayesha! Our advisor will call you within one working day."]),
    ("demo-omar", "Omar Farooq", None, "omar.farooq@example.com", "battery backup for load shedding", None, "this month", "contacted",
     "Emailed the hybrid brochure. Prefers WhatsApp.",
     2.8, ["Do you have battery backup? Load shedding is killing us",
           "Yes, we install lithium battery backup and hybrid inverter setups. May I know your name?",
           "Omar Farooq, omar.farooq@example.com. need it this month",
           "Thanks, Omar! Our advisor will contact you about a backup system."]),
    ("demo-bilal", "Bilal Ahmed", "0300-1112223", None, "5 kW with net metering", "8 lac", "next month", "contacted",
     "Asked about net metering timelines; call back Thursday.",
     4.0, ["do you do net metering?",
           "Yes, we handle the net metering paperwork for you. Approval usually takes 4 to 8 weeks. May I know your name?",
           "Bilal Ahmed, 0300-1112223. want 5kw with net metering, budget 8 lac, next month",
           "Thanks, Bilal! Our advisor will call you within one working day."]),
    ("demo-ahmed", "Ahmed Siddiqui", "0333-4445556", None, "5 kW on installments", "6 lac", "this month", "site_visit",
     "Site visit booked for Thursday 11 am. Interested in the 12-month installment plan.",
     5.2, ["kist pe mil sakta hai?",
           "Ji, hum partner banks ke zariye 6, 12 aur 24 mahine ke installment plans dete hain. 20 percent down payment lazmi hai. Aap ka naam?",
           "Ahmed Siddiqui, 0333-4445556. 5kw chahiye, budget 6 lac, is mahine",
           "Shukriya Ahmed! Free site visit book karne ke liye hamara advisor call karega."]),
    ("demo-sana", "Sana Iqbal", "0331-2345678", None, "5 kW solar", "7 lac", "this month", "quote_sent",
     "Site visit done. Written quote sent; follow up on Friday.",
     7.0, ["mera naam Sana Iqbal hai, 0331-2345678. 5kw solar lagwana hai",
           "Shukriya Sana! Kya aap apna andazan budget bata sakti hain?",
           "7 lac tak, is mahine",
           "Shukriya! Free site visit ke baad hum likha hua quote dete hain."]),
    ("demo-usman", "Usman Tariq", "0301-9876543", "usman.tariq@example.com", "commercial system for a factory", "30 lac", "3 months",
     "quote_sent", "Commercial job. Quote sent for a larger system; owner reviewing with partners.",
     8.5, ["We need solar for our factory. Do you do commercial installations?",
           "Yes, we install residential and commercial solar systems in Karachi, Lahore and Islamabad. May I know your name?",
           "Usman Tariq, 0301-9876543, usman.tariq@example.com. budget around 30 lac, within 3 months",
           "Thanks, Usman! An advisor will arrange a free site visit and a written quote."]),
    ("demo-fatima", "Fatima Noor", "0322-6667778", None, "5 kW on-grid", "7 lac", "this week", "won",
     "Signed. Installation scheduled for next week.",
     9.5, ["How long does installation take?",
           "Most home installations take 3 to 5 days after the site visit is approved. May I know your name?",
           "Fatima Noor, 0322-6667778. 5kw, budget 7 lac, this week if possible",
           "Thanks, Fatima! Our advisor will call you within one working day."]),
    ("demo-kamran", "Kamran Ali", "0302-3334445", "kamran.ali@example.com", "10 kW hybrid with battery", "19 lac", "this month", "won",
     "Paid the down payment. Hybrid with battery, installation booked.",
     9.8, ["10kw hybrid with battery, what's the price and warranty?",
           "A 10 kW hybrid system with battery backup starts from about Rs 1,900,000. Panels have a 12 year product and 25 year performance warranty. May I know your name?",
           "Kamran Ali, 0302-3334445, kamran.ali@example.com. budget 19 lac, this month",
           "Thanks, Kamran! Our advisor will call you within one working day."]),
    ("demo-zainab", "Zainab Hussain", "0311-8889990", None, "5 kW on-grid", "5 lac", "next month", "lost",
     "Went with a cheaper competitor.",
     6.2, ["what is the cheapest 5kw option?",
           "A 5 kW on-grid system starts from about Rs 650,000. Final price depends on roof size and panel brand. May I know your name?",
           "Zainab Hussain, 0311-8889990. budget only 5 lac, next month",
           "Thanks, Zainab! An advisor can talk you through the options."]),
    ("demo-imran", "Imran Sheikh", "0300-1231234", None, "5 kW", None, None, "lost",
     "Not buying this year. Follow up in six months.",
     4.6, ["just checking prices for next year, how much is 5kw?",
           "A 5 kW on-grid system starts from about Rs 650,000. May I know your name?",
           "Imran Sheikh, my number 0300-1231234",
           "Thanks, Imran! Whenever you're ready, our advisor can help."]),
]

# visitors who never shared contact details (hidden on the Pipeline board unless switched on)
ANONYMOUS = [
    ("demo-anon-1", 0.2, ["what is the warranty on panels?",
                          "Solar panels come with a 12 year product warranty and a 25 year performance warranty. What are you looking for?"]),
    ("demo-anon-2", 1.5, ["do you sell generators?",
                          "I'm not sure about that one, but a human advisor can help. May I know your name?"]),
    ("demo-anon-3", 3.4, ["is there a discount for students?",
                          "I'm not sure about that one, but a human advisor can help. What are you looking for?"]),
]

# questions waiting under Admin > Bot & knowledge > Unanswered: (question, times asked, first asked days ago)
UNANSWERED = [
    ("is there a discount for students?", 3, 6.0),
    ("do you sell generators?", 2, 1.5),
    ("what brand of inverter do you use?", 1, 2.3),
    ("can I pay with credit card?", 1, 4.4),
]

# Q&A pairs the owner has already added (answers only restate kb/business.md)
FAQS = [
    ("Can I book a site visit on Sunday?", "sunday ko visit ho sakta hai?",
     "Our team works Monday to Saturday, 9 am to 7 pm, so site visits are booked on those days.", "unanswered", 5.0),
    ("Do you install on commercial buildings?", "factory ke liye solar?\nshop ke liye solar lagate ho?",
     "Yes. We install both residential and commercial solar systems in Karachi, Lahore and Islamabad. A free site visit comes first.",
     "manual", 8.0),
]


def _stage_route(stage):
    """The stages a deal passed through to reach `stage` (won and lost come after a quote or a visit)."""
    if stage in STAGE_PATH:
        return STAGE_PATH[1:STAGE_PATH.index(stage) + 1]
    return ["contacted", "site_visit", "quote_sent", stage] if stage == "won" else ["contacted", stage]


def reset():
    for table in ("messages", "leads", "audit", "kb_faq", "unanswered"):
        db.execute(f"DELETE FROM {table}")


def seed():
    from .main import score_and_tier  # imported here: main imports this module at start-up
    from .scoring import tier_for
    now = time.time()
    audit = []  # (time, actor, kind, action, target, detail)

    def add_chat(sid, start, turns):
        t = start
        for i, text in enumerate(turns):
            db.execute("INSERT INTO messages(session_id, role, content, created) VALUES (?,?,?,?)",
                       (sid, "user" if i % 2 == 0 else "assistant", text, t))
            t += 40 if i % 2 == 0 else 2 * MIN
        return t

    for sid, name, phone, email, need, budget, timeline, stage, notes, days, turns in LEADS:
        start = now - days * DAY
        last = add_chat(sid, start, turns)
        lead = {"session_id": sid, "name": name, "phone": phone, "email": email, "need": need,
                "budget": budget, "timeline": timeline}
        score_and_tier(lead, " ".join(turns[0::2]))
        db.execute(
            """INSERT INTO leads(session_id, name, phone, email, need, budget, timeline, score, rule_score, ml_score,
               tier, reason, synced_at, updated, status, notes, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, name, phone, email, need, budget, timeline, lead["score"], lead["rule_score"], lead["ml_score"],
             lead["tier"], lead["reason"], None, last, stage, notes, start))
        audit.append((start, "visitor", "lead", "New lead", sid, f"first message: {turns[0][:80]}"))
        if lead["tier"] == "hot":
            audit.append((start + 3 * MIN, "system", "lead", "Lead turned hot", sid, f"{name} scored {lead['score']}"))
        # the owner moved the deal along over the following days
        prev, t = "new", last + 2 * HOUR
        for nxt in _stage_route(stage):
            t = min(t + 0.9 * DAY * max(days, 1) / 4, now - 10 * MIN)
            names = db.STATUS_NAMES
            audit.append((t, "admin", "lead", "Stage changed", sid, f"{name}: {names[prev]} → {names[nxt]}"))
            prev = nxt
        if notes:
            audit.append((min(t + 20 * MIN, now - 5 * MIN), "admin", "lead", "Notes edited", sid, name))

    for sid, days, turns in ANONYMOUS:
        start = now - days * DAY
        last = add_chat(sid, start, turns)
        lead = {"session_id": sid}
        score_and_tier(lead, turns[0])
        db.execute("""INSERT INTO leads(session_id, score, rule_score, ml_score, tier, reason, updated, status, notes, created)
                      VALUES (?,?,?,?,?,?,?,?,?,?)""",
                   (sid, lead["score"], lead["rule_score"], lead["ml_score"], tier_for(lead["score"]), lead["reason"],
                    last, "new", "", start))
        audit.append((start, "visitor", "lead", "New lead", sid, f"first message: {turns[0][:80]}"))

    for question, times, days in UNANSWERED:
        for n in range(times):
            db.execute("INSERT INTO unanswered(session_id, question, score, created, status) VALUES (?,?,?,?,?)",
                       (f"demo-q-{n}", question, 0.12, now - (days - n * 0.7) * DAY, "open"))

    for question, variants, answer, source, days in FAQS:
        t = now - days * DAY
        db.execute("INSERT INTO kb_faq(question, variants, answer, source, created) VALUES (?,?,?,?,?)",
                   (question, variants, answer, source, t))
        audit.append((t, "admin", "kb", "Answered a visitor question" if source == "unanswered" else "Q&A added", "", question))

    # owner logins, one failed attempt, and one AI outage handled by the offline bot
    for d in (9.6, 7.1, 5.0, 3.0, 1.1, 0.05):
        audit.append((now - d * DAY, "admin", "auth", "Logged in", "", "from 39.57.120.14"))
    audit.append((now - 4.2 * DAY, "unknown", "auth", "Failed login", "", "username 'admin' from 182.180.66.7"))
    audit.append((now - 2.05 * DAY, "system", "system", "AI failed, offline bot answered",
                  "", "Gemini error 503 (gemini-3.8-flash): This model is currently experiencing high demand."))

    for t, actor, kind, action, target, detail in sorted(audit):
        db.execute("INSERT INTO audit(created, actor, kind, action, target, detail) VALUES (?,?,?,?,?,?)",
                   (t, actor, kind, action, target, detail))
    from . import rag
    rag.reload_kb()  # the new Q&A pairs are answerable straight away
    return len(LEADS), len(ANONYMOUS)


def seed_if_empty():
    """Called at server start when SEED_DEMO=true: fill an empty database with demo data."""
    if not db.rows("SELECT 1 FROM leads LIMIT 1"):
        n, a = seed()
        print(f"Demo data: {n} leads and {a} anonymous visitors added (SEED_DEMO=true).")


if __name__ == "__main__":
    from . import main  # noqa: F401  loads .env and creates the tables
    reset()
    n, a = seed()
    print(f"Demo data ready: {n} leads, {a} anonymous visitors, {len(UNANSWERED)} unanswered questions, {len(FAQS)} Q&A pairs.")
