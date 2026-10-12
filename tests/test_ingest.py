"""Website import: private addresses are refused, and the crawler follows links and the sitemap, obeys
robots.txt, stays in scope and drops repeated paragraphs. A fake website (httpx.MockTransport) stands in
for the internet, so these tests are fast and offline."""
import httpx
import pytest

from app import ingest

NAV = ('<nav><a href="/">Home</a> <a href="/about.html">About</a> <a href="/blog/">Blog</a> '
       '<a href="https://www.google.com/">Google</a> <a href="/menu.pdf">PDF</a> <a href="/private/staff.html">Staff</a></nav>')


def page(title, body):
    return (f"<html><head><title>{title}</title></head><body>{NAV}<h1>{title}</h1>{body}"
            "<p>Kicks Corner, Mall Road Lahore. Call 0300-1112223 for orders any day of the week.</p></body></html>")


SITE = {
    "/": page("Home", "<p>We sell sneakers, joggers and formal shoes across Pakistan.</p>"),
    "/index.html": page("Home", "<p>We sell sneakers, joggers and formal shoes across Pakistan.</p>"),
    "/about.html": page("About", "<p>We started in 2019 as a small shop in Lahore.</p>"),
    "/blog": page("Blog", '<p>News and style tips.</p><a href="/blog/care.html">Care tips</a>'),
    "/blog/care.html": page("Care tips", "<p>Clean leather shoes with a soft cloth.</p>"),
    "/gift-cards.html": page("Gift cards", "<p>Gift cards from Rs 2,000 to Rs 10,000.</p>"),
    "/private/staff.html": page("Staff", "<p>Internal rota, never import.</p>"),
    "/robots.txt": "User-agent: *\nDisallow: /private/\n",
    "/sitemap.xml": "<urlset><url><loc>https://shop.example/gift-cards.html</loc></url></urlset>",
}


def handler(request):
    path = request.url.path.rstrip("/") or "/"
    if path in SITE or request.url.path in SITE:
        body = SITE.get(request.url.path, SITE.get(path))
        kind = "text/plain" if path.endswith((".txt", ".xml")) else "text/html"
        return httpx.Response(200, text=body, headers={"content-type": kind})
    return httpx.Response(404, text="not found")


@pytest.fixture
def fake_site(monkeypatch):
    monkeypatch.setattr(ingest, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(ingest, "_check_public", lambda url: None)  # the fake site has no real address


@pytest.mark.parametrize("url", ["http://localhost:8000/", "http://127.0.0.1/", "http://10.0.0.5/",
                                 "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data/"])
def test_private_addresses_are_refused(url):
    with pytest.raises(ingest.IngestError, match="private network"):
        ingest.fetch_url(url)


def test_only_http_addresses():
    with pytest.raises(ingest.IngestError):
        ingest.crawl("ftp://shop.example/", "domain")


def test_whole_site(fake_site):
    pages, notes = ingest.crawl("https://shop.example/", "domain")
    titles = sorted(t for _, t, _ in pages)
    assert titles == ["About", "Blog", "Care tips", "Gift cards", "Home"]  # gift cards: only in the sitemap
    assert any("asks crawlers not to read it" in n for n in notes)  # robots.txt was obeyed
    assert all("google" not in u and not u.endswith(".pdf") for u, _, _ in pages)


def test_index_html_is_the_same_page(fake_site):
    pages, _ = ingest.crawl("https://shop.example/", "domain")
    assert [t for _, t, _ in pages].count("Home") == 1


def test_section_only(fake_site):
    pages, _ = ingest.crawl("https://shop.example/blog/", "path")
    assert sorted(t for _, t, _ in pages) == ["Blog", "Care tips"]


def test_single_page(fake_site):
    pages, notes = ingest.crawl("https://shop.example/about.html", "exact")
    assert [t for _, t, _ in pages] == ["About"] and notes == []


def test_page_limit(fake_site):
    pages, notes = ingest.crawl("https://shop.example/", "domain", max_pages=2)
    assert len(pages) == 2 and "stopped at the limit of 2 pages" in notes


def test_repeated_paragraph_kept_once(fake_site):
    pages, _ = ingest.crawl("https://shop.example/", "domain")
    assert sum("Mall Road" in text for _, _, text in pages) == 1


def test_link_text_does_not_run_into_the_previous_word(fake_site):
    pages, _ = ingest.crawl("https://shop.example/blog/", "path")
    blog = next(text for _, t, text in pages if t == "Blog")
    assert "tips. Care tips" in blog


def test_chunking_splits_on_headings():
    chunks = ingest.chunk("Doc", "## Prices\nSneakers Rs 3,999.\n\n## Delivery\n3 to 5 days.")
    assert len(chunks) >= 2
