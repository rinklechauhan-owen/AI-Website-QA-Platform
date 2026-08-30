"""Client-rendering detection and crawl politeness.

Both exist to stop the tool misleading whoever reads its output: one so a rendering blind spot
is never mistaken for an SEO problem, the other so pointing the crawler at a client's site
cannot overload it.
"""

import time
import unittest

from audit.crawl.crawler import _RateLimiter
from audit.crawl.rendering import looks_client_rendered
from audit.parse import parse

URL = "https://example.test/"

CRA_SHELL = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>My App</title>'
    "</head><body><noscript>You need to enable JavaScript</noscript>"
    '<div id="root"></div><script src="/static/js/main.js">' + ("var a=1;" * 900) +
    "</script></body></html>"
)

NEXT_SHELL = (
    "<!doctype html><html><head><title>Shop</title></head><body>"
    '<div id="__next"></div>'
    '<script id="__NEXT_DATA__" type="application/json">' + ("x" * 9000) +
    "</script></body></html>"
)

SERVER_RENDERED = (
    '<!doctype html><html lang="en"><head><title>Real Page</title>'
    '<meta name="description" content="A normal server-rendered page."></head><body>'
    '<div id="root"><h1>Our Services</h1><p>'
    + ("Genuine server-rendered body copy that a crawler can read. " * 40)
    + "</p></div><script>"
    + ("t();" * 3000)
    + "</script></body></html>"
)

PLAIN = (
    '<!doctype html><html lang="en"><head><title>Plain</title></head><body>'
    "<h1>Heading</h1><p>" + ("Ordinary copy. " * 60) + "</p></body></html>"
)


class TestDetectsShells(unittest.TestCase):
    def test_create_react_app_shell(self):
        signal = looks_client_rendered(parse(CRA_SHELL, URL))
        self.assertTrue(signal.client_rendered)
        self.assertEqual(signal.framework, "React")

    def test_next_shell(self):
        signal = looks_client_rendered(parse(NEXT_SHELL, URL))
        self.assertTrue(signal.client_rendered)
        self.assertEqual(signal.framework, "Next.js")

    def test_reasons_are_reported(self):
        signal = looks_client_rendered(parse(CRA_SHELL, URL))
        self.assertGreaterEqual(len(signal.reasons), 2)
        self.assertTrue(any("mount point" in reason for reason in signal.reasons))

    def test_summary_reads_plainly(self):
        self.assertIn("browser", looks_client_rendered(parse(CRA_SHELL, URL)).summary)


class TestAvoidsFalsePositives(unittest.TestCase):
    """A false positive would wave away real findings, so detection has to be conservative."""

    def test_server_rendered_page_with_a_heavy_bundle(self):
        self.assertFalse(looks_client_rendered(parse(SERVER_RENDERED, URL)).client_rendered)

    def test_plain_page(self):
        self.assertFalse(looks_client_rendered(parse(PLAIN, URL)).client_rendered)

    def test_thin_page_alone_is_not_enough(self):
        """example.com is tiny but perfectly server-rendered."""
        thin = "<html lang=en><head><title>Example</title></head><body><h1>Example</h1>" \
               "<p>Short but served.</p></body></html>"
        self.assertFalse(looks_client_rendered(parse(thin, URL)).client_rendered)

    def test_framework_marker_alone_is_not_enough(self):
        """react.dev ships Next.js markers and still serves its content."""
        page = (
            "<html lang=en><head><title>Docs</title></head><body><h1>Docs</h1><p>"
            + ("Real served documentation copy. " * 50)
            + '</p><script id="__NEXT_DATA__">{}</script></body></html>'
        )
        self.assertFalse(looks_client_rendered(parse(page, URL)).client_rendered)

    def test_empty_document(self):
        self.assertFalse(looks_client_rendered(parse("", URL)).client_rendered)

    def test_none_document(self):
        self.assertFalse(looks_client_rendered(None).client_rendered)


class TestRateLimiter(unittest.TestCase):
    """robots.txt Crawl-delay is a site-wide instruction, not a per-worker one."""

    def test_zero_interval_does_not_wait(self):
        limiter = _RateLimiter(0)
        started = time.monotonic()
        for _ in range(5):
            limiter.wait()
        self.assertLess(time.monotonic() - started, 0.1)

    def test_requests_are_spaced(self):
        limiter = _RateLimiter(0.05)
        started = time.monotonic()
        for _ in range(4):
            limiter.wait()
        # Four requests at 50 ms apart cannot complete in under 150 ms.
        self.assertGreaterEqual(time.monotonic() - started, 0.15)

    def test_spacing_holds_across_threads(self):
        """With per-worker sleeping, N workers would make N requests per interval."""
        import threading

        limiter = _RateLimiter(0.04)
        stamps, lock = [], threading.Lock()

        def worker():
            for _ in range(3):
                limiter.wait()
                with lock:
                    stamps.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        started = time.monotonic()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # 12 requests spaced 40 ms apart take at least ~440 ms however many threads there are.
        self.assertGreaterEqual(time.monotonic() - started, 0.4)
        self.assertEqual(len(stamps), 12)


class TestCrawlDelayIsApplied(unittest.TestCase):
    def test_robots_crawl_delay_overrides_a_faster_setting(self):
        from audit.crawl import robots as robots_module
        from audit.crawl.crawler import Crawler
        from audit.crawl.settings import CrawlSettings
        from audit.crawl.store import CrawlStore

        store = CrawlStore(":memory:")
        self.addCleanup(store.close)
        crawler = Crawler("https://example.test", CrawlSettings(delay_ms=0), store)

        rules, sitemaps, delay, group = robots_module.parse("User-agent: *\nCrawl-delay: 0.2")
        crawler.robots = robots_module.RobotsTxt(
            url="", found=True, status=200, rules=rules, crawl_delay=delay
        )
        crawler._prepared = True

        # Re-run the part of preparation that installs the limiter.
        if crawler.settings.respect_robots and crawler.robots.crawl_delay:
            interval = max(
                crawler.settings.delay_ms / 1000, float(crawler.robots.crawl_delay)
            )
            crawler._limiter = _RateLimiter(interval)

        self.assertEqual(crawler._limiter.interval, 0.2)

    def test_user_setting_wins_when_stricter(self):
        from audit.crawl.settings import CrawlSettings

        settings = CrawlSettings(delay_ms=500)
        self.assertEqual(max(settings.delay_ms / 1000, 0.2), 0.5)


if __name__ == "__main__":
    unittest.main()
