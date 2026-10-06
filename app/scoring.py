"""Explainable lead scoring (rules). Returns a 0-100 score, a tier, and a human-readable reason."""
import re

INTENT_WORDS = [
    "price", "pricing", "cost", "quote", "quotation", "how much", "installment", "financing",
    "site visit", "book", "buy", "order", "install", "qeemat", "keemat", "kitna", "kitne",
    "rate", "daam", "kist", "qist", "chahiye", "lagwana", "lagwani",
]
URGENT_WORDS = [
    "asap", "urgent", "this week", "this month", "next week", "immediately", "jaldi",
    "is hafte", "is mahine", "abhi", "today", "tomorrow", "kal", "aaj",
]

WEIGHTS = {
    "phone": 25, "email": 15, "name": 5, "need": 15, "budget": 15, "timeline": 10,
}


def score_lead(lead, user_text):
    text = (user_text or "").lower()
    pts, reasons = 0, []

    for field, w in WEIGHTS.items():
        if lead.get(field):
            pts += w
            reasons.append(f"shared {field}")

    if any(re.search(rf"\b{re.escape(w)}\b", text) for w in INTENT_WORDS):
        pts += 10
        reasons.append("asked about pricing/purchase")

    if any(w in text for w in URGENT_WORDS):
        pts += 5
        reasons.append("urgent timeline")

    pts = min(pts, 100)
    return pts, tier_for(pts), ", ".join(reasons) or "no buying signals yet"


def tier_for(pts):
    return "hot" if pts >= 70 else "warm" if pts >= 40 else "cold"
