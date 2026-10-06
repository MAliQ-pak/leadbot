"""Trained lead classifier (logistic regression) that works alongside the rules in scoring.py.

The same features() function is used for training (train_classifier.py) and live scoring, so
they can never drift apart. Logistic regression is used on purpose: every feature gets one
learned weight that can be printed and explained, unlike a black-box model.
If no trained model file exists, predict() returns None and the app uses rules only.
"""
import re
from pathlib import Path

from .scoring import INTENT_WORDS, URGENT_WORDS

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "lead_classifier.joblib"
DATA_PATH = ROOT / "data" / "labeled_leads.csv"

FIELDS = ["name", "phone", "email", "need", "budget", "timeline"]
# "Not now" signals the hand-written rules ignore; the model learns how much they matter.
NOT_NOW_WORDS = [
    "just checking", "just looking", "just curious", "just comparing", "maybe next year",
    "next year", "not now", "later", "for now", "research", "baad mein", "sirf maloomat",
    "sirf rate", "pooch rahe",
]

FEATURE_NAMES = [f"has_{f}" for f in FIELDS] + [
    "asked_price_or_purchase", "urgent", "not_now", "questions", "message_length",
]


def features(lead, user_text):
    """Turn a lead + everything the visitor typed into a list of numbers (all between 0 and 1)."""
    text = (user_text or "").lower()
    return [1.0 if lead.get(f) else 0.0 for f in FIELDS] + [
        1.0 if any(re.search(rf"\b{re.escape(w)}\b", text) for w in INTENT_WORDS) else 0.0,
        1.0 if any(w in text for w in URGENT_WORDS) else 0.0,
        1.0 if any(w in text for w in NOT_NOW_WORDS) else 0.0,
        min(text.count("?"), 5) / 5,
        min(len(text.split()), 50) / 50,
    ]


_model = None
_loaded = False


def _load():
    global _model, _loaded
    if not _loaded:
        _loaded = True
        if MODEL_PATH.exists():
            import joblib
            try:
                _model = joblib.load(MODEL_PATH)
            except Exception as e:  # a bad model file must never break the chat
                print("Could not load lead classifier, using rules only:", e)
    return _model


def predict(lead, user_text):
    """Probability (0-1) that this lead is qualified, or None if no model is trained."""
    model = _load()
    if model is None:
        return None
    return float(model.predict_proba([features(lead, user_text)])[0][1])
