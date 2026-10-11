# LeadBot: AI Lead Qualification Chatbot (FYP)

A chatbot product for small businesses. A business signs up, picks an industry template (solar installer, shoe store, clinic, restaurant or caterer, real estate agency, school or tuition academy, salon, or start from scratch), teaches the bot its own prices and policies, tests it in a live preview, and pastes one line of code on its website. The bot answers customers only from that business's knowledge, collects their details, scores each lead (hot / warm / cold, with a reason) and puts it on the business's own pipeline.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env        # set LLM_PROVIDER and its key (optional, see below)
python -m app.seed          # optional: two demo businesses with leads
uvicorn app.main:app --reload
```

| Page | Address |
|---|---|
| Product home page | http://localhost:8000 |
| Sign up / log in | http://localhost:8000/signup, http://localhost:8000/login |
| Owner dashboard | http://localhost:8000/app |
| Setup wizard with live preview | http://localhost:8000/app/setup |
| Demo websites with the bot embedded | http://localhost:8000/demo/brightpath-solar, http://localhost:8000/demo/stride-shoes |
| One business's chat window | http://localhost:8000/bot/stride-shoes |

Demo logins (after `python -m app.seed`): `owner@brightpath.demo` and `owner@stride.demo`, password `leadbot-demo` on a laptop (or `DEMO_PASSWORD` if set).

**Choose the AI:** set `LLM_PROVIDER` in `.env` to `gemini` (Google, free tier: add `GEMINI_API_KEY` from aistudio.google.com) or `claude` (Anthropic, paid: add `ANTHROPIC_API_KEY`). With no key, or if the API fails, the offline rule-based bot answers so the demo always works. On Gemini's free tier Google may use the content to improve its products, so use demo data only.

## Setting up a bot for a new business (e.g. a shoe shop)

1. **Sign up** at `/signup` with the business name and the closest template. The template gives a working bot straight away: a starting knowledge base (with the business's own name), quick-reply buttons, the questions it asks customers, buying-signal words, its own synonyms (Roman Urdu and everyday words), and pipeline stage names for that industry (a shoe shop gets *Order confirmed* and *Out for delivery* instead of *Site visit booked* and *Quote sent*).
2. **Setup wizard** (`/app/setup`), with the bot running live beside it:
   1. Business name, website and template.
   2. Teach the bot: edit the main text (each `##` heading is one topic), import the business's website (only one page, all pages under an address, or the whole site, up to 30 pages, following links and the sitemap and obeying robots.txt), or upload a PDF, Word, TXT or Markdown file.
   3. Bot name, greeting, brand colour and quick replies.
   4. Lead questions, product words, buying signals and pipeline stage names.
   5. Install: copy the embed code.
3. **Test in the live preview.** Preview chats are marked as tests and never appear as leads; *Clear test chats* deletes them.
4. **Paste the code** on the website, just before `</body>`:

```html
<script src="https://YOUR-HOST/static/widget.js" data-bot="your-business" data-color="#2E3A6E" defer></script>
```

The loader draws a chat bubble and opens `/bot/your-business` in an iframe. The iframe is served by LeadBot itself, so it works on any website without CORS set-up and the site's own styles cannot break it. An iframe-only snippet and a direct link (for WhatsApp or social media) are given too. Buttons on the site can open the bot with a question: `LeadBot.open("Do you have size 44?")`.

## How it works

1. A visitor's message goes to `POST /api/chat` with the business's slug.
2. `rag.py` retrieves the most relevant chunks from **that business's** knowledge base (TF-IDF over character n-grams, tolerant of Roman Urdu spellings). Each business has its own cached index.
3. `llm.py` asks the LLM to answer only from that context, as that business's assistant, and to return the reply plus any lead details stated so far (JSON). The offline bot uses the business's own questions and product words.
4. `scoring.py` computes an explainable 0-100 rule score (with the business's buying-signal words); `classifier.py` (logistic regression, trained by `train_classifier.py` on `data/labeled_leads.csv`) predicts how likely the lead is qualified. The final score blends both (`ML_WEIGHT`, default 0.5).
5. The lead appears in that owner's **dashboard** (`/app`):
   - **Overview**: hot / warm / cold / won / lost totals, hot leads to call now, latest conversations.
   - **Pipeline**: a deals board with one column per stage; drag a card to move the deal.
   - **Leads**: filter or search; open a lead for contact details, score breakdown, the full chat, stage and notes.
   - **Audit log**: every owner action and key event (new lead, lead turned hot, AI failed, logins).
   - **Bot & knowledge**: Q&A pairs, unanswered questions (best match below 30%, so the bot said it was not sure), documents and web pages, the main text, and a knowledge test box.
6. Optional: `crm.py` pushes warm/hot leads to a CRM webhook when `CRM_ENABLED=true`.

## Accounts and data separation

- Every table carries a `business_id`; every owner API reads the business from the logged-in session, never from the request, so one business can never see another's leads, chats or knowledge.
- Passwords are stored as PBKDF2-SHA256 hashes. Login uses a signed, HttpOnly session cookie (`SECRET_KEY`). Five failed logins in 15 minutes from one address are blocked for a while.
- Data is in SQLite (`leadbot.db`) on a laptop, or PostgreSQL when `DATABASE_URL` is set.

## Demo data

```bash
python -m app.seed
```

This **replaces everything** with two fictional businesses: BrightPath Solar (17 chats) and Stride Shoes (10 chats), each with leads in every stage, chats in English and Roman Urdu, unanswered questions, Q&A pairs and an audit history. With `SEED_DEMO=true` the server does this by itself when the database has no accounts.

## Put it online (Render + free PostgreSQL)

1. Create a free PostgreSQL database (for example on [neon.tech](https://neon.tech)) and copy its connection string. Keep it secret: it goes only into Render, never into git or chat.
2. On [render.com](https://render.com), choose **New > Blueprint** and pick this repository. Render reads `render.yaml`.
3. When asked, enter `DATABASE_URL`, `DEMO_PASSWORD`, and the AI key (`GEMINI_API_KEY` or `ANTHROPIC_API_KEY`). `SECRET_KEY` is generated by Render.
4. Open the `onrender.com` link. Sign-ups, leads and knowledge-base edits are kept in PostgreSQL, so they survive Render's free-tier restarts (uploaded files' text is stored in the database too).

The free service sleeps after a period without visits; the first visit then takes about a minute. Spending guards: at most `LLM_HOURLY_LIMIT` Claude replies per hour site-wide and `MAX_CLAUDE_MESSAGES_PER_CHAT` per conversation; beyond either, the offline bot answers.

## Project report

`report/report.md` is the report text. Build the styled PDF with:

```bash
pip install markdown
python report/build_report.py
```

## Project layout

```
app/main.py        API, accounts, pages
app/business.py    industry templates (add one entry to add an industry) and per-business bot settings
app/auth.py        sign-up/login: password hashing, session cookie, lockout
app/rag.py         knowledge-base retrieval, one index per business
app/ingest.py      reads PDF / Word / TXT / MD files and web pages into topics
app/llm.py         Gemini / Claude call + offline bot
app/scoring.py     lead scoring rules
app/classifier.py  trained lead classifier (scikit-learn)
app/crm.py         optional CRM webhook sync
app/db.py          SQLite or PostgreSQL storage
app/seed.py        two fictional demo businesses
static/landing.html, auth.html     product home page, sign-up and log-in
static/setup.*                     setup wizard with live preview
static/admin.*                     owner dashboard
static/bot.*                       the chat window (shown in the iframe)
static/widget.js                   the embed loader businesses paste on their site
static/demo/                       BrightPath Solar and Stride Shoes demo websites
kb/business.md                     solar template knowledge base
```

## Known limits (future work)

- The classifier's starter training set (62 rows) is hand-written and illustrative; replace it with real labeled conversations and re-run `python train_classifier.py`. It is shared by all businesses.
- One owner login per business (no team members or roles yet), and no password reset by email.
- Retrieval is TF-IDF; embeddings and a vector store would suit larger knowledge bases.
