"""Demo data for presentations: two fictional businesses, BrightPath Solar and Stride Shoes, each with
an owner account, leads at every pipeline stage, chats in English and Roman Urdu, Q&A pairs,
unanswered questions and an audit history spread over the last ten days.

    python -m app.seed            # replace EVERYTHING (all businesses and accounts) with fresh demo data
    SEED_DEMO=true (in .env)      # the server seeds by itself whenever the database has no accounts,
                                  # e.g. after every restart on Render's free tier

Demo logins: owner@brightpath.demo and owner@stride.demo. The password is DEMO_PASSWORD; on a laptop
with no DEMO_PASSWORD set it is "leadbot-demo". Scores are not typed in: every lead is scored by the
real rules and classifier (main.score_and_tier). All names and phone numbers are made up.
"""
import os
import secrets
import time

from . import auth, business, db

DAY, HOUR, MIN = 86400, 3600, 60
STAGE_PATH = ["new", "contacted", "site_visit", "quote_sent"]  # the usual road before won or lost

# (session id, name, phone, email, need, budget, timeline, stage, notes, first seen (days ago), chat)
# chat = visitor and bot turns, alternating, starting with the visitor
SOLAR_LEADS = [
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
SOLAR_ANONYMOUS = [
    ("demo-anon-1", 0.2, ["what is the warranty on panels?",
                          "Solar panels come with a 12 year product warranty and a 25 year performance warranty. What are you looking for?"]),
    ("demo-anon-2", 1.5, ["do you sell generators?",
                          "I'm not sure about that one, but a human advisor can help. May I know your name?"]),
    ("demo-anon-3", 3.4, ["is there a discount for students?",
                          "I'm not sure about that one, but a human advisor can help. What are you looking for?"]),
]

# questions waiting under Admin > Bot & knowledge > Unanswered: (question, times asked, first asked days ago)
SOLAR_UNANSWERED = [
    ("is there a discount for students?", 3, 6.0),
    ("do you sell generators?", 2, 1.5),
    ("what brand of inverter do you use?", 1, 2.3),
    ("can I pay with credit card?", 1, 4.4),
]

# Q&A pairs the owner has already added (answers only restate kb/business.md)
SOLAR_FAQS = [
    ("Can I book a site visit on Sunday?", "sunday ko visit ho sakta hai?",
     "Our team works Monday to Saturday, 9 am to 7 pm, so site visits are booked on those days.", "unanswered", 5.0),
    ("Do you install on commercial buildings?", "factory ke liye solar?\nshop ke liye solar lagate ho?",
     "Yes. We install both residential and commercial solar systems in Karachi, Lahore and Islamabad. A free site visit comes first.",
     "manual", 8.0),
]


# ---------- Stride Shoes ----------
SHOE_LEADS = [
    ("demo-saad", "Saad Ahmed", "0300-4561237", None, "sneakers", "6000", "by Friday", "new", "",
     0.2, ["do you have sneakers in size 43?",
           "Adult sizes run from EU 36 to EU 46, and sneakers start from Rs 4,500. May I have your name?",
           "Saad Ahmed, 0300-4561237. budget 6000, need them by Friday",
           "Thanks, Saad! Delivery takes 3 to 5 working days. Our team will confirm stock and get back to you shortly."]),
    ("demo-mahnoor", "Mahnoor Tariq", "0321-7894561", None, "khussa", "5000", "next month", "new", "",
     0.9, ["khussa ki qeemat kya hai? shaadi ke liye chahiye",
           "Khussa Rs 2,500 se shuru hote hain. Kya main aap ka naam jaan sakti hoon?",
           "Mahnoor Tariq, 0321-7894561. budget 5000, agle mahine shaadi hai",
           "Shukriya Mahnoor! Hamari team aap se jald rabta karegi."]),
    ("demo-danish", "Danish Iqbal", "0333-1478523", "danish.iqbal@example.com", "formal shoes size 42", "8000", "this week",
     "contacted", "Sent photos of two black formal pairs on WhatsApp.",
     2.1, ["I need formal shoes in size 42 for an interview this week",
           "Formal shoes start from Rs 6,000, and we deliver in 3 to 5 working days. May I have your name?",
           "Danish Iqbal, 0333-1478523, danish.iqbal@example.com. budget around 8000",
           "Thanks, Danish! Our team will get back to you shortly."]),
    ("demo-waqar", "Coach Waqar", "0301-2583691", "waqar.sports@example.com", "school shoes, 25 pairs", "60000", "2 weeks",
     "site_visit", "Bulk order for a football academy. Sizes list received; order confirmed.",
     4.0, ["we need 25 pairs of sports shoes for our football academy, do you do bulk orders?",
           "Yes. Schools and companies ordering 20 or more pairs can ask for a bulk quote. May I have your name?",
           "Coach Waqar, 0301-2583691, waqar.sports@example.com. budget 60000, within 2 weeks",
           "Thanks, Coach Waqar! A team member will call to confirm sizes and prices."]),
    ("demo-areeba", "Areeba Shah", "0312-9637412", None, "kids shoes size 30 and 32", "4500", "this week", "site_visit",
     "Two pairs of kids' school shoes, cash on delivery.",
     3.2, ["kids school shoes size 30 aur 32 chahiye, COD hai?",
           "Ji, cash on delivery available hai. Kids' shoes Rs 2,000 se shuru hote hain. Aap ka naam?",
           "Areeba Shah, 0312-9637412. budget 4500, is hafte",
           "Shukriya Areeba! Hamari team order confirm karegi."]),
    ("demo-faisal", "Faisal Mehmood", "0345-3216549", None, "joggers size 44", "7000", "this week", "quote_sent",
     "Shipped with courier, tracking sent by SMS.",
     5.0, ["joggers in size 44? how much is delivery to Multan?",
           "Joggers start from Rs 4,500. Delivery is free on orders above Rs 5,000, otherwise Rs 250. May I have your name?",
           "Faisal Mehmood, 0345-3216549. budget 7000, this week",
           "Thanks, Faisal! Our team will get back to you shortly."]),
    ("demo-nida", "Nida Hassan", "0322-7418529", "nida.hassan@example.com", "heels size 38", "6500", "this week", "won",
     "Delivered and paid. Asked about the return policy for a second pair.",
     7.5, ["do you have heels in size 38? what's the return policy?",
           "Unworn shoes can be returned or exchanged within 7 days of delivery with the receipt. May I have your name?",
           "Nida Hassan, 0322-7418529, nida.hassan@example.com. budget 6500, this week",
           "Thanks, Nida! Our team will get back to you shortly."]),
    ("demo-hamid", "Hamid Raza", "0311-9517534", None, "sneakers", "3000", None, "lost",
     "Wanted sneakers under Rs 3,000; our range starts higher.",
     6.0, ["cheapest sneakers you have?",
           "Sneakers and joggers start from Rs 4,500. May I have your name?",
           "Hamid Raza, 0311-9517534. my budget is only 3000",
           "Thanks, Hamid! Our team will let you know about any sales."]),
]

SHOE_ANONYMOUS = [
    ("demo-shoe-anon-1", 0.5, ["what is your return policy?",
                               "Unworn shoes can be returned or exchanged within 7 days of delivery with the receipt."]),
    ("demo-shoe-anon-2", 1.8, ["do you have size 47?",
                               "I'm not sure about that one, but our team can help. Which shoes are you looking for?"]),
]

SHOE_UNANSWERED = [
    ("do you have size 47?", 2, 1.8),
    ("can I pick up my order from the store?", 1, 3.0),
    ("do you sell socks?", 1, 2.2),
]

SHOE_FAQS = [
    ("Do you deliver to Gilgit and Skardu?", "gilgit delivery?\nskardu mein delivery hoti hai?",
     "Yes, we deliver across Pakistan, including Gilgit-Baltistan. Remote areas can take a few extra days.", "unanswered", 4.0),
]

DEMO = [  # (slug, business name, template, owner email, owner name, data)
    ("brightpath-solar", "BrightPath Solar", "solar", "owner@brightpath.demo", "BrightPath Owner",
     (SOLAR_LEADS, SOLAR_ANONYMOUS, SOLAR_UNANSWERED, SOLAR_FAQS)),
    ("stride-shoes", "Stride Shoes", "shoes", "owner@stride.demo", "Stride Owner",
     (SHOE_LEADS, SHOE_ANONYMOUS, SHOE_UNANSWERED, SHOE_FAQS)),
]


def demo_password():
    """DEMO_PASSWORD if set; on a laptop "leadbot-demo"; on a server with none set, a random one (printed)."""
    if os.getenv("DEMO_PASSWORD"):
        return os.getenv("DEMO_PASSWORD")
    if os.getenv("RENDER"):  # Render sets this: never leave a guessable password on the internet
        pw = secrets.token_urlsafe(9)
        print(f"Demo accounts: DEMO_PASSWORD is not set, using a random password for this start-up: {pw}")
        return pw
    return "leadbot-demo"


def _stage_route(stage):
    """The stages a deal passed through to reach `stage` (won and lost come after the third and fourth)."""
    if stage in STAGE_PATH:
        return STAGE_PATH[1:STAGE_PATH.index(stage) + 1]
    return ["contacted", "site_visit", "quote_sent", stage] if stage == "won" else ["contacted", stage]


def reset():
    for table in ("messages", "leads", "audit", "kb_faq", "kb_docs", "unanswered", "users", "businesses"):
        db.execute(f"DELETE FROM {table}")


def _seed_business(bid, owner_email, data):
    from .main import score_and_tier  # imported here: main imports this module at start-up
    from .scoring import tier_for
    leads, anonymous, unanswered, faqs = data
    settings = business.settings(db.get_business(bid))
    names = settings["stage_names"]
    now = time.time()
    audit = []  # (time, actor, kind, action, target, detail)

    def add_chat(sid, start, turns):
        t = start
        for i, text in enumerate(turns):
            db.add_message(bid, sid, "user" if i % 2 == 0 else "assistant", text, created=t)
            t += 40 if i % 2 == 0 else 2 * MIN
        return t

    for sid, name, phone, email, need, budget, timeline, stage, notes, days, turns in leads:
        start = now - days * DAY
        last = add_chat(sid, start, turns)
        lead = {"session_id": sid, "business_id": bid, "name": name, "phone": phone, "email": email, "need": need,
                "budget": budget, "timeline": timeline, "status": stage, "notes": notes, "created": start,
                "updated_override": last}
        score_and_tier(lead, " ".join(turns[0::2]), settings)
        db.save_lead(lead)
        audit.append((start, "visitor", "lead", "New lead", sid, f"first message: {turns[0][:80]}"))
        if lead["tier"] == "hot":
            audit.append((start + 3 * MIN, "system", "lead", "Lead turned hot", sid, f"{name} scored {lead['score']}"))
        # the owner moved the deal along over the following days
        prev, t = "new", last + 2 * HOUR
        for nxt in _stage_route(stage):
            t = min(t + 0.9 * DAY * max(days, 1) / 4, now - 10 * MIN)
            audit.append((t, owner_email, "lead", "Stage changed", sid, f"{name}: {names[prev]} → {names[nxt]}"))
            prev = nxt
        if notes:
            audit.append((min(t + 20 * MIN, now - 5 * MIN), owner_email, "lead", "Notes edited", sid, name))

    for sid, days, turns in anonymous:
        start = now - days * DAY
        last = add_chat(sid, start, turns)
        lead = {"session_id": sid, "business_id": bid, "created": start, "updated_override": last}
        score_and_tier(lead, turns[0], settings)
        lead["tier"] = tier_for(lead["score"])
        db.save_lead(lead)
        audit.append((start, "visitor", "lead", "New lead", sid, f"first message: {turns[0][:80]}"))

    for question, times, days in unanswered:
        for n in range(times):
            db.add_unanswered(bid, f"demo-q-{bid}-{n}", question, 0.12, created=now - (days - n * 0.7) * DAY)

    for question, variants, answer, source, days in faqs:
        t = now - days * DAY
        db.execute("INSERT INTO kb_faq(business_id, question, variants, answer, source, created) VALUES (?,?,?,?,?,?)",
                   (bid, question, variants, answer, source, t))
        audit.append((t, owner_email, "kb", "Answered a visitor question" if source == "unanswered" else "Q&A added", "", question))

    # owner logins, one failed attempt, and one AI outage handled by the offline bot
    audit.append((now - 10 * DAY, owner_email, "auth", "Account created", "", "demo account"))
    for d in (9.6, 7.1, 5.0, 3.0, 1.1, 0.05):
        audit.append((now - d * DAY, owner_email, "auth", "Logged in", "", "from 39.57.120.14"))
    audit.append((now - 4.2 * DAY, "unknown", "auth", "Failed login", "", "from 182.180.66.7"))
    audit.append((now - 2.05 * DAY, "system", "system", "AI failed, offline bot answered",
                  "", "Gemini error 503 (gemini-3.8-flash): This model is currently experiencing high demand."))

    for t, actor, kind, action, target, detail in sorted(audit):
        db.execute("INSERT INTO audit(business_id, created, actor, kind, action, target, detail) VALUES (?,?,?,?,?,?,?)",
                   (bid, t, actor, kind, action, target, detail))
    return len(leads) + len(anonymous)


def seed():
    from . import rag
    password = demo_password()
    total = 0
    for slug, name, industry, email, owner, data in DEMO:
        biz = db.business_by_slug(slug)
        bid = biz["id"] if biz else business.create_from_template(name, industry, "", setup_done=1, slug=slug)
        db.update_business(bid, setup_done=1)
        if not db.user_by_email(email):
            db.create_user(email, auth.hash_password(password), owner, bid)
        total += _seed_business(bid, email, data)
        rag.reload_kb(bid)  # the new Q&A pairs are answerable straight away
    return total


def seed_if_empty():
    """Called at server start when SEED_DEMO=true: fill a database that has no accounts with demo data."""
    if not db.rows("SELECT 1 AS x FROM users LIMIT 1"):
        n = seed()
        print(f"Demo data: 2 businesses with {n} leads added (SEED_DEMO=true).")


if __name__ == "__main__":
    from . import main  # noqa: F401  loads .env and creates the tables
    reset()
    business.bootstrap()
    n = seed()
    print(f"Demo data ready: 2 businesses, {n} leads. Log in as owner@brightpath.demo or owner@stride.demo "
          f"(password: {demo_password() if os.getenv('DEMO_PASSWORD') or not os.getenv('RENDER') else 'see DEMO_PASSWORD'}).")
