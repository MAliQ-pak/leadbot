"""Businesses: industry templates, per-business bot settings, and creating a new business.

Each business has its own bot (name, greeting, colour, quick replies), its own lead questions and
buying-signal words, and its own knowledge base. A template fills all of these in one click, so a
new company (a shoe shop, say) starts with a working bot and only edits its own details.
"""
import json
import re
from pathlib import Path

from . import db

ROOT = Path(__file__).resolve().parent.parent

# The lead details every bot collects (db.LEAD_FIELDS); a template only changes how it asks for them.
TEMPLATES = {
    "solar": {
        "label": "Solar installer",
        "sample": "BrightPath Solar",
        "bot_name": "BrightPath Assistant",
        "color": "#3E5C3F",
        "greeting": "Assalam o Alaikum! I can help with prices, installation, warranty, installments or booking a free site visit. You can write in English or Roman Urdu.",
        "quick_replies": ["How much is a 5 kW system?", "5kw ki qeemat kitni hai?", "Book a free site visit", "Do you offer installments?"],
        "questions": {
            "need": "What are you looking for (e.g. home system size or backup needs)?",
            "name": "May I know your name?",
            "phone": "What's the best phone number for our advisor to reach you?",
            "budget": "Do you have a rough budget in mind?",
            "timeline": "When are you hoping to get this done?",
        },
        "need_keywords": ["kw", "solar", "inverter", "battery", "net metering", "maintenance", "hybrid", "on-grid"],
        "intent_words": ["install", "lagwana", "lagwani", "site visit"],
        "kb_file": "kb/business.md",
        "stage_names": {"site_visit": "Site visit booked", "quote_sent": "Quote sent"},
    },
    "shoes": {
        "label": "Shoe store",
        "sample": "Stride Shoes",
        "bot_name": "Stride Assistant",
        "color": "#2E3A6E",
        "greeting": "Hi! Looking for shoes? Ask me about sizes, prices, delivery or returns. English or Roman Urdu both work.",
        "quick_replies": ["Do you have size 44?", "Delivery charges?", "Return policy?", "Khussa ki qeemat kya hai?"],
        "questions": {
            "need": "Which shoes are you looking for (style and size)?",
            "name": "May I have your name?",
            "phone": "What's your phone number so we can confirm the order?",
            "budget": "Do you have a budget in mind?",
            "timeline": "When do you need them by?",
        },
        "need_keywords": ["sneakers", "sneaker", "joggers", "formal shoes", "formal", "khussa", "sandals", "heels",
                          "boots", "loafers", "sports shoes", "kids shoes", "school shoes"],
        "intent_words": ["order", "buy", "size", "deliver", "cod", "chahiye"],
        "stage_names": {"site_visit": "Order confirmed", "quote_sent": "Out for delivery"},
        "kb": """# Stride Shoes (sample business for demo)

## About
Stride Shoes sells men's, women's and kids' shoes online across Pakistan and in two stores, in Lahore and Karachi. We have been in business since 2018.

## Products
We sell sneakers, joggers and sports shoes, formal shoes, loafers, sandals, heels, boots, traditional khussa, and kids' school shoes.

## Pricing
Sneakers and joggers start from Rs 4,500. Formal shoes start from Rs 6,000. Khussa start from Rs 2,500. Kids' shoes start from Rs 2,000. Prices are shown on each product page and may change during sales.

## Sizes
Adult sizes run from EU 36 to EU 46. Kids' sizes run from EU 24 to EU 35. Half sizes are not available. If you are between sizes, we suggest the larger size.

## Delivery
We deliver across Pakistan in 3 to 5 working days. Delivery is free on orders above Rs 5,000; otherwise it costs Rs 250. Cash on delivery is available.

## Returns and exchange
Unworn shoes can be returned or exchanged within 7 days of delivery with the receipt. Exchanging for a different size is free.

## Payment
We accept cash on delivery, debit and credit cards, JazzCash and EasyPaisa.

## Store hours and contact
Our stores are open every day, 11 am to 10 pm. Our customer team replies to messages within a few hours.

## Bulk orders
Schools and companies ordering 20 or more pairs can ask for a bulk quote. A team member will call to confirm sizes and prices.
""",
    },
    "blank": {
        "label": "Start from scratch",
        "sample": "My business",
        "bot_name": "Assistant",
        "color": "#3E5C3F",
        "greeting": "Hi! How can I help you today?",
        "quick_replies": ["What do you offer?", "What are your prices?", "How can I contact you?"],
        "questions": {
            "need": "What are you looking for?",
            "name": "May I know your name?",
            "phone": "What's the best phone number to reach you?",
            "budget": "Do you have a budget in mind?",
            "timeline": "When do you need it?",
        },
        "need_keywords": [],
        "intent_words": [],
        "stage_names": {"site_visit": "Meeting booked", "quote_sent": "Proposal sent"},
        "kb": """# My business

## About
Describe your business in two or three sentences: what you sell, where, and since when.

## Services
List what you offer.

## Pricing
Give starting prices for your main products or services.

## Working hours and contact
When you are open and how customers can reach you.
""",
    },
}


def template(key):
    return TEMPLATES.get(key) or TEMPLATES["blank"]


def template_kb(key, name=None):
    """The template's starting text, with the sample business's name swapped for this business's."""
    t = template(key)
    text = (ROOT / t["kb_file"]).read_text(encoding="utf-8") if "kb_file" in t else t["kb"]
    if name and name != t["sample"]:
        text = text.replace(" (sample business for demo)", " (sample text: change it to your own details)")
        text = text.replace(t["sample"], name)
    return text


def template_bot_name(key, name):
    t = template(key)
    return t["bot_name"] if name == t["sample"] else f"{name} Assistant"[:40]


BASE_STAGES = {"new": "New", "contacted": "Contacted", "won": "Won", "lost": "Lost"}


def settings_from_template(key):
    t = template(key)
    out = {k: t[k] for k in ("quick_replies", "questions", "need_keywords", "intent_words")}
    out["stage_names"] = {**BASE_STAGES, **t["stage_names"]}  # the six pipeline stages, named for this industry
    return out


def settings(biz):
    """The business's bot settings, with any missing key filled from its template."""
    try:
        s = json.loads(biz.get("settings") or "{}")
    except json.JSONDecodeError:
        s = {}
    base = settings_from_template(biz.get("industry") or "blank")
    merged = {**base, **{k: v for k, v in s.items() if v not in (None, "")}}
    merged["stage_names"] = {**base["stage_names"], **(s.get("stage_names") or {})}
    return merged


def slugify(name):
    base = re.sub(r"[^a-z0-9]+", "-", (name or "business").lower()).strip("-")[:40] or "business"
    slug, n = base, 2
    while db.business_by_slug(slug):
        slug, n = f"{base}-{n}", n + 1
    return slug


def create_from_template(name, industry, website="", setup_done=0, slug=None):
    t = template(industry)
    return db.create_business(
        slug or slugify(name), name=name, industry=industry if industry in TEMPLATES else "blank", website=website,
        bot_name=template_bot_name(industry, name), greeting=t["greeting"], color=t["color"],
        settings=json.dumps(settings_from_template(industry)), kb_text=template_kb(industry, name), setup_done=setup_done)


def public_config(biz):
    """What the chat window needs to look right: safe to show anyone."""
    s = settings(biz)
    return {"slug": biz["slug"], "name": biz["name"], "bot_name": biz["bot_name"], "greeting": biz["greeting"],
            "color": biz["color"], "quick_replies": s["quick_replies"][:6]}


def bootstrap():
    """At start-up: make sure the original solar demo exists as a business and owns any older data."""
    first = db.business_by_slug("brightpath-solar")
    if not first:
        bid = create_from_template("BrightPath Solar", "solar", "", setup_done=1, slug="brightpath-solar")
        first = db.get_business(bid)
    db.adopt_orphans(first["id"])
    return first
