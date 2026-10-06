# LeadBot (university FYP)

AI lead-qualification chatbot for small businesses. A website chat widget answers from a knowledge base, collects lead details, scores the lead (hot/warm/cold with a reason), and syncs warm/hot leads to a CRM webhook. Owner dashboard at /admin.

## Run
    pip install -r requirements.txt
    cp .env.example .env     # add ANTHROPIC_API_KEY (empty = offline mock mode)
    uvicorn app.main:app --reload
Demo website: http://localhost:8000  |  Admin panel: http://localhost:8000/admin  |  Bot tester: http://localhost:8000/chat

## Layout
- app/main.py     FastAPI routes (/api/chat, /api/leads [GET/PATCH/DELETE], /api/conversations/{id}, /api/kb/* for KB training)
- app/rag.py      TF-IDF (char n-grams) retrieval over kb/*.md + Q&A + uploaded docs/web pages (SQLite), with Roman Urdu synonyms.
                  Best score below rag.CONFIDENT (0.3) on a question = bot says not sure + logs it to 'unanswered'
- app/ingest.py   file (pdf via pypdf, docx via zipfile, txt, md) and URL text extraction + chunking
- app/llm.py      Claude call (JSON reply + lead fields) and offline rule-based mock
- app/scoring.py  explainable rule-based score 0-100
- app/classifier.py  logistic-regression lead classifier; main.py blends it with the rules (ML_WEIGHT)
- train_classifier.py  trains from data/labeled_leads.csv -> models/lead_classifier.joblib (re-run after editing data)
- app/crm.py      optional webhook sync, OFF unless CRM_ENABLED=true; falls back to crm_mock.jsonl
- app/auth.py     owner login (HTTP Basic) for /admin, /chat and admin APIs; ADMIN_PASSWORD unset = localhost only
- app/db.py       SQLite (leadbot.db); leads have status new/contacted/won/lost + notes
- static/         demo website (index.html, site.css), chat widget (widget.js), bot tester (chat.*), admin panel (admin.html/.css/.js, admin-kb.js = KB training)
- kb/business.md  sample business (BrightPath Solar); replace with your own

## Rules for changes
- Keep it simple: this is a student project that must be demoable and explainable in a viva.
- Mock mode (no API key) must keep working so the demo never depends on internet.
- The LLM must answer only from retrieved context and never invent prices or policies.
- Website prices/policies must match kb/business.md.
- Test after changes: start the server, chat on /, check /admin.

## Known gaps / next steps
1. Classifier done (rules plus classifier). Its 62-row training set is hand-written/illustrative; replace with real labeled conversations.
2. Admin login done (single owner, app/auth.py). Claude spend guards: LLM_HOURLY_LIMIT, MAX_CLAUDE_MESSAGES_PER_CHAT.
3. Test with a real ANTHROPIC_API_KEY and fix odd replies.
4. Deploy: render.yaml (Render free tier) is ready; secrets go in Render env vars, never in git. Free tier disk is wiped on restart.
5. Write the final report and viva Q&A.
