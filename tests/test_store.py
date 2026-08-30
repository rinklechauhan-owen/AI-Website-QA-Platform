"""Crawl persistence: sessions, incremental writes, paginated reads, aggregates."""

import threading
import unittest

from audit.crawl.store import SORTABLE_COLUMNS, CrawlStore
from audit.findings import Finding, Severity

ROOT = "https://example.com"


def page(url, **overrides):
    record = {
        "url": url,
        "dedupe_key": url.rstrip("/"),
        "depth": 1,
        "status_code": 200,
        "final_url": url,
        "title": "A title",
        "title_length": 7,
        "meta_description": "A description",
        "meta_length": 13,
        "h1": "A heading",
        "h1_count": 1,
        "word_count": 400,
        "internal_links": 5,
        "external_links": 2,
        "images": 3,
        "missing_alt": 0,
        "score": 90.0,
        "issue_count": 0,
        "result_json": '{"url": "%s"}' % url,
    }
    record.update(overrides)
    return record


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.store = CrawlStore(":memory:")
        self.session = self.store.create_session(ROOT, '{"max_urls": 2000}')

    def tearDown(self):
        self.store.close()


class TestSessions(StoreTestCase):
    def test_session_created_running(self):
        row = self.store.get_session(self.session)
        self.assertEqual(row.root_url, ROOT)
        self.assertEqual(row.status, "running")
        self.assertTrue(row.is_running)

    def test_settings_round_trip(self):
        self.assertIn("2000", self.store.session_settings_json(self.session))

    def test_finish_sets_status_and_score(self):
        self.store.add_url(self.session, page(f"{ROOT}/a", score=80.0))
        self.store.add_url(self.session, page(f"{ROOT}/b", score=100.0))
        self.store.finish_session(self.session)
        row = self.store.get_session(self.session)
        self.assertEqual(row.status, "completed")
        self.assertEqual(row.health_score, 90.0)
        self.assertIsNotNone(row.finished_at)

    def test_sessions_listed_newest_first(self):
        second = self.store.create_session("https://other.test")
        self.assertEqual([s.id for s in self.store.list_sessions()], [second, self.session])

    def test_two_sessions_stay_separate(self):
        """Crawl comparison later depends on sessions not bleeding into each other."""
        other = self.store.create_session("https://other.test")
        self.store.add_url(self.session, page(f"{ROOT}/a"))
        self.store.add_url(other, page("https://other.test/a"))
        self.assertEqual(self.store.count_urls(self.session), 1)
        self.assertEqual(self.store.count_urls(other), 1)

    def test_delete_removes_everything(self):
        url_id = self.store.add_url(self.session, page(f"{ROOT}/a"))
        self.store.add_issues(
            self.session, url_id, f"{ROOT}/a",
            [Finding(rule="seo.x", module="seo", severity=Severity.HIGH, title="x")],
        )
        self.store.delete_session(self.session)
        self.assertIsNone(self.store.get_session(self.session))
        self.assertEqual(self.store.count_urls(self.session), 0)


class TestUrls(StoreTestCase):
    def test_add_and_count(self):
        self.store.add_url(self.session, page(f"{ROOT}/a"))
        self.assertEqual(self.store.count_urls(self.session), 1)

    def test_same_key_updates_rather_than_duplicating(self):
        self.store.add_url(self.session, page(f"{ROOT}/a", title="First"))
        self.store.add_url(self.session, page(f"{ROOT}/a", title="Second"))
        self.assertEqual(self.store.count_urls(self.session), 1)
        rows = self.store.urls_page(self.session)
        self.assertEqual(rows[0]["title"], "Second")

    def test_result_json_round_trips(self):
        url_id = self.store.add_url(self.session, page(f"{ROOT}/a"))
        self.assertEqual(self.store.result_for(self.session, url_id)["url"], f"{ROOT}/a")

    def test_pagination_never_returns_everything(self):
        for i in range(250):
            self.store.add_url(self.session, page(f"{ROOT}/p{i}"))
        first = self.store.urls_page(self.session, limit=100, offset=0)
        second = self.store.urls_page(self.session, limit=100, offset=100)
        self.assertEqual(len(first), 100)
        self.assertEqual(len(second), 100)
        self.assertNotEqual({r["url"] for r in first}, {r["url"] for r in second})

    def test_sorting(self):
        self.store.add_url(self.session, page(f"{ROOT}/a", word_count=100))
        self.store.add_url(self.session, page(f"{ROOT}/b", word_count=900))
        rows = self.store.urls_page(self.session, sort="word_count", descending=True)
        self.assertEqual(rows[0]["word_count"], 900)

    def test_unknown_sort_column_falls_back_safely(self):
        """A sort column reaches SQL by interpolation, so it must be allow-listed."""
        self.store.add_url(self.session, page(f"{ROOT}/a"))
        rows = self.store.urls_page(self.session, sort="url; DROP TABLE crawl_url")
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.store.count_urls(self.session), 1)

    def test_sortable_columns_are_real_columns(self):
        row = self.store.urls_page(self.session, limit=1)
        self.store.add_url(self.session, page(f"{ROOT}/a"))
        row = self.store.urls_page(self.session, limit=1)[0]
        for column in SORTABLE_COLUMNS:
            with self.subTest(column=column):
                self.assertIn(column, row.keys())

    def test_filtering(self):
        self.store.add_url(self.session, page(f"{ROOT}/ok", status_code=200))
        self.store.add_url(self.session, page(f"{ROOT}/gone", status_code=404))
        rows = self.store.urls_page(self.session, where="status_code = ?", params=(404,))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], f"{ROOT}/gone")

    def test_search(self):
        self.store.add_url(self.session, page(f"{ROOT}/services/seo"))
        self.store.add_url(self.session, page(f"{ROOT}/about"))
        self.assertEqual(len(self.store.urls_page(self.session, search="services")), 1)

    def test_iter_streams_every_row(self):
        for i in range(120):
            self.store.add_url(self.session, page(f"{ROOT}/p{i}"))
        self.assertEqual(len(list(self.store.iter_urls(self.session, batch=25))), 120)

    def test_failed_page_is_stored_with_its_error(self):
        """A URL that never responded still gets a row, or the crawl loses the evidence."""
        self.store.add_url(
            self.session, page(f"{ROOT}/dead", status_code=None, error="timed out", score=None)
        )
        row = self.store.urls_page(self.session)[0]
        self.assertIsNone(row["status_code"])
        self.assertEqual(row["error"], "timed out")


class TestIssues(StoreTestCase):
    def _add(self, url, rule, severity=Severity.HIGH):
        url_id = self.store.add_url(self.session, page(url))
        self.store.add_issues(
            self.session, url_id, url,
            [Finding(rule=rule, module="seo", severity=severity, title=rule)],
        )

    def test_issue_summary_counts_affected_urls(self):
        self._add(f"{ROOT}/a", "seo.missing-meta-description")
        self._add(f"{ROOT}/b", "seo.missing-meta-description")
        self._add(f"{ROOT}/c", "seo.missing-h1")
        summary = {row["rule"]: row["urls"] for row in self.store.issue_summary(self.session)}
        self.assertEqual(summary["seo.missing-meta-description"], 2)
        self.assertEqual(summary["seo.missing-h1"], 1)

    def test_summary_ordered_by_severity(self):
        self._add(f"{ROOT}/a", "seo.low-thing", Severity.LOW)
        self._add(f"{ROOT}/b", "seo.critical-thing", Severity.CRITICAL)
        self.assertEqual(self.store.issue_summary(self.session)[0]["severity"], "critical")

    def test_urls_for_one_issue(self):
        self._add(f"{ROOT}/a", "seo.missing-h1")
        self._add(f"{ROOT}/b", "seo.missing-h1")
        rows = self.store.urls_with_issue(self.session, "seo.missing-h1")
        self.assertEqual({r["url"] for r in rows}, {f"{ROOT}/a", f"{ROOT}/b"})
        self.assertEqual(self.store.count_urls_with_issue(self.session, "seo.missing-h1"), 2)

    def test_severity_counts(self):
        self._add(f"{ROOT}/a", "x", Severity.HIGH)
        self._add(f"{ROOT}/b", "y", Severity.LOW)
        counts = self.store.severity_counts(self.session)
        self.assertEqual(counts["high"], 1)
        self.assertEqual(counts["low"], 1)


class TestAggregates(StoreTestCase):
    def test_status_breakdown(self):
        for index, code in enumerate((200, 200, 301, 404, 500, None)):
            self.store.add_url(self.session, page(f"{ROOT}/p{index}", status_code=code))
        buckets = self.store.status_breakdown(self.session)
        self.assertEqual(buckets["2xx"], 2)
        self.assertEqual(buckets["3xx"], 1)
        self.assertEqual(buckets["4xx"], 1)
        self.assertEqual(buckets["5xx"], 1)
        self.assertEqual(buckets["failed"], 1)

    def test_duplicate_titles(self):
        self.store.add_url(self.session, page(f"{ROOT}/a", title="Same"))
        self.store.add_url(self.session, page(f"{ROOT}/b", title="Same"))
        self.store.add_url(self.session, page(f"{ROOT}/c", title="Different"))
        duplicates = self.store.duplicates(self.session, "title")
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0]["value"], "Same")
        self.assertEqual(duplicates[0]["n"], 2)

    def test_duplicates_ignore_empty_values(self):
        self.store.add_url(self.session, page(f"{ROOT}/a", title=""))
        self.store.add_url(self.session, page(f"{ROOT}/b", title=""))
        self.assertEqual(self.store.duplicates(self.session, "title"), [])

    def test_duplicates_ignore_error_pages(self):
        """Two 404s sharing a title are not a duplicate-content problem."""
        self.store.add_url(self.session, page(f"{ROOT}/a", title="Not found", status_code=404))
        self.store.add_url(self.session, page(f"{ROOT}/b", title="Not found", status_code=404))
        self.assertEqual(self.store.duplicates(self.session, "title"), [])

    def test_duplicate_column_is_allow_listed(self):
        with self.assertRaises(ValueError):
            self.store.duplicates(self.session, "url; DROP TABLE crawl_url")

    def test_depth_breakdown(self):
        self.store.add_url(self.session, page(f"{ROOT}/", depth=0))
        self.store.add_url(self.session, page(f"{ROOT}/a", depth=1))
        self.store.add_url(self.session, page(f"{ROOT}/b", depth=1))
        self.assertEqual(self.store.depth_breakdown(self.session), {0: 1, 1: 2})

    def test_health_score_ignores_unscored_pages(self):
        self.store.add_url(self.session, page(f"{ROOT}/a", score=80.0))
        self.store.add_url(self.session, page(f"{ROOT}/dead", score=None))
        self.assertEqual(self.store.health_score(self.session), 80.0)


class TestLinks(StoreTestCase):
    def test_links_recorded_and_queried(self):
        self.store.add_links(
            self.session,
            [
                {"source_url": f"{ROOT}/a", "target_url": f"{ROOT}/b", "is_internal": True},
                {"source_url": f"{ROOT}/c", "target_url": f"{ROOT}/b", "is_internal": True},
            ],
        )
        self.assertEqual(len(self.store.links_to(self.session, f"{ROOT}/b")), 2)
        self.assertEqual(self.store.inlink_counts(self.session)[f"{ROOT}/b"], 2)

    def test_orphan_detection(self):
        self.store.add_url(self.session, page(f"{ROOT}/linked", depth=1))
        self.store.add_url(self.session, page(f"{ROOT}/orphan", depth=1))
        self.store.add_links(
            self.session,
            [{"source_url": f"{ROOT}/", "target_url": f"{ROOT}/linked", "is_internal": True}],
        )
        orphans = [r["url"] for r in self.store.orphans(self.session)]
        self.assertEqual(orphans, [f"{ROOT}/orphan"])

    def test_homepage_is_never_an_orphan(self):
        self.store.add_url(self.session, page(f"{ROOT}/", depth=0))
        self.assertEqual(self.store.orphans(self.session), [])


class TestFrontierPersistence(StoreTestCase):
    def test_snapshot_round_trip(self):
        snapshot = {"queued": [{"url": f"{ROOT}/a", "key": f"{ROOT}/a", "depth": 1}],
                    "seen": [f"{ROOT}/a"]}
        self.store.save_frontier(self.session, snapshot)
        self.assertEqual(self.store.load_frontier(self.session), snapshot)

    def test_saving_twice_overwrites(self):
        self.store.save_frontier(self.session, {"seen": ["a"]})
        self.store.save_frontier(self.session, {"seen": ["b"]})
        self.assertEqual(self.store.load_frontier(self.session), {"seen": ["b"]})

    def test_absent_snapshot_returns_none(self):
        self.assertIsNone(self.store.load_frontier(999))


class TestConcurrentWrites(unittest.TestCase):
    def test_workers_can_write_at_once(self):
        """The crawler writes from a thread pool; losing rows to locking would be silent."""
        store = CrawlStore(":memory:")
        session = store.create_session(ROOT)

        def worker(start):
            for i in range(start, start + 50):
                store.add_url(session, page(f"{ROOT}/p{i}"))

        threads = [threading.Thread(target=worker, args=(n * 50,)) for n in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(store.count_urls(session), 300)
        store.close()


if __name__ == "__main__":
    unittest.main()
