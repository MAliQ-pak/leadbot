"""Turn uploaded files and web pages into plain text, then into topics (chunks) for the knowledge base.

Supported: .pdf (pypdf), .docx (read straight from the zip, no extra package), .txt, .md, and web pages.
"""
import io
import ipaddress
import os
import re
import socket
import time
import zipfile
from collections import Counter
from urllib import robotparser
from urllib.parse import urldefrag, urljoin, urlparse
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
        elif tag == "a":
            self.out.append(" ")  # so link text never runs into the word before it

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


def _check_public(url):
    """Refuse addresses inside the server's own network (localhost, 10.x, 192.168.x, cloud metadata...),
    so nobody can use the importer to read internal services. ALLOW_LOCAL_URLS=true allows them for testing."""
    host = urlparse(url).hostname or ""
    if os.getenv("ALLOW_LOCAL_URLS", "").lower() == "true":
        return
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        raise IngestError("Could not find that website. Check the address.")
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise IngestError("That address is on a private network, so it cannot be imported.")


def _get(url, client):
    """One page: (final url, response). Every redirect hop is checked too."""
    for _ in range(5):
        _check_public(url)
        r = client.get(url, timeout=10, follow_redirects=False)
        if r.is_redirect and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            continue
        return url, r
    raise IngestError("That address redirects too many times.")


def _page_text(r, url):
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
    return " ".join(parser.title.split()) or url, text


def _client():
    return httpx.Client(headers={"User-Agent": USER_AGENT})


def fetch_url(url):
    """Returns (page title, text). Only http(s); size and time limited."""
    if not re.match(r"^https?://", url, re.I):
        raise IngestError("Enter a full address starting with http:// or https://")
    try:
        with _client() as client:
            url, r = _get(url, client)
    except IngestError:
        raise
    except Exception:
        raise IngestError("Could not reach that website. Check the address and your internet connection.")
    title, text = _page_text(r, url)
    if len(text) < 40:
        raise IngestError("Found almost no text on that page (it may need JavaScript to load).")
    return title, text


# ---------- crawling a whole website ----------
USER_AGENT = "LeadBot-KB-import"
CRAWL_MODES = ("exact", "path", "domain")
MAX_CRAWL_PAGES = 30
CRAWL_SECONDS = 60
SKIP_EXT = re.compile(r"\.(jpe?g|png|gif|webp|svg|ico|pdf|zip|rar|mp4|mp3|avi|mov|docx?|xlsx?|pptx?|css|js|xml|json|woff2?|ttf)$", re.I)


class _Links(HTMLParser):
    """Every <a href> on the page, including the menu and footer (that is how the other pages are found)."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def _site(host):
    return (host or "").lower().removeprefix("www.")


def _normal(url):
    """One spelling per page: no #fragment, no ?query, no trailing slash, so it is fetched once."""
    u = urlparse(urldefrag(url)[0])
    path = re.sub(r"/index\.(html?|php)$", "/", u.path, flags=re.I).rstrip("/") or "/"  # /index.html is /
    port = f":{u.port}" if u.port else ""
    return f"{u.scheme.lower()}://{(u.hostname or '').lower()}{port}{path}"


def crawl(start, mode="domain", max_pages=MAX_CRAWL_PAGES, seconds=CRAWL_SECONDS):
    """Import a website the way a search engine reads it, politely and within limits.
    mode: "exact" = only this page; "path" = pages under this address's folder; "domain" = the whole site.
    Returns (pages, notes): pages = [(url, title, text)], notes = short messages about what was left out."""
    if mode not in CRAWL_MODES:
        raise IngestError("Unknown import mode.")
    if not re.match(r"^https?://", start, re.I):
        raise IngestError("Enter a full address starting with http:// or https://")
    if mode == "exact":
        title, text = fetch_url(start)
        return [(start, title, text)], []

    first = urlparse(start)
    site = _site(first.hostname)
    prefix = first.path.rstrip("/") if mode == "path" else ""

    def in_scope(url):
        u = urlparse(url)
        return (u.scheme in ("http", "https") and _site(u.hostname) == site and not SKIP_EXT.search(u.path)
                and (u.path == prefix or u.path.startswith(prefix + "/") if prefix else True))

    deadline, pages, notes, seen, texts = time.time() + seconds, [], [], set(), set()
    begin = _normal(start)
    queue = [begin]
    with _client() as client:
        robots = robotparser.RobotFileParser()  # the site's own rules for crawlers
        try:
            _, r = _get(f"{first.scheme}://{first.netloc}/robots.txt", client)
            robots.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            robots.parse([])
        try:  # a sitemap lists pages the menu may not link to; in_scope() below keeps only the wanted ones
            _, r = _get(f"{first.scheme}://{first.netloc}/sitemap.xml", client)
            if r.status_code == 200:
                queue += [_normal(u) for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)][:500]
        except Exception:
            pass
        while queue and len(pages) < max_pages:
            if time.time() > deadline:
                notes.append(f"stopped after {seconds} seconds")
                break
            url = queue.pop(0)
            if url in seen or not in_scope(url):
                continue
            seen.add(url)
            if not robots.can_fetch(USER_AGENT, url):
                notes.append(f"skipped {url} (the site asks crawlers not to read it)")
                continue
            try:
                final, r = _get(url, client)
                title, text = _page_text(r, final)
            except IngestError:
                if url == begin:
                    raise  # the starting page itself failed: tell the owner why
                continue
            except Exception:
                if url == begin:
                    raise IngestError("Could not reach that website. Check the address and your internet connection.")
                continue
            if len(text) >= 40 and text not in texts:  # the same page under two addresses is kept once
                texts.add(text)
                pages.append((final, title, text))
            links = _Links()
            links.feed(r.text)
            queue += [n for n in (_normal(urljoin(final, h)) for h in links.links) if n not in seen and in_scope(n)]
        if len(pages) >= max_pages and any(u not in seen for u in queue):
            notes.append(f"stopped at the limit of {max_pages} pages")
    if not pages:
        raise IngestError("Found almost no text on that website (it may need JavaScript to load).")
    return _drop_repeats(pages), notes


def _drop_repeats(pages):
    """Paragraphs repeated on most pages (a banner, the address) are kept on the first page only."""
    if len(pages) < 3:
        return pages
    paras = [[p.strip() for p in text.split("\n\n") if p.strip()] for _, _, text in pages]
    counts = Counter(p for ps in paras for p in set(ps))
    common = {p for p, n in counts.items() if n > len(pages) / 2 and not p.startswith("## ")}
    out = []
    for i, ((url, title, _), ps) in enumerate(zip(pages, paras)):
        keep = ps if i == 0 else [p for p in ps if p not in common]
        if keep:
            out.append((url, title, "\n\n".join(keep)))
    return out


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
