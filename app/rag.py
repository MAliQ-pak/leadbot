"""Tiny retrieval layer: chunk the knowledge base and rank chunks with TF-IDF.

Character n-grams are used on purpose: they tolerate Roman Urdu spelling variations
(e.g. "qeemat" / "keemat") better than word-level matching, and need no embedding API.
"""
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

KB_DIR = Path(__file__).resolve().parent.parent / "kb"

# Common Roman Urdu / English intent words mapped to KB vocabulary so queries match.
SYNONYMS = {
    "qeemat": "price pricing cost",
    "keemat": "price pricing cost",
    "kitna": "price cost how much",
    "kitne": "price cost how much",
    "rate": "price pricing",
    "daam": "price cost",
    "kist": "installment financing",
    "qist": "installment financing",
    "installments": "installment financing",
    "guarantee": "warranty",
    "waranty": "warranty",
    "time": "installation time duration",
    "kitna time": "installation time duration",
    "kab": "installation time",
    "visit": "site visit",
    "timing": "working hours contact",
    "timings": "working hours contact",
    "hours": "working hours contact",
    "net metering": "services net metering paperwork",
    "cost": "price pricing",
    "how much": "price pricing",
    "expensive": "price pricing",
    "cheap": "price pricing",
    "emi": "installment financing",
    "open": "working hours contact",
    "sunday": "working hours contact",
    "loan": "installment financing",
    "installation": "installation time",
    "how long": "installation time duration",
    "where": "areas karachi lahore islamabad",
    "contact": "working hours contact",
    "call": "working hours contact",
    # words the website uses that the knowledge base doesn't ("Packages", "Starting prices")
    "package": "pricing price",
    "packages": "pricing price",
    "price": "pricing",
    "prices": "pricing price",
    "rates": "pricing price",
    "price list": "pricing price maintenance",
    "plans": "pricing price financing",
    "offer": "services pricing",
    "options": "services pricing",
    "products": "services pricing",
    "which system": "pricing services",
    "on grid": "pricing on-grid",
    "on-grid": "pricing",
    "hybrid": "pricing services battery",
    "battery": "services battery backup pricing",
    "backup": "services battery backup pricing",
    "load shedding": "services battery backup",
    "areas": "about karachi lahore islamabad",
    "cities": "about karachi lahore islamabad",
    "city": "about karachi lahore islamabad",
    "serve": "about karachi lahore islamabad",
    "located": "about karachi lahore islamabad",
    "company": "about",
    "who are you": "about",
    "batao": "price pricing",
    # general shop words (a shoe store, clothing, retail)
    "delivery": "delivery",
    "shipping": "delivery",
    "deliver": "delivery",
    "cod": "delivery payment cash",
    "cash on delivery": "delivery payment",
    "return": "returns exchange",
    "returns": "returns exchange",
    "exchange": "returns exchange",
    "refund": "returns exchange",
    "size": "sizes",
    "sizes": "sizes",
    "joota": "products shoes",
    "joote": "products shoes",
    "shoes": "products",
    "jazzcash": "payment",
    "easypaisa": "payment",
    "card": "payment",
    "pay": "payment",
    "bulk": "bulk orders",
}


STOPWORDS = {
    "a", "an", "and", "are", "can", "do", "does", "for", "how", "i", "in", "is", "it", "me", "my", "of",
    "on", "or", "our", "the", "to", "we", "what", "when", "where", "which", "with", "you", "your",
    "hai", "ka", "ki", "ke", "ko", "se", "mein", "kya",
}
CONFIDENT = 0.3  # below this the bot is guessing; the question is logged as "unanswered" for the owner


def _keywords(text):
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOPWORDS and len(w) > 1}


class KnowledgeBase:
    """One business's knowledge, indexed together: its main text, its Q&A pairs, and its uploaded
    documents / imported web pages (all stored in the database under its business_id)."""

    def __init__(self, business_id):
        self.business_id = business_id
        self.chunks = []
        self._load()
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True)
        self.matrix = self.vec.fit_transform([c["index"] for c in self.chunks]) if self.chunks else None

    def _add(self, section, body, source, index_extra="", keywords_from=None):
        text = f"{section}: {body}"
        self.chunks.append({
            "section": section, "text": text, "source": source,
            "index": text + " " + index_extra,                        # what TF-IDF matches against
            "keywords": _keywords(keywords_from or section),          # for the title boost
        })

    def _load(self):
        from . import db, ingest  # imported here to avoid a circular import at startup
        biz = db.get_business(self.business_id) or {}
        section, body = "", []
        for line in (biz.get("kb_text") or "").splitlines():  # the main text: each "## " heading is one topic
            if line.startswith("# "):
                continue  # document title
            if line.startswith("## "):
                if body:
                    self._add(section, " ".join(body), "text")
                section, body = line[3:].strip(), []
            elif line.strip():
                body.append(line.strip())
        if body:
            self._add(section, " ".join(body), "text")

        for q in db.faqs(self.business_id):
            variants = " ".join(v.strip() for v in (q["variants"] or "").splitlines() if v.strip())
            self._add(q["question"], q["answer"], "qa", index_extra=variants,
                      keywords_from=q["question"] + " " + variants)
        for d in db.docs(self.business_id, with_text=True):
            for section, body in ingest.chunk(d["name"], d["text"]):
                self._add(section, body, d["kind"])

    def _expand(self, query):
        q = query.lower()
        extra = [v for k, v in SYNONYMS.items() if re.search(rf"\b{re.escape(k)}\b", q)]
        return q + " " + " ".join(extra)

    def search_scored(self, query, k=3):
        """Top-k chunks as dicts with a 'score' (TF-IDF cosine similarity + title boost)."""
        if not self.chunks:
            return []
        expanded = self._expand(query)
        sims = cosine_similarity(self.vec.transform([expanded]), self.matrix)[0].copy()
        # Boost chunks whose title (or Q&A question) words appear in the expanded query,
        # e.g. "how much" -> "pricing" boosts the Pricing section. Filler words are ignored.
        words = _keywords(expanded)
        for i, ch in enumerate(self.chunks):
            if ch["keywords"]:
                sims[i] += 0.3 * len(ch["keywords"] & words) / len(ch["keywords"])
        ranked = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:k]
        return [{**self.chunks[i], "score": float(sims[i])} for i in ranked]

    def search(self, query, k=3, min_score=0.12):
        return [c["text"] for c in self.search_scored(query, k) if c["score"] >= min_score]


_kbs = {}  # business_id -> its KnowledgeBase, built on first use


def get_kb(business_id):
    if business_id not in _kbs:
        _kbs[business_id] = KnowledgeBase(business_id)
    return _kbs[business_id]


def reload_kb(business_id):
    """Rebuild one business's index after its knowledge base changes in the admin panel."""
    _kbs[business_id] = KnowledgeBase(business_id)
    return _kbs[business_id]
