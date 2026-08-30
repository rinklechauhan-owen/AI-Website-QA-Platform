"""The crawl frontier: deduplication, scope rules, depth, and limits."""

import threading
import unittest

from audit.crawl import robots
from audit.crawl.frontier import Frontier, SkipReason
from audit.crawl.settings import CrawlSettings

ROOT = "https://example.com"


def frontier(**settings) -> Frontier:
    return Frontier(ROOT, CrawlSettings(**settings))


class TestSeeding(unittest.TestCase):
    def test_seed_queues_the_root(self):
        f = frontier()
        self.assertTrue(f.seed())
        self.assertEqual(len(f), 1)
        self.assertEqual(f.take().depth, 0)

    def test_seed_is_idempotent(self):
        f = frontier()
        f.seed()
        self.assertFalse(f.seed())
        self.assertEqual(len(f), 1)

    def test_seed_ignores_include_patterns(self):
        """A root outside the include patterns would otherwise leave nothing to crawl."""
        f = frontier(include_patterns=["/blog/"])
        self.assertTrue(f.seed())

    def test_invalid_root_rejected(self):
        with self.assertRaises(ValueError):
            Frontier("mailto:a@b.com")


class TestDeduplication(unittest.TestCase):
    def test_same_url_queued_once(self):
        f = frontier()
        self.assertTrue(f.add(f"{ROOT}/a")[0])
        queued, reason = f.add(f"{ROOT}/a")
        self.assertFalse(queued)
        self.assertIs(reason, SkipReason.DUPLICATE)

    def test_trailing_slash_variants_collapse(self):
        f = frontier()
        f.add(f"{ROOT}/about")
        self.assertFalse(f.add(f"{ROOT}/about/")[0])
        self.assertEqual(len(f), 1)

    def test_fragment_variants_collapse(self):
        f = frontier()
        f.add(f"{ROOT}/about")
        self.assertFalse(f.add(f"{ROOT}/about#team")[0])

    def test_tracking_parameter_variants_collapse(self):
        f = frontier()
        f.add(f"{ROOT}/about")
        self.assertFalse(f.add(f"{ROOT}/about?utm_source=news")[0])

    def test_meaningful_query_is_a_separate_page(self):
        f = frontier()
        f.add(f"{ROOT}/search?q=a")
        self.assertTrue(f.add(f"{ROOT}/search?q=b")[0])

    def test_relative_and_absolute_forms_collapse(self):
        f = frontier()
        f.add(f"{ROOT}/about")
        self.assertFalse(f.add("/about", base=f"{ROOT}/team")[0])


class TestScope(unittest.TestCase):
    def test_external_link_refused(self):
        f = frontier()
        queued, reason = f.add("https://other.test/a")
        self.assertFalse(queued)
        self.assertIs(reason, SkipReason.EXTERNAL)

    def test_external_links_are_recorded(self):
        f = frontier()
        f.add("https://other.test/a")
        self.assertIn("https://other.test/a", f.stats.external)

    def test_subdomain_refused_by_default(self):
        self.assertIs(frontier().add("https://blog.example.com/a")[1], SkipReason.EXTERNAL)

    def test_subdomain_allowed_when_enabled(self):
        self.assertTrue(frontier(crawl_subdomains=True).add("https://blog.example.com/a")[0])

    def test_www_variant_is_internal(self):
        self.assertTrue(frontier().add("https://www.example.com/a")[0])

    def test_binary_refused(self):
        self.assertIs(frontier().add(f"{ROOT}/logo.png")[1], SkipReason.BINARY)

    def test_pdf_refused_by_default(self):
        self.assertIs(frontier().add(f"{ROOT}/report.pdf")[1], SkipReason.DOCUMENT)

    def test_pdf_allowed_when_enabled(self):
        self.assertTrue(frontier(include_pdfs=True).add(f"{ROOT}/report.pdf")[0])

    def test_non_http_scheme_refused(self):
        self.assertIs(frontier().add("mailto:a@b.com")[1], SkipReason.BAD_SCHEME)

    def test_crawler_trap_refused(self):
        self.assertIs(frontier().add(f"{ROOT}/a/b/a/b/a/b/a/b")[1], SkipReason.TRAP)


class TestDepth(unittest.TestCase):
    def test_depth_recorded(self):
        f = frontier()
        f.add(f"{ROOT}/a", depth=3)
        self.assertEqual(f.take().depth, 3)

    def test_depth_limit_enforced(self):
        f = frontier(max_depth=2)
        self.assertTrue(f.add(f"{ROOT}/a", depth=2)[0])
        self.assertIs(f.add(f"{ROOT}/b", depth=3)[1], SkipReason.TOO_DEEP)

    def test_unlimited_depth_by_default(self):
        self.assertTrue(frontier().add(f"{ROOT}/a", depth=99)[0])

    def test_depth_zero_limit_crawls_only_the_root(self):
        f = frontier(max_depth=0)
        f.seed()
        self.assertIs(f.add(f"{ROOT}/a", depth=1)[1], SkipReason.TOO_DEEP)


class TestPatterns(unittest.TestCase):
    def test_exclude_pattern(self):
        f = frontier(exclude_patterns=["/tag/"])
        self.assertIs(f.add(f"{ROOT}/tag/x")[1], SkipReason.EXCLUDED)
        self.assertTrue(f.add(f"{ROOT}/blog/x")[0])

    def test_include_pattern_restricts(self):
        f = frontier(include_patterns=["/blog/"])
        self.assertTrue(f.add(f"{ROOT}/blog/x")[0])
        self.assertIs(f.add(f"{ROOT}/about")[1], SkipReason.NOT_INCLUDED)

    def test_exclude_beats_include(self):
        f = frontier(include_patterns=["/blog/"], exclude_patterns=["/blog/draft"])
        self.assertIs(f.add(f"{ROOT}/blog/draft-1")[1], SkipReason.EXCLUDED)


class TestRobotsIntegration(unittest.TestCase):
    def _robots(self, text):
        rules, sitemaps, delay, group = robots.parse(text)
        return robots.RobotsTxt(url="", found=True, status=200, rules=rules, sitemaps=sitemaps)

    def test_blocked_url_refused(self):
        f = Frontier(ROOT, CrawlSettings(), self._robots("User-agent: *\nDisallow: /private/"))
        self.assertIs(f.add(f"{ROOT}/private/x")[1], SkipReason.ROBOTS)
        self.assertTrue(f.add(f"{ROOT}/public/x")[0])

    def test_robots_ignored_when_disabled(self):
        f = Frontier(
            ROOT,
            CrawlSettings(respect_robots=False),
            self._robots("User-agent: *\nDisallow: /"),
        )
        self.assertTrue(f.add(f"{ROOT}/private/x")[0])


class TestLimits(unittest.TestCase):
    def test_max_urls_enforced(self):
        f = frontier(max_urls=3)
        for i in range(10):
            f.add(f"{ROOT}/p{i}")
        self.assertEqual(f.seen_count, 3)
        self.assertEqual(f.stats.skipped.get("limit_reached"), 7)

    def test_limit_is_configurable_not_hardcoded(self):
        self.assertEqual(CrawlSettings().max_urls, 2000)
        self.assertEqual(CrawlSettings(max_urls=25).max_urls, 25)
        self.assertEqual(CrawlSettings(max_urls=999_999).max_urls, 50_000)


class TestLifecycle(unittest.TestCase):
    def test_take_marks_in_flight_and_done_clears_it(self):
        f = frontier()
        f.seed()
        item = f.take()
        self.assertEqual(f.in_flight, 1)
        self.assertFalse(f.is_exhausted())
        f.done(item)
        self.assertEqual(f.in_flight, 0)
        self.assertTrue(f.is_exhausted())

    def test_take_on_empty_queue_returns_none(self):
        self.assertIsNone(frontier().take())

    def test_requeue_puts_it_back(self):
        f = frontier()
        f.seed()
        item = f.take()
        f.requeue(item)
        self.assertEqual(len(f), 1)
        self.assertEqual(f.in_flight, 0)

    def test_exhausted_only_when_queue_and_flight_are_empty(self):
        f = frontier()
        self.assertTrue(f.is_exhausted())
        f.seed()
        self.assertFalse(f.is_exhausted())


class TestThreadSafety(unittest.TestCase):
    def test_concurrent_adds_never_duplicate(self):
        f = frontier(max_urls=5000)
        urls = [f"{ROOT}/p{i}" for i in range(200)]

        def worker():
            for url in urls:
                f.add(url)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(f.seen_count, 200)
        self.assertEqual(len(f), 200)

    def test_concurrent_takes_never_hand_out_the_same_url(self):
        f = frontier(max_urls=5000)
        for i in range(300):
            f.add(f"{ROOT}/p{i}")

        taken, lock = [], threading.Lock()

        def worker():
            while True:
                item = f.take()
                if item is None:
                    return
                with lock:
                    taken.append(item.key)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(taken), 300)
        self.assertEqual(len(set(taken)), 300)


class TestSnapshot(unittest.TestCase):
    def test_snapshot_and_restore_round_trip(self):
        f = frontier()
        f.seed()
        for i in range(5):
            f.add(f"{ROOT}/p{i}")
        snapshot = f.snapshot()

        resumed = frontier()
        resumed.restore(snapshot)
        self.assertEqual(len(resumed), len(f))
        self.assertEqual(resumed.seen_count, f.seen_count)

    def test_restored_frontier_refuses_already_seen_urls(self):
        f = frontier()
        f.add(f"{ROOT}/a")
        resumed = frontier()
        resumed.restore(f.snapshot())
        self.assertIs(resumed.add(f"{ROOT}/a")[1], SkipReason.DUPLICATE)

    def test_snapshot_preserves_depth(self):
        f = frontier()
        f.add(f"{ROOT}/deep", depth=4)
        resumed = frontier()
        resumed.restore(f.snapshot())
        self.assertEqual(resumed.take().depth, 4)


if __name__ == "__main__":
    unittest.main()
