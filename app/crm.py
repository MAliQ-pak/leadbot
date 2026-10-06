"""CRM sync. Posts qualified leads to a webhook (e.g. a GoHighLevel inbound webhook).
With no CRM_WEBHOOK_URL set it falls back to a local mock CRM (crm_mock.jsonl) so demos always work.
"""
import json
import os
import time
from pathlib import Path

import httpx

MOCK_FILE = Path(__file__).resolve().parent.parent / "crm_mock.jsonl"


def should_sync(lead):
    has_contact = bool(lead.get("phone") or lead.get("email"))
    return has_contact and lead.get("tier") in ("warm", "hot")


def sync(lead):
    """Returns True if the lead was delivered."""
    payload = {
        "name": lead.get("name"),
        "phone": lead.get("phone"),
        "email": lead.get("email"),
        "need": lead.get("need"),
        "budget": lead.get("budget"),
        "timeline": lead.get("timeline"),
        "lead_score": lead.get("score"),
        "lead_tier": lead.get("tier"),
        "rule_score": lead.get("rule_score"),
        "ml_score": lead.get("ml_score"),
        "score_reason": lead.get("reason"),
        "source": "leadbot-website-chat",
    }
    url = os.getenv("CRM_WEBHOOK_URL", "").strip()
    if url:
        try:
            r = httpx.post(url, json=payload, timeout=10)
            return r.status_code < 300
        except Exception as e:  # CRM down must never break the chat
            print("CRM sync failed:", e)
            return False
    with MOCK_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**payload, "ts": time.time()}) + "\n")
    return True
