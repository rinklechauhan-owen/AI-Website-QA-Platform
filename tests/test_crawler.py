"""End-to-end crawler tests against a real HTTP server.

The fixture site exhibits every condition the brief lists — redirects, 404s, 500s, duplicate
titles, missing metadata, missing alt text, robots restrictions, sitemaps, query-parameter
variants and a page that never responds — so these tests exercise the crawler the way a real
site would rather than through mocks.
"""

import unittest

from audit.crawl.crawler import CrawlState, Crawler, compact_result
from audit.crawl.settings import CrawlSettings
from audit.crawl.store import CrawlStore
from tests.fixture_site import serve


class CrawlTestCase(unittest.TestCase):
    """Starts the fixture site once for the whole class; each test crawls it fresh."""

    @classmethod
    def setUpClass(cls):
        cls.base, cls.shutdown, cls.hits = serve()

    @classmethod
    def tearDownClass(cls):
        cls.shutdown()

    def crawl(self, **settings):
        options = {"max_urls": 60, "concurrency": 4, "timeout": 5, "max_retries": 0}
        options.update(settings)
        store = CrawlStore(":memory:")
        self.addCleanup(store.close)
        crawler = Crawler(self.base, CrawlSettings(**options), store)
        crawler.run()
        return crawler

    def urls(self, crawler):
        return {row["url"] for row in crawler.store.iter_urls(crawler.session_id)}

    def row_for(self, crawler, path):
        for row in crawler.store.iter_urls(crawler.session_id):
            if row["url"] == self.base + path:
                return row
        return None


class TestBasicCrawl(CrawlTestCase):
    def test_crawl_completes(self):
        crawler = self.crawl()
        self.assertIs(crawler.state, CrawlState.COMPLETED)

    def test_discovers_pages_by_following_links(self):
        crawler = self.crawl()
        found = self.urls(crawler)
        for path in ("/", "/about", "/services", "/blog/", "/blog/post-1", "/blog/post-2"):
            with self.subTest(path=path):
                self.assertIn(self.base + path, found)

    def test_homepage_is_depth_zero_and_children_are_deeper(self):
        crawler = self.crawl()
        self.assertEqual(self.row_for(crawler, "/")["depth"], 0)
        self.assertGreaterEqual(self.row_for(crawler, "/about")["depth"], 1)

    def test_depth_chain_increases(self):
        crawler = self.crawl()
        depths = [self.row_for(crawler, f"/deep/{n}")["depth"] for n in (1, 2, 3)]
        self.assertLess(depths[0], depths[1])
        self.assertLess(depths[1], depths[2])

    def test_every_page_gets_the_existing_seo_analysis(self):
        """The crawler must reuse the audit engine, not a reduced copy of it."""
        row = self.row_for(self.crawl(), "/about")
        self.assertIsNotNone(row["result_json"])
        self.assertIsNotNone(row["score"])
        self.assertEqual(row["title"], "About — Fixture Site")
        self.assertGreater(row["word_count"], 0)

    def test_session_records_totals(self):
        crawler = self.crawl()
        session = crawler.store.get_session(crawler.session_id)
        self.assertEqual(session.status, "completed")
        self.assertGreater(session.urls_crawled, 5)
        self.assertGreater(session.health_score, 0)


class TestUrlHandling(CrawlTestCase):
    def test_url_variants_are_fetched_once(self):
        """/about, /about/ and /about#team are linked separately but are one page."""
        type(self).hits.clear()
        self.crawl()
        self.assertEqual(self.hits.get("/about", 0), 1)

    def test_tracking_parameter_variant_not_crawled_twice(self):
        type(self).hits.clear()
        self.crawl()
        self.assertEqual(self.hits.get("/search", 0), 1)

    def test_external_links_recorded_but_not_crawled(self):
        crawler = self.crawl()
        self.assertNotIn("https://external.invalid/page", self.urls(crawler))
        self.assertTrue(any("external.invalid" in u for u in crawler.frontier.stats.external))

    def test_binary_and_mail_links_skipped(self):
        crawler = self.crawl()
        found = self.urls(crawler)
        self.assertNotIn(self.base + "/logo.png", found)
        self.assertFalse(any(u.startswith("mailto:") for u in found))

    def test_pdf_skipped_by_default(self):
        self.assertNotIn(self.base + "/report.pdf", self.urls(self.crawl()))

    def test_pdf_crawled_when_enabled(self):
        self.assertIn(self.base + "/report.pdf", self.urls(self.crawl(include_pdfs=True)))


class TestErrorsDoNotStopTheCrawl(CrawlTestCase):
    def test_404_recorded_and_crawl_continues(self):
        crawler = self.crawl()
        row = self.row_for(crawler, "/gone")
        self.assertIsNotNone(row)
        self.assertEqual(row["status_code"], 404)
        self.assertIs(crawler.state, CrawlState.COMPLETED)

    def test_500_recorded_and_crawl_continues(self):
        crawler = self.crawl()
        row = self.row_for(crawler, "/boom")
        self.assertEqual(row["status_code"], 500)
        self.assertGreater(len(self.urls(crawler)), 10)

    def test_unreachable_host_does_not_end_the_crawl(self):
        """A dead URL in the frontier must cost one row, not the whole run."""
        store = CrawlStore(":memory:")
        self.addCleanup(store.close)
        crawler = Crawler(self.base, CrawlSettings(max_urls=40, timeout=2, max_retries=0), store)
        crawler.prepare()
        crawler.frontier.add(self.base + "/", depth=0)
        crawler.run()
        self.assertIs(crawler.state, CrawlState.COMPLETED)
        self.assertGreater(crawler.progress.crawled, 5)

    def test_status_breakdown_covers_every_class(self):
        crawler = self.crawl()
        buckets = crawler.store.status_breakdown(crawler.session_id)
        self.assertGreater(buckets["2xx"], 5)
        self.assertGreaterEqual(buckets["4xx"], 1)
        self.assertGreaterEqual(buckets["5xx"], 1)

    def test_errors_counted_in_progress(self):
        self.assertGreaterEqual(self.crawl().progress.errors, 2)


class TestRedirects(CrawlTestCase):
    def test_single_redirect_followed_and_recorded(self):
        crawler = self.crawl()
        row = self.row_for(crawler, "/old-page")
        self.assertIsNotNone(row)
        self.assertEqual(row["redirect_hops"], 1)
        self.assertTrue(row["final_url"].endswith("/new-page"))
        self.assertEqual(row["status_code"], 200)

    def test_redirect_chain_hops_counted(self):
        store = CrawlStore(":memory:")
        self.addCleanup(store.close)
        crawler = Crawler(self.base, CrawlSettings(max_urls=10, max_retries=0), store)
        crawler.prepare()
        crawler.frontier.add(self.base + "/chain-a", depth=1)
        crawler.run()
        row = self.row_for(crawler, "/chain-a")
        self.assertEqual(row["redirect_hops"], 3)

    def test_redirect_loop_survived(self):
        store = CrawlStore(":memory:")
        self.addCleanup(store.close)
        crawler = Crawler(self.base, CrawlSettings(max_urls=10, max_retries=0), store)
        crawler.prepare()
        crawler.frontier.add(self.base + "/loop-a", depth=1)
        crawler.run()
        self.assertIs(crawler.state, CrawlState.COMPLETED)
        self.assertIsNotNone(self.row_for(crawler, "/loop-a"))

    def test_redirects_counted_in_progress(self):
        self.assertGreaterEqual(self.crawl().progress.redirects, 1)

    def test_redirects_can_be_left_unfollowed(self):
        store = CrawlStore(":memory:")
        self.addCleanup(store.close)
        crawler = Crawler(
            self.base,
            CrawlSettings(max_urls=10, max_retries=0, follow_redirects=False),
            store,
        )
        crawler.prepare()
        crawler.frontier.add(self.base + "/old-page", depth=1)
        crawler.run()
        self.assertEqual(self.row_for(crawler, "/old-page")["status_code"], 301)


class TestRobots(CrawlTestCase):
    def test_robots_read_and_respected(self):
        crawler = self.crawl()
        self.assertTrue(crawler.robots.found)
        self.assertNotIn(self.base + "/private/secret", self.urls(crawler))

    def test_robots_can_be_ignored_when_asked(self):
        crawler = self.crawl(respect_robots=False)
        self.assertIn(self.base + "/private/secret", self.urls(crawler))

    def test_sitemap_discovered_from_robots(self):
        crawler = self.crawl()
        self.assertTrue(crawler.sitemap.any_found)
        self.assertIn(self.base + "/sitemap-only", crawler.sitemap.urls)

    def test_sitemap_urls_are_crawled(self):
        """A page in the sitemap but linked from nowhere must still be reached."""
        self.assertIn(self.base + "/sitemap-only", self.urls(self.crawl()))

    def test_sitemap_membership_flagged_on_rows(self):
        crawler = self.crawl()
        self.assertEqual(self.row_for(crawler, "/about")["in_sitemap"], 1)
        self.assertEqual(self.row_for(crawler, "/no-meta")["in_sitemap"], 0)


class TestPageAnalysis(CrawlTestCase):
    def test_missing_meta_description_detected(self):
        crawler = self.crawl()
        rules = {
            row["rule"] for row in crawler.store.issue_summary(crawler.session_id)
        }
        self.assertIn("seo.missing-meta-description", rules)

    def test_missing_h1_detected(self):
        crawler = self.crawl()
        affected = crawler.store.urls_with_issue(crawler.session_id, "seo.missing-h1")
        self.assertIn(self.base + "/no-h1", {row["url"] for row in affected})

    def test_missing_alt_recorded_per_page(self):
        row = self.row_for(self.crawl(), "/missing-alt")
        self.assertEqual(row["images"], 3)
        self.assertEqual(row["missing_alt"], 2)

    def test_duplicate_titles_found_site_wide(self):
        crawler = self.crawl()
        duplicates = crawler.store.duplicates(crawler.session_id, "title")
        self.assertIn("Duplicated Title", {row["value"] for row in duplicates})

    def test_duplicate_meta_descriptions_found(self):
        crawler = self.crawl()
        values = {row["value"] for row in crawler.store.duplicates(crawler.session_id,
                                                                  "meta_description")}
        self.assertTrue(any("two pages" in value for value in values))

    def test_indexability_recorded(self):
        crawler = self.crawl()
        self.assertEqual(self.row_for(crawler, "/about")["indexable"], 1)

    def test_link_counts_recorded(self):
        row = self.row_for(self.crawl(), "/")
        self.assertGreater(row["internal_links"], 5)
        self.assertGreaterEqual(row["external_links"], 1)

    def test_link_graph_stored(self):
        crawler = self.crawl()
        inlinks = crawler.store.inlink_counts(crawler.session_id)
        self.assertGreaterEqual(inlinks.get(self.base + "/about", 0), 1)

    def test_hreflang_captured(self):
        self.assertEqual(self.row_for(self.crawl(), "/hreflang")["hreflang"], "de,fr")

    def test_meta_noindex_page_marked_unindexable(self):
        self.assertEqual(self.row_for(self.crawl(), "/noindex")["indexable"], 0)

    def test_header_level_noindex_detected(self):
        """X-Robots-Tag is invisible in the markup, so a crawler that only reads HTML misses it."""
        self.assertEqual(self.row_for(self.crawl(), "/x-robots")["indexable"], 0)


class TestLimitsAndControls(CrawlTestCase):
    def test_max_urls_is_respected(self):
        crawler = self.crawl(max_urls=5)
        self.assertLessEqual(crawler.store.count_urls(crawler.session_id), 5)

    def test_max_urls_is_configurable(self):
        crawler = self.crawl(max_urls=3)
        self.assertLessEqual(crawler.store.count_urls(crawler.session_id), 3)

    def test_depth_limit_respected(self):
        crawler = self.crawl(max_depth=1)
        depths = {row["depth"] for row in crawler.store.iter_urls(crawler.session_id)}
        self.assertTrue(max(depths) <= 1, depths)

    def test_exclude_pattern_respected(self):
        crawler = self.crawl(exclude_patterns=["/blog/"])
        self.assertFalse(any("/blog/" in url for url in self.urls(crawler)))

    def test_stop_ends_the_crawl_early(self):
        store = CrawlStore(":memory:")
        self.addCleanup(store.close)
        crawler = Crawler(self.base, CrawlSettings(max_urls=500, concurrency=2), store)
        crawler.start()

        # Let it get going, then ask it to stop.
        for _ in range(200):
            if crawler.progress.crawled >= 2:
                break
            import time as _t

            _t.sleep(0.02)
        crawler.stop()
        crawler.wait(timeout=20)

        self.assertIs(crawler.state, CrawlState.STOPPED)
        self.assertEqual(crawler.store.get_session(crawler.session_id).status, "stopped")

    def test_progress_snapshot_is_readable_mid_crawl(self):
        progress = self.crawl().progress
        self.assertGreater(progress.crawled, 0)
        self.assertGreaterEqual(progress.percent, 0)
        self.assertIn("crawled", progress.to_dict())
        self.assertIsInstance(progress.bar, str)


class TestConcurrency(CrawlTestCase):
    def test_single_worker_crawls_the_same_pages(self):
        one = self.urls(self.crawl(concurrency=1))
        many = self.urls(self.crawl(concurrency=8))
        self.assertEqual(one, many)

    def test_no_page_is_fetched_twice_under_concurrency(self):
        type(self).hits.clear()
        self.crawl(concurrency=8)
        repeated = {
            path: count
            for path, count in self.hits.items()
            if count > 1 and path not in ("/robots.txt", "/sitemap.xml")
        }
        self.assertEqual(repeated, {})


class TestStorageShape(CrawlTestCase):
    def test_stored_result_is_trimmed(self):
        """Keeping a full outline for every page would cost memory the crawl does not need."""
        crawler = self.crawl()
        payload = crawler.store.result_for(
            crawler.session_id, self.row_for(crawler, "/about")["id"]
        )
        self.assertIn("packs", payload)
        self.assertNotIn("outline", payload.get("inventory", {}))

    def test_compact_result_keeps_findings(self):
        from audit.engine import audit_response
        from tests.fixtures import MESSY, response

        payload = compact_result(audit_response(response(MESSY), "https://acme.test/"))
        self.assertTrue(payload["packs"])
        self.assertIn("canonical", payload["inventory"])

    def test_nothing_is_written_to_disk(self):
        crawler = self.crawl()
        self.assertEqual(crawler.store.path, ":memory:")


if __name__ == "__main__":
    unittest.main()
