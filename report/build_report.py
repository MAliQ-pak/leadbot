"""Build the styled FYP report PDF from report/report.md.

    python report/build_report.py

Steps: Markdown -> HTML (Fraunces + Inter, the LeadBot colour palette) -> PDF printed by Microsoft
Edge or Google Chrome in headless mode. The three figures are drawn here as SVG from LIVE data:
the classifier weights come from models/lead_classifier.joblib and the retrieval scores from
app/rag.py, so the figures always match the code. Needs: pip install markdown
"""
import html
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import markdown

# ---------- cover page details: fill these in, then rebuild ----------
TITLE = "LeadBot"
SUBTITLE = "An AI lead-qualification chatbot for small businesses"
STUDENT = "Muhammad Ali"
ROLL_NUMBER = ""      # e.g. "FA21-BSCS-0123"
SUPERVISOR = ""       # e.g. "Dr. A. Khan"
DEPARTMENT = ""       # e.g. "Department of Computer Science"
UNIVERSITY = ""       # e.g. "University of ..."
REPORT_DATE = date.today().strftime("%B %Y")
LIVE_URL = "https://leadbot-g3d4.onrender.com"
CODE_URL = "https://github.com/MAliQ-pak/leadbot"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = HERE / "report.md"
OUT_HTML = HERE / "LeadBot-FYP-Report.html"
OUT_PDF = HERE / "LeadBot-FYP-Report.pdf"

# the design specification's palette
C = {
    "green": "#3E5C3F", "green_d": "#2D462F", "green_dk": "#243A27", "ink": "#1C1B18",
    "text": "#4B463D", "text2": "#5F5A51", "muted": "#8A8478", "faint": "#A39B8B",
    "cream": "#F7F2EA", "card": "#FFFDF8", "line": "#E7E0D4", "line2": "#D9D2C4",
    "tint": "#DEEBDB", "tint2": "#E8F0E4", "sand": "#F2E3CF", "brown": "#7A5A2A",
    "blue": "#2B5CE6", "navy": "#2E3A6E",
}
FONT_BODY = "Inter, 'Segoe UI', sans-serif"
FONT_DISPLAY = "Fraunces, Georgia, serif"


# ---------- figures ----------
def svg_text(x, y, words, size=13, weight=400, fill=None, anchor="start", family=FONT_BODY, italic=False):
    style = " font-style='italic'" if italic else ""
    return (f"<text x='{x}' y='{y}' font-family=\"{family}\" font-size='{size}' font-weight='{weight}'"
            f" fill='{fill or C['ink']}' text-anchor='{anchor}'{style}>{html.escape(str(words))}</text>")


def fig_architecture():
    edge, W, H = C["muted"], 248, 56

    def box(x, y, w, h, main=False):
        return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='8' fill='{C['tint'] if main else '#FFFFFF'}'"
                f" stroke='{C['green'] if main else C['line2']}' stroke-width='{2 if main else 1.25}'/>")

    def card(x, y, w, h, name, lines, main=False):
        out = box(x, y, w, h, main) + svg_text(x + 12, y + 24, name, 13, 600)
        for i, line in enumerate(lines):
            out += svg_text(x + 12, y + 42 + 18 * i, line, 11.5, 400, C["ink"] if main else C["text2"])
        return out

    arrows = [("M204 120H256", ""), ("M204 408H256", ""), ("M380 148V164", ""), ("M380 220V236", ""),
              ("M380 292V308", ""), ("M556 192H504", ""), ("M504 264H556", "both"), ("M504 336H556", ""),
              ("M504 408H556", "both")]
    paths = "".join(f"<path d='{d}' marker-end='url(#a)'{' marker-start=\"url(#a)\"' if both else ''}/>" for d, both in arrows)
    return f"""<svg viewBox='0 0 760 470' xmlns='http://www.w3.org/2000/svg' role='img' aria-label='LeadBot architecture'>
<defs><marker id='a' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='6' markerHeight='6' orient='auto-start-reverse'><path d='M0 0L10 5L0 10z' fill='{edge}'/></marker></defs>
{svg_text(24, 28, "Every reply is grounded in the owner's knowledge base, with an offline fallback", 15, 600, family=FONT_DISPLAY)}
<rect x='240' y='50' width='280' height='402' rx='10' fill='{C['cream']}' stroke='{C['line']}' stroke-width='1.25'/>
{svg_text(256, 76, "FastAPI server, one process", 12.5, 600, C['green_d'])}
<g fill='none' stroke='{edge}' stroke-width='1.25'>{paths}</g>
{card(24, 92, 180, H, "Website visitor", ["chat widget on any site"])}
{card(24, 380, 180, H, "Business owner", ["admin panel, password"])}
{card(256, 92, W, H, "Chat API", ["saves the message, runs each step"])}
{card(256, 164, W, H, "Retrieval", ["TF-IDF, top 3 topics, 0.3 threshold"])}
{card(256, 236, W, H, "AI layer", ["JSON reply; offline bot if AI fails"], main=True)}
{card(256, 308, W, H, "Lead scoring", ["rules + classifier, blended 50/50"])}
{card(256, 380, W, H, "Admin API", ["pipeline, audit log, KB; login"])}
{card(556, 164, 180, H, "Main text", ["kb/business.md"])}
{card(556, 236, 180, H, "Gemini or Claude", ["external AI over HTTPS"])}
{card(556, 308, 180, 128, "SQLite database", ["leads and messages", "Q&A pairs, documents", "unanswered, audit log"])}
</svg>"""


def live_weights():
    sys.path.insert(0, str(ROOT))
    import joblib
    from app import classifier
    model = joblib.load(classifier.MODEL_PATH)
    names = {"has_phone": "Phone shared", "has_budget": "Budget stated", "has_timeline": "Timeline stated",
             "asked_price_or_purchase": "Asked about price or buying", "has_name": "Name shared",
             "has_email": "Email shared", "urgent": "Urgent wording", "has_need": "Need stated",
             "message_length": "Message length", "questions": "Number of questions",
             "not_now": "Not-now wording (just checking, next year)"}
    rows = [(k, names.get(k, k), float(w)) for k, w in zip(classifier.FEATURE_NAMES, model.coef_[0])]
    return sorted(rows, key=lambda r: -r[2])


def fig_weights(rows):
    lo, hi = min(r[2] for r in rows), max(r[2] for r in rows)
    left, right = 300, 690
    unit = (right - left) / (hi - lo)
    x0 = left - lo * unit
    X = lambda v: x0 + v * unit
    y0, step = 92, 26
    top_pos = max(rows, key=lambda r: r[2])
    top_neg = min(rows, key=lambda r: r[2])
    phrase = {"has_phone": "a shared phone number", "has_budget": "a stated budget", "has_timeline": "a stated timeline",
              "not_now": "Not-now wording", "has_email": "a shared email", "has_name": "a shared name"}
    out = [svg_text(24, 28, f"{phrase.get(top_neg[0], top_neg[1])} pulls a lead down hardest; {phrase.get(top_pos[0], top_pos[1].lower())} lifts it most", 15, 600, family=FONT_DISPLAY),
           svg_text(24, 50, "Logistic-regression weight per feature. Right of zero = more likely qualified.", 11.5, 400, C["text2"]),
           f"<line x1='{x0:.1f}' x2='{x0:.1f}' y1='{y0 - 16}' y2='{y0 + step * len(rows) - 8}' stroke='{C['muted']}' stroke-width='1'/>",
           svg_text(x0, y0 - 22, "0", 11, 400, C["muted"], "middle")]
    for i, (key, label, w) in enumerate(rows):
        y = y0 + i * step
        accent = key == "not_now"
        x = X(w) if w < 0 else x0
        out.append(svg_text(left - 12, y + 4, label, 12, 600 if accent else 400, C["ink"] if accent else C["text2"], "end"))
        out.append(f"<rect x='{x:.1f}' y='{y - 8}' width='{abs(X(w) - x0):.1f}' height='16' rx='3' fill='{C['brown'] if accent else C['line2']}'/>")
        out.append(svg_text((x0 + 8) if w < 0 else (X(w) + 8), y + 4, f"{'+' if w > 0 else ''}{w:.2f}", 12, 600 if accent else 400))
    height = y0 + step * len(rows) + 6
    return f"<svg viewBox='0 0 760 {height}' xmlns='http://www.w3.org/2000/svg' role='img' aria-label='Classifier weights'>{''.join(out)}</svg>"


QUESTIONS = [  # (question, covered by the knowledge base?, note)
    ("what is the warranty?", True, ""), ("do you offer installments?", True, ""),
    ("kist milti hai? (Roman Urdu)", True, ""), ("maintenance plan", True, ""),
    ("book a free site visit", True, ""), ("how long does it take?", True, ""),
    ("what are your timings?", True, "after adding a synonym"), ("do you do net metering?", True, "after adding a synonym"),
    ("what are your packages?", True, "after adding a Packages topic"), ("price list", True, "after adding a synonym"),
    ("what areas do you serve?", True, "after adding a synonym"), ("how much is a 5kw system?", True, ""),
    ("5kw ki qeemat kitni hai? (Roman Urdu)", True, ""),
    ("do you have jobs?", False, ""), ("do you install in Multan?", False, "missed: the city list implies no"),
    ("is there a discount for students?", False, ""), ("what brand of inverter do you use?", False, ""),
    ("are panels made in china?", False, ""), ("can I pay with credit card?", False, ""),
    ("do you sell generators?", False, ""),
]


def live_retrieval():
    sys.path.insert(0, str(ROOT))
    from app import db, rag
    db.init()
    kb = rag.get_kb()
    rows = []
    for q, covered, note in QUESTIONS:
        query = q.replace(" (Roman Urdu)", "")
        rows.append((q, covered, note, kb.search_scored(query)[0]["score"]))
    covered_rows = sorted([r for r in rows if r[1]], key=lambda r: -r[3])
    other_rows = sorted([r for r in rows if not r[1]], key=lambda r: -r[3])
    return covered_rows + other_rows, rag.CONFIDENT


def fig_retrieval(rows, threshold):
    x0, span = 330, 300
    X = lambda v: x0 + min(v, 1) * span
    thr = X(threshold)
    low_cov = min(r[3] for r in rows if r[1])
    high_off = max(r[3] for r in rows if not r[1])
    out = [svg_text(24, 28, f"Answerable questions scored {low_cov:.2f} or more; off-topic ones {high_off:.2f} or less", 15, 600, family=FONT_DISPLAY),
           svg_text(24, 50, f"Best retrieval score per test question (0 to 1). Below {threshold} the bot says it is not sure and logs the question.", 11.5, 400, C["text2"])]
    y, last_group, ys = 96, None, []
    for q, covered, note, score in rows:
        if covered != last_group:
            y += 22 if last_group is not None else 0
            out.append(svg_text(24, y, "Covered by the knowledge base" if covered else "Not covered", 12.5, 600, C["green_d"]))
            y += 26
            last_group = covered
        ys.append(y)
        near = X(score) < thr < X(score) + 34
        vx = (thr if near else X(score)) + 6
        out.append(svg_text(x0 - 10, y + 4, q, 12, 400, C["text2"], "end"))
        out.append(f"<rect x='{x0}' y='{y - 7}' width='{X(score) - x0:.1f}' height='14' rx='3' fill='{C['green'] if covered else C['line2']}'/>")
        out.append(svg_text(vx, y + 4, f"{score:.2f}", 12))
        if note:
            out.append(svg_text(vx + 36, y + 4, note, 11, 400, C["muted"]))
        y += 22
    out.insert(2, f"<line x1='{thr}' x2='{thr}' y1='74' y2='{ys[-1] + 14}' stroke='{C['brown']}' stroke-width='1.25' stroke-dasharray='4 4'/>"
                  + svg_text(thr + 6, 70, f"{threshold} confidence threshold", 11.5, 400, C["brown"]))
    return f"<svg viewBox='0 0 760 {ys[-1] + 30}' xmlns='http://www.w3.org/2000/svg' role='img' aria-label='Retrieval scores'>{''.join(out)}</svg>"


def figure(svg, caption, n):
    return f"<figure>{svg}<figcaption><b>Figure {n}.</b> {html.escape(caption)}</figcaption></figure>"


# ---------- page ----------
CSS = f"""
@font-face {{ font-family: Inter; src: url('../static/fonts/Inter-Variable.ttf'); font-weight: 100 900; }}
@font-face {{ font-family: Fraunces; src: url('../static/fonts/Fraunces-Variable.ttf'); font-weight: 100 900; font-style: normal; }}
@font-face {{ font-family: Fraunces; src: url('../static/fonts/Fraunces-Italic-Variable.ttf'); font-weight: 100 900; font-style: italic; }}
@page {{ size: A4; margin: 20mm 19mm 22mm;
  @bottom-left {{ content: "LeadBot \\00B7  Final Year Project Report"; font: 500 7.5pt Inter, sans-serif; color: {C['muted']}; }}
  @bottom-right {{ content: counter(page); font: 600 8pt Inter, sans-serif; color: {C['green']}; }} }}
@page :first {{ margin: 0; @bottom-left {{ content: none; }} @bottom-right {{ content: none; }} }}
* {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
html {{ font: 400 10pt/1.62 {FONT_BODY}; color: {C['text']}; }}
body {{ margin: 0; hyphens: auto; }}
*, *::before, *::after, text {{ font-variation-settings: 'WONK' 0 !important; }}  /* Fraunces: standard letter shapes, not the quirky ones */
h2, h3, h4 {{ font-family: {FONT_DISPLAY}; font-weight: 600; color: {C['ink']}; line-height: 1.2; break-after: avoid; }}
h2 {{ font-size: 22pt; margin: 0 0 14pt; padding-bottom: 8pt; border-bottom: 1.5pt solid {C['line']}; break-before: page; }}
h3 {{ font-size: 13pt; margin: 18pt 0 6pt; }}
h2 .num, h3 .num {{ color: {C['green']}; margin-right: 6pt; }}
p {{ margin: 0 0 8pt; orphans: 3; widows: 3; }}
strong, b {{ font-family: {FONT_DISPLAY}; font-weight: 600; color: {C['ink']}; }}
em {{ font-family: {FONT_DISPLAY}; font-style: italic; font-weight: 600; }}
a {{ color: {C['green']}; text-decoration: none; border-bottom: 0.6pt solid {C['tint']}; }}
code {{ hyphens: none; white-space: nowrap; font: 500 8.6pt Consolas, monospace; color: {C['green_d']}; background: #EFEAE0; padding: 0.5pt 3pt; border-radius: 3pt; }}
ul, ol {{ margin: 0 0 9pt; padding-left: 16pt; }}
li {{ margin-bottom: 3pt; }}
li::marker {{ color: {C['green']}; font-weight: 600; }}
table {{ width: 100%; border-collapse: separate; border-spacing: 0; margin: 6pt 0 12pt; font-size: 8.6pt; line-height: 1.45;
  border: 0.75pt solid {C['line']}; border-radius: 6pt; overflow: hidden; }}
th {{ background: {C['green_d']}; color: #FFFFFF; font-weight: 600; text-align: left; padding: 6pt 8pt; }}
td {{ padding: 5pt 8pt; border-top: 0.75pt solid {C['line']}; vertical-align: top; color: {C['text']}; }}
tr:nth-child(even) td {{ background: {C['card']}; }}
tr {{ break-inside: avoid; }}
td:first-child {{ color: {C['ink']}; font-weight: 500; }}
.swatch {{ display: inline-block; width: 9pt; height: 9pt; border-radius: 2pt; margin: 0 4pt -1pt 0; border: 0.5pt solid rgba(0,0,0,.15); }}
figure {{ margin: 10pt 0 14pt; padding: 12pt 12pt 8pt; background: #FFFFFF; border: 0.75pt solid {C['line']}; border-radius: 8pt; break-inside: avoid; }}
figure svg {{ width: 100%; height: auto; display: block; }}
figcaption {{ font-size: 8pt; color: {C['muted']}; margin-top: 6pt; }}
figcaption b {{ font-family: {FONT_BODY}; font-weight: 600; color: {C['green_d']}; }}
.formula {{ margin: 8pt 0 12pt; padding: 10pt 14pt; background: {C['tint2']}; border-left: 3pt solid {C['green']}; border-radius: 0 6pt 6pt 0;
  font: italic 600 12pt {FONT_DISPLAY}; color: {C['green_d']}; }}
.qa p {{ break-inside: avoid; }}  /* keep each question with its answer */
.qa p > strong:first-child {{ display: block; margin: 10pt 0 2pt; font-size: 10.5pt; color: {C['green_d']}; }}

/* cover */
.cover {{ height: 297mm; width: 210mm; padding: 26mm 22mm 22mm; display: flex; flex-direction: column; break-after: page;
  background: linear-gradient(160deg, #EEF3E9 0%, #E5EEDA 100%); position: relative; }}
.cover .brand {{ display: flex; align-items: center; gap: 8pt; font: 600 13pt {FONT_DISPLAY}; color: {C['ink']}; }}
.cover .brand i {{ color: {C['green']}; font-style: italic; }}
.cover .eyebrow {{ margin-top: 52mm; font: 600 9pt {FONT_BODY}; letter-spacing: .16em; text-transform: uppercase; color: {C['green']}; }}
.cover h1 {{ font: 600 58pt/1 {FONT_DISPLAY}; color: {C['ink']}; margin: 8pt 0 10pt; letter-spacing: -.01em; }}
.cover .sub {{ font: italic 600 20pt/1.25 {FONT_DISPLAY}; color: {C['green']}; max-width: 140mm; }}
.cover .rule {{ width: 34mm; height: 2.5pt; background: {C['green']}; margin: 16pt 0; border-radius: 2pt; }}
.cover .lede {{ font-size: 10.5pt; color: {C['text']}; max-width: 135mm; }}
.cover dl {{ margin-top: auto; display: grid; grid-template-columns: 34mm 1fr; gap: 5pt 10pt; font-size: 9.5pt;
  background: rgba(255,253,248,.75); border: 0.75pt solid {C['line']}; border-radius: 10pt; padding: 14pt 16pt; }}
.cover dt {{ color: {C['muted']}; font-weight: 500; }}
.cover dd {{ margin: 0; color: {C['ink']}; font-weight: 600; }}
.cover dd.todo {{ color: {C['faint']}; font-weight: 400; font-style: italic; }}
.cover .sun {{ position: absolute; right: 22mm; top: 22mm; width: 30mm; }}

/* contents */
.toc h2 {{ break-before: auto; }}
.toc ol {{ list-style: none; padding: 0; columns: 1; }}
.toc li {{ display: flex; gap: 10pt; padding: 6pt 0; border-bottom: 0.75pt dotted {C['line2']}; font-size: 10.5pt; }}
.toc li span {{ width: 18pt; color: {C['green']}; font-weight: 600; }}
.toc a {{ color: {C['ink']}; border: 0; }}
"""

SUN = (f"<svg class='sun' viewBox='0 0 32 32'><circle cx='16' cy='16' r='7' fill='{C['green']}'/><g stroke='{C['green']}' stroke-width='2.5' stroke-linecap='round'>"
       "<path d='M16 2v4M16 26v4M2 16h4M26 16h4M6 6l2.8 2.8M23.2 23.2 26 26M6 26l2.8-2.8M23.2 8.8 26 6'/></g></svg>")


def cover():
    def row(label, value, hint):
        return f"<dt>{label}</dt>" + (f"<dd>{html.escape(value)}</dd>" if value else f"<dd class='todo'>{hint}</dd>")
    return f"""<section class='cover'>
<div class='brand'>{SUN.replace("class='sun'", "width='20'")}LeadBot <i>FYP</i></div>
{SUN}
<div class='eyebrow'>Final Year Project Report</div>
<h1>{html.escape(TITLE)}</h1>
<div class='sub'>{html.escape(SUBTITLE)}</div>
<div class='rule'></div>
<p class='lede'>A website chatbot that answers from a business's own knowledge base in English and Roman Urdu,
captures and scores leads, and gives the owner a pipeline, an audit log and four ways to train the bot.</p>
<dl>
{row("Student", STUDENT, "add in build_report.py")}
{row("Roll number", ROLL_NUMBER, "add in build_report.py")}
{row("Supervisor", SUPERVISOR, "add in build_report.py")}
{row("Department", DEPARTMENT, "add in build_report.py")}
{row("University", UNIVERSITY, "add in build_report.py")}
{row("Date", REPORT_DATE, "")}
{row("Live demo", LIVE_URL, "")}
{row("Source code", CODE_URL, "")}
</dl>
</section>"""


def add_swatches(body):
    """In the colour-scheme table (the one with a "Hex" column), put a swatch before every colour
    in the Hex cells, and only there."""
    def per_table(m):
        table = m.group(0)
        if "<th>Hex</th>" not in table:
            return table

        def per_row(r):
            cells = re.findall(r"<td>.*?</td>", r.group(0), re.S)
            if len(cells) < 2:
                return r.group(0)
            colour = re.compile(r"#[0-9A-Fa-f]{6}|hsl\([^)]*\)")
            hexed = colour.sub(lambda c: f"<span class='swatch' style='background:{c.group(0)}'></span>{c.group(0)}", cells[1])
            return r.group(0).replace(cells[1], hexed, 1)
        return re.sub(r"<tr>.*?</tr>", per_row, table, flags=re.S)
    return re.sub(r"<table>.*?</table>", per_table, body, flags=re.S)


def build_html():
    md = SOURCE.read_text(encoding="utf-8")
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists", "toc"])

    weights = live_weights()
    retrieval, threshold = live_retrieval()
    n_cov = sum(1 for r in retrieval if r[1])
    figs = {
        "architecture": figure(fig_architecture(), "LeadBot architecture: ten components in one server process.", 1),
        "weights": figure(fig_weights(weights), f"Classifier weights, read from models/lead_classifier.joblib ({len(weights)} features, trained on all 62 labelled leads).", 2),
        "retrieval": figure(fig_retrieval(retrieval, threshold),
                            f"Retrieval scores computed by app/rag.py on the BrightPath knowledge base when this report was built: "
                            f"{n_cov} answerable and {len(retrieval) - n_cov} off-topic questions.", 3),
    }
    for key, fig in figs.items():
        body = body.replace(f"<p>[[FIG:{key}]]</p>", fig)
    body = body.replace("<p>[[FORMULA]]</p>",
                        "<div class='formula'>score = (1 &minus; w) &times; rules + w &times; 100 &times; P(qualified)</div>")
    assert "[[" not in body, "a placeholder was not replaced"

    # section numbers in green
    body = re.sub(r"<(h[23]) id=\"([^\"]+)\">((?:[A-Z]\.)?\d+(?:\.\d+)?) ", r"<\1 id='\2'><span class='num'>\3</span>", body)
    body = add_swatches(body)
    # appendix: questions as headings of their answers
    body = body.replace("<h2 id=\"appendix-a-viva-questions-and-answers\">", "<div class='qa'><h2 id='appendix-a-viva-questions-and-answers'>") + "</div>"

    heads = re.findall(r"<h2 id=['\"]([^'\"]+)['\"]>(?:<span class='num'>([^<]+)</span>)?([^<]+)</h2>", body)
    toc = "".join(f"<li><span>{num or ''}</span><a href='#{hid}'>{html.escape(name.strip())}</a></li>" for hid, num, name in heads)
    page = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><title>LeadBot: Final Year Project Report</title>
<style>{CSS}</style></head><body>{cover()}
<section class='toc'><h2>Contents</h2><ol>{toc}</ol></section>
{body}</body></html>"""
    OUT_HTML.write_text(page, encoding="utf-8")
    return OUT_HTML


def find_browser():
    for p in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]:
        if Path(p).exists():
            return p
    return shutil.which("msedge") or shutil.which("google-chrome") or shutil.which("chromium")


def print_pdf(html_path):
    browser = find_browser()
    if not browser:
        sys.exit("No Edge or Chrome found: open the .html file in a browser and print it to PDF.")
    OUT_PDF.unlink(missing_ok=True)
    profile = tempfile.mkdtemp(prefix="leadbot-pdf-")  # own profile: never clashes with an open browser
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
                    f"--user-data-dir={profile}", "--virtual-time-budget=8000", f"--print-to-pdf={OUT_PDF}", html_path.as_uri()],
                   capture_output=True, timeout=180)
    # the browser can return before the file is fully written: wait until its size stops changing
    last = -1
    for _ in range(120):
        size = OUT_PDF.stat().st_size if OUT_PDF.exists() else -1
        if size > 0 and size == last:
            break
        last = size
        time.sleep(0.5)
    shutil.rmtree(profile, ignore_errors=True)
    if not OUT_PDF.exists():
        sys.exit("The browser did not write the PDF: open the .html file in a browser and print it to PDF.")
    return OUT_PDF


if __name__ == "__main__":
    pdf = print_pdf(build_html())
    print(f"Wrote {pdf} ({pdf.stat().st_size // 1024} KB)")
