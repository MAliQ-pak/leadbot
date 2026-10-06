"""Turn uploaded files and web pages into plain text, then into topics (chunks) for the knowledge base.

Supported: .pdf (pypdf), .docx (read straight from the zip, no extra package), .txt, .md, and web pages.
"""
import io
import re
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree

import httpx

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PAGE_BYTES = 2 * 1024 * 1024
CHUNK_CHARS = 700  # roughly one paragraph or two; small chunks retrieve more precisely


class IngestError(Exception):
    """A problem the admin should see (unsupported file, empty page, ...)."""


# ---------- files ----------
def extract_file(filename, data):
    if len(data) > MAX_FILE_BYTES:
        raise IngestError("File is larger than 5 MB.")
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in ("txt", "md"):
        text = data.decode("utf-8", errors="replace")
    elif ext == "pdf":
        text = _pdf_text(data)
    elif ext == "docx":
        text = _docx_text(data)
    else:
        raise IngestError("Unsupported file type. Use PDF, DOCX, TXT or MD.")
    if not text.strip():
        raise IngestError("No readable text found (a scanned PDF has images, not text).")
    return text


def _pdf_text(data):
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        raise IngestError(f"Could not read this PDF ({e}).")


def _docx_text(data):
    """A .docx is a zip; the text lives in word/document.xml. Heading styles become '## ' topics."""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ElementTree.fromstring(z.read("word/document.xml"))
    except Exception:
        raise IngestError("Could not read this Word file. Save it as .docx and try again.")
    lines = []
    for p in root.iter(f"{{{ns['w']}}}p"):
        text = "".join(t.text or "" for t in p.iter(f"{{{ns['w']}}}t")).strip()
        if not text:
            continue
        style = p.find("w:pPr/w:pStyle", ns)
        is_heading = style is not None and "heading" in (style.get(f"{{{ns['w']}}}val") or "").lower()
        lines.append(("## " + text) if is_heading else text)
    return "\n\n".join(lines)


# ---------- web pages ----------
class _PageText(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "form", "button", "head"}
    BLOCK = {"p", "li", "div", "section", "article", "td", "br", "tr", "dd", "dt"}

    def __init__(self):
        super().__init__()
        self.out, self.skip, self.title, self._in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in ("h1", "h2", "h3"):
            self.out.append("\n\n## ")
        elif tag in self.BLOCK:
            self.out.append("\n\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in ("h1", "h2", "h3"):
            self.out.append("\n\n")  # blank line so the heading is its own paragraph

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.out.append(data)


def fetch_url(url):
    """Returns (page title, text). Only http(s); size and time limited."""
    if not re.match(r"^https?://", url, re.I):
        raise IngestError("Enter a full address starting with http:// or https://")
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True, headers={"User-Agent": "LeadBot-KB-import"})
    except Exception:
        raise IngestError("Could not reach that website. Check the address and your internet connection.")
    if r.status_code >= 400:
        raise IngestError(f"The website answered with error {r.status_code}.")
    if "html" not in r.headers.get("content-type", "html"):
        raise IngestError("That address is not a web page.")
    if len(r.content) > MAX_PAGE_BYTES:
        raise IngestError("That page is too large (over 2 MB).")
    parser = _PageText()
    parser.feed(r.text)
    text = re.sub(r"[ \t]+", " ", "".join(parser.out))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if len(text) < 40:
        raise IngestError("Found almost no text on that page (it may need JavaScript to load).")
    return parser.title.strip() or url, text


# ---------- chunking ----------
def chunk(name, text):
    """Split text into (section title, body) topics. Headings start new topics; long
    sections are cut into ~CHUNK_CHARS pieces on paragraph boundaries."""
    name = re.sub(r"\.(pdf|docx|txt|md)$", "", name, flags=re.I)  # "rates.pdf" -> "rates"
    sections, title, buf, para = [], name, [], []

    def end_para():
        if para:
            buf.append(" ".join(para))
            para.clear()

    for line in text.replace("\r\n", "\n").split("\n"):
        line = " ".join(line.split())
        m = re.match(r"^#{1,3}\s+(.*)", line)
        if m and len(m.group(1)) < 120:  # a heading line starts a new topic
            end_para()
            if buf:
                sections.append((title, buf))
            title, buf = m.group(1).strip() or name, []
        elif line:
            para.append(line)
        else:  # blank line ends a paragraph
            end_para()
    end_para()
    if buf:
        sections.append((title, buf))

    out = []
    for title, paras in sections:
        piece = ""
        for p in paras:
            if piece and len(piece) + len(p) > CHUNK_CHARS:
                out.append((title, piece))
                piece = ""
            piece = (piece + " " + p).strip()
        if piece:
            out.append((title, piece))
    # number repeated titles so each topic is identifiable in the admin panel
    seen, numbered = {}, []
    for title, body in out:
        seen[title] = seen.get(title, 0) + 1
        numbered.append((title if seen[title] == 1 else f"{title} ({seen[title]})", body))
    return numbered
