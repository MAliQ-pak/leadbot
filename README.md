# LeadBot: AI Lead Qualification Chatbot (FYP)

Website chat widget that answers customer questions from a business knowledge base, collects lead details in conversation, scores each lead (hot / warm / cold, with a reason), and pushes qualified leads to a CRM webhook. Includes an owner dashboard.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env        # add ANTHROPIC_API_KEY (optional, see below)
uvicorn app.main:app --reload
```

- Demo website (BrightPath Solar) with the chatbot: http://localhost:8000
- Admin panel (the hub for all leads): http://localhost:8000/admin
- Bot tester with live lead score (rules vs model): http://localhost:8000/chat

**Choose the AI:** set `LLM_PROVIDER` in `.env` to `claude` (Anthropic, paid: add `ANTHROPIC_API_KEY`) or `gemini` (Google, free tier: add `GEMINI_API_KEY` from aistudio.google.com). With no key, or if the API fails, the offline rule-based bot answers so the demo always works. Note: on Gemini's free tier Google may use the content to improve its products, so use demo data only.

## How it works

1. Visitor message goes to `POST /api/chat`.
2. `rag.py` retrieves the most relevant knowledge-base chunks (TF-IDF over character n-grams, tolerant of Roman Urdu spellings).
3. `llm.py` asks the LLM to answer only from that context and return the reply plus any lead details stated so far (JSON).
4. `scoring.py` computes an explainable 0-100 rule score; `classifier.py` (logistic regression, trained by `train_classifier.py` on `data/labeled_leads.csv`) predicts how likely the lead is qualified. The final score is a blend of both (`ML_WEIGHT`, default 0.5) and sets the hot/warm/cold tier. With no trained model it uses rules only.
5. Every chat becomes a lead in the **admin panel** (`/admin`):
   - **Overview**: totals for hot / warm / cold / won / lost, hot leads to call now, pipeline, latest conversations.
   - **Pipeline**: a deals board with one column per stage (New, Contacted, Site visit booked, Quote sent, Won, Lost). Each card shows the lead's hot / warm / cold tag and score; drag a card to move the deal. Visitors without a phone or email are hidden unless switched on.
   - **Leads**: filter by Hot, Warm, Cold, Won, Lost, or search; open a lead to see contact details, the score breakdown and reason, the full conversation, set its stage, add notes, or delete it.
   - **Audit log**: every owner action (stage changes, notes, deletes, knowledge-base edits, uploads, logins and failed logins) and key events (new lead, lead turned hot, AI failed), filterable by type.
   - **Bot & knowledge**: bot mode, scoring mode, a **Test the knowledge** box (shows which topics a question matches and how confidently), and four ways to train the knowledge base. Every change applies on the next message:
     - **Q&A**: question + other ways to ask it (e.g. Roman Urdu) + answer.
     - **Unanswered**: questions visitors asked that the knowledge base could not answer confidently (best match below 30%). The bot says it is not sure instead of guessing; the owner answers once and the bot knows it from then on.
     - **Documents & websites**: upload PDF, Word (.docx), TXT or Markdown files, or import a web page by URL. Text is split into topics by headings / paragraphs.
     - **Main text**: edit `kb/business.md` directly.
6. Optional: `crm.py` can also push warm/hot leads to a CRM webhook. It is off by default; set `CRM_ENABLED=true` in `.env` to turn it on.

## Project report

`report/report.md` is the report text. Build the styled PDF (Fraunces + Inter, the LeadBot palette, figures drawn from the live code) with:

```bash
pip install markdown
python report/build_report.py
```

Fill in the cover details (roll number, supervisor, department, university) at the top of `report/build_report.py` first. The PDF is written to `report/LeadBot-FYP-Report.pdf`; it is printed by Microsoft Edge or Google Chrome in headless mode.

## Admin login

`/admin`, the bot tester (`/chat`) and all admin APIs need the owner login set by `ADMIN_USER` / `ADMIN_PASSWORD` (the browser shows its own login box). With no password set, the admin panel only opens on the computer running the server, so a deployment can never be left open by accident.

## Put it online (Render, free)

1. Push this folder to a GitHub repository (`.gitignore` keeps `.env` and `leadbot.db` out).
2. On [render.com](https://render.com), sign in with GitHub, choose **New > Blueprint**, and pick the repository. Render reads `render.yaml`.
3. When asked, enter `ADMIN_PASSWORD` and the key for your provider: `GEMINI_API_KEY` (with `LLM_PROVIDER=gemini`) or `ANTHROPIC_API_KEY` (with `LLM_PROVIDER=claude`).
4. Open the `onrender.com` link Render gives you. The admin panel is at `/admin`.

Free-tier notes: the service sleeps after a period of no visits (the first visit then takes about a minute), and its disk is reset on every restart or deploy, so leads, uploads and knowledge-base edits made on the live site are temporary. A paid plan with a persistent disk keeps them.

Spending guards: at most `LLM_HOURLY_LIMIT` Claude replies per hour site-wide, and `MAX_CLAUDE_MESSAGES_PER_CHAT` per conversation. Beyond either, the offline bot answers. Also set a monthly spend limit in the Anthropic Console.

## Use your own business

Replace `kb/business.md` with your own FAQs, pricing, and policies (headings `##` become chunks), and set `BUSINESS_NAME` in `.env`.

## Embed on any site

```html
<script src="https://YOUR-HOST/static/widget.js" defer></script>
```

## Project layout

```
app/main.py      API + routing
app/rag.py       knowledge-base retrieval
app/ingest.py    reads PDF / Word / TXT / MD files and web pages into topics
app/llm.py       LLM call (Claude) + offline mock
app/scoring.py   lead scoring rules
app/classifier.py trained lead classifier (scikit-learn)
train_classifier.py  trains it -> models/lead_classifier.joblib
app/crm.py       CRM webhook sync
app/db.py        SQLite storage
static/          chat widget, demo site, dashboard
kb/              knowledge base (markdown)
```

## Known limits (good for the report's "future work")

- The classifier's starter training set (`data/labeled_leads.csv`, 62 rows) is hand-written and illustrative; replace or extend it with real labeled conversations and re-run `python train_classifier.py`.
- The admin panel has no login yet; add auth before real deployment.
- Retrieval is TF-IDF; swap in embeddings + a vector store for larger knowledge bases.
