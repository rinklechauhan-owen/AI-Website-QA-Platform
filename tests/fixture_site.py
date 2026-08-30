"""A synthetic website served over HTTP, for testing the crawler against real conditions.

The brief lists the situations a crawler has to survive — redirects, 404s, 500s, broken links,
duplicate titles, missing metadata, missing alt text, timeouts, query-parameter duplicates,
robots restrictions, sitemaps. Rather than trusting a live site to keep exhibiting all of them,
this fixture exhibits every one on demand, so the tests are deterministic and offline.

Start it with :func:`serve`, which returns a base URL and a shutdown callable.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, Tuple
from urllib.parse import urlsplit


def _page(title: str, body: str, *, description: str = "", extra_head: str = "") -> str:
    meta = f'<meta name="description" content="{description}">' if description else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{title}</title>{meta}{extra_head}</head>
<body>{body}</body>
</html>"""


# A small site with a deliberate defect on almost every page.
PAGES: Dict[str, str] = {
    "/": _page(
        "Home — Fixture Site",
        """<h1>Fixture Site</h1>
        <p>A small site built to exercise a crawler against real conditions.</p>
        <nav>
          <a href="/about">About</a>
          <a href="/services">Services</a>
          <a href="/blog/">Blog</a>
          <a href="/duplicate-a">Duplicate A</a>
          <a href="/duplicate-b">Duplicate B</a>
          <a href="/no-meta">No meta</a>
          <a href="/no-h1">No H1</a>
          <a href="/missing-alt">Missing alt</a>
          <a href="/old-page">Old page (redirects)</a>
          <a href="/gone">Broken link</a>
          <a href="/boom">Server error</a>
          <a href="/private/secret">Robots-blocked</a>
          <a href="/deep/1">Deep chain</a>
          <a href="/hreflang">Hreflang</a>
          <a href="/noindex">Noindex</a>
          <a href="/x-robots">Header noindex</a>
          <a href="/search?q=shoes">Query page</a>
          <a href="/search?q=shoes&utm_source=news">Same page, tracked</a>
          <a href="/about/">About with slash</a>
          <a href="/about#team">About with fragment</a>
          <a href="https://external.invalid/page">External site</a>
          <a href="/report.pdf">A PDF</a>
          <a href="/logo.png">An image</a>
          <a href="mailto:hello@fixture.invalid">Email</a>
        </nav>""",
        description="The home page of a fixture site used to test a website crawler end to end.",
    ),
    "/about": _page(
        "About — Fixture Site",
        "<h1>About</h1><p>We exist to be crawled.</p><a href='/'>Home</a>",
        description="About the fixture site, which exists purely so a crawler can be tested.",
    ),
    "/services": _page(
        "Services — Fixture Site",
        "<h1>Services</h1><p>Things we do.</p><a href='/'>Home</a><a href='/orphan-target'>x</a>",
        description="Services offered by the fixture site, listed for crawler testing purposes.",
    ),
    "/blog/": _page(
        "Blog — Fixture Site",
        "<h1>Blog</h1><a href='/blog/post-1'>Post 1</a><a href='/blog/post-2'>Post 2</a>",
        description="The blog index of the fixture site, linking to a couple of test posts.",
    ),
    "/blog/post-1": _page(
        "Post 1 — Fixture Site",
        "<h1>Post 1</h1><p>" + ("Body copy. " * 60) + "</p><a href='/blog/'>Back</a>",
        description="The first test post, long enough not to be flagged as thin content.",
    ),
    "/blog/post-2": _page(
        "Post 2 — Fixture Site",
        "<h1>Post 2</h1><p>Short.</p><a href='/blog/'>Back</a>",
        description="The second test post, deliberately short so thin content is detected.",
    ),
    # Two pages sharing a title and description — site-wide duplicate detection.
    "/duplicate-a": _page(
        "Duplicated Title",
        "<h1>Duplicated Heading</h1><p>Page A.</p>",
        description="This description is used on two pages so duplication can be detected.",
    ),
    "/duplicate-b": _page(
        "Duplicated Title",
        "<h1>Duplicated Heading</h1><p>Page B.</p>",
        description="This description is used on two pages so duplication can be detected.",
    ),
    "/no-meta": _page("No Meta Description", "<h1>No meta</h1><p>Missing a description.</p>"),
    "/no-h1": _page(
        "No H1 Here",
        "<h2>Only an H2</h2><p>This page has no first-level heading at all.</p>",
        description="A page with no H1, so the missing-heading rule has something to find.",
    ),
    "/missing-alt": _page(
        "Missing Alt Text",
        """<h1>Images</h1>
        <img src="/a.png">
        <img src="/b.png" alt="">
        <img src="/c.png" alt="A described image">""",
        description="A page whose images are missing alt text, for the accessibility checks.",
    ),
    "/noindex": _page(
        "Noindex Page",
        "<h1>Not for indexing</h1><p>This one asks not to be indexed.</p>",
        description="A page carrying a noindex directive so indexability can be tested.",
        extra_head='<meta name="robots" content="noindex,nofollow">',
    ),
    "/orphan-target": _page(
        "Linked Once",
        "<h1>Linked once</h1><p>Reached from services only.</p>",
        description="A page linked from exactly one other page, for inlink counting.",
    ),
    "/search": _page(
        "Search — Fixture Site",
        "<h1>Search</h1><p>Results would appear here.</p>",
        description="A search results page reached with a query string, for URL handling.",
    ),
    "/deep/1": _page("Deep 1", "<h1>Deep 1</h1><a href='/deep/2'>Next</a>"),
    "/deep/2": _page("Deep 2", "<h1>Deep 2</h1><a href='/deep/3'>Next</a>"),
    "/deep/3": _page("Deep 3", "<h1>Deep 3</h1><p>End of the chain.</p>"),
    "/private/secret": _page("Secret", "<h1>Secret</h1><p>Blocked by robots.txt.</p>"),
    "/hreflang": _page(
        "Hreflang Page",
        "<h1>International</h1><p>Alternates declared.</p>",
        description="A page declaring hreflang alternates so they can be collected.",
        extra_head='<link rel="alternate" hreflang="fr" href="/fr/">'
                   '<link rel="alternate" hreflang="de" href="/de/">',
    ),
    # Redirect targets.
    "/new-page": _page(
        "New Page",
        "<h1>New page</h1><p>The destination of a redirect.</p>",
        description="The final destination of a redirect chain used in the crawler tests.",
    ),
}

ROBOTS = """User-agent: *
Disallow: /private/
Sitemap: {base}/sitemap.xml
"""

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{base}/</loc></url>
  <url><loc>{base}/about</loc></url>
  <url><loc>{base}/services</loc></url>
  <url><loc>{base}/sitemap-only</loc></url>
  <url><loc>{base}/gone</loc></url>
</urlset>"""

# Redirects: source -> (status, target)
REDIRECTS: Dict[str, Tuple[int, str]] = {
    "/old-page": (301, "/new-page"),
    "/chain-a": (301, "/chain-b"),
    "/chain-b": (301, "/chain-c"),
    "/chain-c": (302, "/new-page"),
    "/loop-a": (301, "/loop-b"),
    "/loop-b": (301, "/loop-a"),
}


class _Handler(BaseHTTPRequestHandler):
    base_url = ""
    slow_seconds = 2.0
    hits: Dict[str, int] = {}

    def log_message(self, *args):  # noqa: A002 - silence the default per-request logging
        return

    def _send(self, body: str, status: int = 200, content_type: str = "text/html") -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET(body=False)

    def do_GET(self, body: bool = True) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        type(self).hits[path] = type(self).hits.get(path, 0) + 1

        if path == "/robots.txt":
            self._send(ROBOTS.format(base=self.base_url), content_type="text/plain")
            return

        if path == "/sitemap.xml":
            self._send(SITEMAP.format(base=self.base_url), content_type="application/xml")
            return

        if path in REDIRECTS:
            status, target = REDIRECTS[path]
            self.send_response(status)
            self.send_header("Location", target)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if path == "/boom":
            self._send("<h1>Server error</h1>", status=500)
            return

        if path == "/slow":
            time.sleep(self.slow_seconds)
            self._send(_page("Slow", "<h1>Eventually</h1>"))
            return

        if path == "/x-robots":
            payload = _page("Header noindex", "<h1>Blocked by header</h1>").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("X-Robots-Tag", "noindex")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/report.pdf":
            self._send("%PDF-1.4 fake", content_type="application/pdf")
            return

        if path in ("/logo.png", "/a.png", "/b.png", "/c.png"):
            self._send("not really a png", content_type="image/png")
            return

        if path in PAGES:
            self._send(PAGES[path])
            return

        self._send(_page("Not Found", "<h1>404</h1><p>No such page.</p>"), status=404)


def serve(slow_seconds: float = 2.0) -> Tuple[str, Callable[[], None], Dict[str, int]]:
    """Start the fixture site on a free loopback port.

    Returns ``(base_url, shutdown, hits)``. ``hits`` counts requests per path, which is how
    the tests prove a URL was fetched exactly once despite many spellings linking to it.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"

    _Handler.base_url = base
    _Handler.slow_seconds = slow_seconds
    _Handler.hits = {}

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def shutdown() -> None:
        server.shutdown()
        server.server_close()

    return base, shutdown, _Handler.hits
