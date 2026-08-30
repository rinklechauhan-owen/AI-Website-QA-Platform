"""The crawl routes, driven over real HTTP against a real fixture site."""

import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from audit import server
from audit.crawl.manager import CrawlManager
from tests.fixture_site import serve


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def http_get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), resp.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), exc.headers


def http_post(base, path, data):
    """POSTs without following the redirect, so the Location header can be inspected."""
    request = urllib.request.Request(
        base + path, data=urllib.parse.urlencode(data).encode(), method="POST"
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=60) as resp:
            return resp.status, resp.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Location", "")


def start_crawl(base, site, **extra):
    options = {"url": site, "max_urls": "40", "concurrency": "4", "respect_robots": "1",
               "follow_redirects": "1", "discover_sitemaps": "1"}
    options.update(extra)
    status, location = http_post(base, "/crawl", options)
    assert status == 303, f"expected a redirect, got {status}"
    return location.rstrip("/").rsplit("/", 1)[-1]


def wait_for_finish(crawl_id, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        crawler = server.CRAWLS.get(int(crawl_id))
        if crawler is not None and crawler.state.is_finished:
            return crawler
        time.sleep(0.2)
    raise AssertionError("crawl did not finish in time")


class CrawlRouteTestCase(unittest.TestCase):
    """A QA server and a site for it to crawl, plus one completed crawl to inspect."""

    @classmethod
    def setUpClass(cls):
        cls.site, cls.site_shutdown, _ = serve()

        # Isolate the manager so these tests never see crawls from another test module.
        cls._saved_manager = server.CRAWLS
        server.CRAWLS = CrawlManager()

        cls.port = server.find_port(start=9100)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", cls.port), server._Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.port}"

        cls.crawl_id = start_crawl(cls.base, cls.site)
        wait_for_finish(cls.crawl_id)

    @classmethod
    def tearDownClass(cls):
        server.CRAWLS.stop_all()
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.site_shutdown()
        server.CRAWLS = cls._saved_manager

    def _get(self, path):
        return http_get(self.base, path)

    def _post(self, path, data=None):
        return http_post(self.base, path, data or {"_": "1"})


class TestCrawlEntry(CrawlRouteTestCase):
    def test_crawl_form_served(self):
        status, body, _ = self._get("/crawl")
        self.assertEqual(status, 200)
        self.assertIn('name="max_urls"', body)
        self.assertIn("Respect robots.txt", body)

    def test_home_page_offers_both_modes(self):
        status, body, _ = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("Single Page Audit", body)
        self.assertIn("Full Website Crawl", body)

    def test_starting_a_crawl_redirects_rather_than_re_posting(self):
        status, location = self._post("/crawl", {"url": self.site, "max_urls": "5"})
        self.assertEqual(status, 303)
        self.assertTrue(location.startswith("/crawl/"))
        server.CRAWLS.get(int(location.rsplit("/", 1)[-1])).stop()

    def test_invalid_url_returns_the_form_with_an_error(self):
        request = urllib.request.Request(
            self.base + "/crawl",
            data=urllib.parse.urlencode({"url": "file:///etc/passwd"}).encode(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                status, body = resp.status, resp.read().decode()
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read().decode()
        self.assertEqual(status, 400)
        self.assertIn("Only http and https", body)

    def test_unknown_crawl_id_is_handled(self):
        status, body, _ = self._get("/crawl/9999")
        self.assertEqual(status, 404)
        self.assertIn("no longer available", body)


class TestCrawlResults(CrawlRouteTestCase):
    def test_dashboard(self):
        status, body, _ = self._get(f"/crawl/{self.crawl_id}")
        self.assertEqual(status, 200)
        self.assertIn("Website SEO Audit", body)
        self.assertIn("Pages crawled", body)

    def test_url_table(self):
        status, body, _ = self._get(f"/crawl/{self.crawl_id}/urls")
        self.assertEqual(status, 200)
        self.assertIn("<table", body)

    def test_url_table_filter(self):
        _, body, _ = self._get(f"/crawl/{self.crawl_id}/urls?filter=4xx")
        self.assertIn("4xx Errors", body)

    def test_url_table_search(self):
        _, body, _ = self._get(f"/crawl/{self.crawl_id}/urls?q=blog")
        self.assertIn("blog", body)

    def test_url_table_sort(self):
        status, _, _ = self._get(f"/crawl/{self.crawl_id}/urls?sort=word_count&desc=1")
        self.assertEqual(status, 200)

    def test_issue_list(self):
        _, body, _ = self._get(f"/crawl/{self.crawl_id}/issues")
        self.assertIn("Duplicate title", body)

    def test_issue_detail(self):
        _, body, _ = self._get(f"/crawl/{self.crawl_id}/issues/site.duplicate-title")
        self.assertIn("duplicate-a", body)

    def test_url_detail(self):
        _, body, _ = self._get(f"/crawl/{self.crawl_id}/url/1")
        self.assertIn("Basic information", body)

    def test_links_page(self):
        _, body, _ = self._get(f"/crawl/{self.crawl_id}/links")
        self.assertIn("Source page", body)

    def test_technical_page(self):
        _, body, _ = self._get(f"/crawl/{self.crawl_id}/technical")
        self.assertIn("robots.txt", body)

    def test_no_crawl_screen_contains_script(self):
        for path in ("", "/urls", "/issues", "/links", "/technical"):
            with self.subTest(path=path):
                _, body, _ = self._get(f"/crawl/{self.crawl_id}{path}")
                self.assertNotIn("<script", body.lower())

    def test_csp_still_blocks_scripts(self):
        _, _, headers = self._get(f"/crawl/{self.crawl_id}")
        self.assertIn("default-src 'none'", headers.get("Content-Security-Policy", ""))


class TestExportRoutes(CrawlRouteTestCase):
    def test_urls_csv(self):
        status, body, headers = self._get(f"/crawl/{self.crawl_id}/export/urls")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers.get("Content-Type", ""))
        self.assertIn("crawl-urls.csv", headers.get("Content-Disposition", ""))
        self.assertIn("URL,Status Code", body)

    def test_issues_csv(self):
        _, body, headers = self._get(f"/crawl/{self.crawl_id}/export/issues")
        self.assertIn("crawl-issues.csv", headers.get("Content-Disposition", ""))
        self.assertIn("Rule", body)

    def test_broken_links_csv(self):
        _, body, _ = self._get(f"/crawl/{self.crawl_id}/export/broken-links")
        self.assertIn("Source,Target", body)

    def test_issue_specific_csv(self):
        _, body, headers = self._get(
            f"/crawl/{self.crawl_id}/export/issue?rule=site.duplicate-title"
        )
        self.assertIn("site-duplicate-title.csv", headers.get("Content-Disposition", ""))
        self.assertEqual(len([l for l in body.splitlines() if l.strip()]) - 1, 2)

    def test_unknown_export_does_not_crash(self):
        status, _, _ = self._get(f"/crawl/{self.crawl_id}/export/nonsense")
        self.assertEqual(status, 404)


class TestCrawlControls(unittest.TestCase):
    """Pause, resume and stop, exercised against a crawl that is still running."""

    @classmethod
    def setUpClass(cls):
        cls.site, cls.site_shutdown, _ = serve()
        cls._saved = server.CRAWLS
        server.CRAWLS = CrawlManager()
        cls.port = server.find_port(start=9200)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", cls.port), server._Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        server.CRAWLS.stop_all()
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.site_shutdown()
        server.CRAWLS = cls._saved

    def _post(self, path, data=None):
        return http_post(self.base, path, data or {"_": "1"})

    def test_stop_ends_a_running_crawl(self):
        status, location = self._post(
            "/crawl", {"url": self.site, "max_urls": "500", "concurrency": "2"}
        )
        self.assertEqual(status, 303)
        crawl_id = location.rsplit("/", 1)[-1]

        status, _ = self._post(f"/crawl/{crawl_id}/stop")
        self.assertEqual(status, 303)

        crawler = server.CRAWLS.get(int(crawl_id))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not crawler.state.is_finished:
            time.sleep(0.1)
        self.assertTrue(crawler.state.is_finished)

    def test_pause_then_resume(self):
        _, location = self._post(
            "/crawl", {"url": self.site, "max_urls": "500", "concurrency": "2"}
        )
        crawl_id = location.rsplit("/", 1)[-1]
        crawler = server.CRAWLS.get(int(crawl_id))

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and crawler.progress.crawled < 1:
            time.sleep(0.05)

        self._post(f"/crawl/{crawl_id}/pause")
        self.assertIn(crawler.state.value, ("paused", "completed", "stopped"))

        self._post(f"/crawl/{crawl_id}/resume")
        crawler.stop()

    def test_progress_page_refreshes_itself_without_script(self):
        _, location = self._post(
            "/crawl", {"url": self.site, "max_urls": "500", "concurrency": "1", "delay_ms": "200"}
        )
        crawl_id = location.rsplit("/", 1)[-1]

        with urllib.request.urlopen(self.base + f"/crawl/{crawl_id}", timeout=20) as resp:
            body = resp.read().decode()

        self.assertIn('http-equiv="refresh"', body)
        self.assertNotIn("<script", body.lower())
        self.assertIn("URLs crawled", body)
        server.CRAWLS.get(int(crawl_id)).stop()


class TestManagerEviction(unittest.TestCase):
    def test_finished_crawls_are_evicted_once_the_cap_is_reached(self):
        """Crawls live in memory, so an unbounded manager would leak until restart."""
        manager = CrawlManager(max_retained=2)

        class Fake:
            def __init__(self, finished=True):
                self.closed = False
                self._finished = finished
                self.store = self

            @property
            def state(self):
                class S:
                    is_finished = self._finished
                return S()

            def close(self):
                self.closed = True

        for index in range(4):
            manager._crawls[index] = Fake()
            manager._order.append(index)
            manager._evict_locked()

        self.assertLessEqual(len(manager._crawls), 2)

    def test_running_crawls_are_never_evicted(self):
        manager = CrawlManager(max_retained=1)

        class Running:
            store = None

            @property
            def state(self):
                class S:
                    is_finished = False
                return S()

        for index in range(3):
            manager._crawls[index] = Running()
            manager._order.append(index)
            manager._evict_locked()

        self.assertEqual(len(manager._crawls), 3)


if __name__ == "__main__":
    unittest.main()
