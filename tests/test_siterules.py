"""Site-wide analysis, export, and the crawl screens.

Site rules are the ones that cannot exist in a single-page audit, so they are tested against a
crawl of the fixture site rather than against a single document.
"""

import unittest

from audit.crawl import export as crawl_export
from audit.crawl import siterules
from audit.crawl.crawler import Crawler
from audit.crawl.settings import CrawlSettings
from audit.crawl.store import CrawlStore
from audit.report import crawl_pages
from tests.fixture_site import serve


class SiteTestCase(unittest.TestCase):
    """One crawl of the fixture site, shared by every assertion in the class."""

    @classmethod
    def setUpClass(cls):
        cls.base, cls.shutdown, _ = serve()
        cls.store = CrawlStore(":memory:")
        cls.crawler = Crawler(
            cls.base,
            CrawlSettings(max_urls=60, concurrency=4, timeout=5, max_retries=0,
                          check_external_links=False),
            cls.store,
        )
        cls.crawler.run()
        cls.session = cls.crawler.session_id
        cls.report = cls.crawler.site_report

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.shutdown()

    def rules(self):
        return {row["rule"] for row in self.store.issue_summary(self.session)}


class TestSiteAnalysisRuns(SiteTestCase):
    def test_report_produced_by_the_crawl(self):
        self.assertIsNotNone(self.report)
        self.assertTrue(self.report.findings)

    def test_findings_reach_the_issue_list(self):
        """Site findings must be filterable exactly like per-page ones."""
        self.assertTrue(any(rule.startswith("site.") for rule in self.rules()))

    def test_per_page_findings_survive_alongside(self):
        self.assertTrue(any(rule.startswith("seo.") for rule in self.rules()))


class TestDuplicates(SiteTestCase):
    def test_duplicate_titles_detected(self):
        values = {group.value for group in self.report.duplicate_titles}
        self.assertIn("Duplicated Title", values)

    def test_duplicate_group_lists_every_affected_url(self):
        group = next(g for g in self.report.duplicate_titles if g.value == "Duplicated Title")
        self.assertEqual(group.count, 2)
        self.assertTrue(all(url.startswith("http") for url in group.urls))

    def test_duplicate_descriptions_detected(self):
        self.assertTrue(self.report.duplicate_descriptions)

    def test_duplicate_h1s_detected(self):
        values = {group.value for group in self.report.duplicate_h1s}
        self.assertIn("Duplicated Heading", values)

    def test_every_duplicate_url_is_reported_individually(self):
        affected = self.store.urls_with_issue(self.session, "site.duplicate-title")
        self.assertEqual(len(affected), 2)


class TestBrokenLinks(SiteTestCase):
    def test_broken_internal_link_found(self):
        targets = {link.target for link in self.report.broken_internal}
        self.assertIn(self.base + "/gone", targets)

    def test_broken_link_names_its_source(self):
        """A broken link is only actionable if you know which page contains it."""
        link = next(l for l in self.report.broken_internal if l.target.endswith("/gone"))
        self.assertTrue(link.sources)
        self.assertIn(self.base + "/", link.sources)

    def test_server_error_link_found(self):
        targets = {link.target for link in self.report.broken_internal}
        self.assertIn(self.base + "/boom", targets)

    def test_internal_links_need_no_extra_requests(self):
        """Statuses come from the crawl, not from re-requesting each target."""
        self.assertNotIn("external_links_checked", self.report.stats)


class TestRedirects(SiteTestCase):
    def test_redirect_recorded(self):
        self.assertTrue(any(row.url.endswith("/old-page") for row in self.report.redirects))

    def test_link_to_redirect_reported(self):
        self.assertIn("site.link-to-redirect", self.rules())


class TestIndexability(SiteTestCase):
    def test_noindex_pages_reported(self):
        self.assertIn("site.noindex-page", self.rules())

    def test_missing_canonical_reported(self):
        self.assertIn("site.missing-canonical", self.rules())

    def test_low_word_count_reported(self):
        self.assertIn("site.low-word-count", self.rules())


class TestSitemapComparison(SiteTestCase):
    def test_comparison_ran(self):
        self.assertTrue(self.report.sitemap.checked)

    def test_sitemap_url_returning_404_reported(self):
        errors = {url for url, _ in self.report.sitemap.sitemap_errors}
        self.assertIn(self.base + "/gone", errors)

    def test_pages_missing_from_the_sitemap_reported(self):
        self.assertTrue(self.report.sitemap.crawled_not_in_sitemap)
        self.assertIn("site.missing-from-sitemap", self.rules())

    def test_pages_in_the_sitemap_were_crawled(self):
        """/sitemap-only is linked from nowhere, so only the sitemap can have found it."""
        crawled = {row["url"] for row in self.store.iter_urls(self.session)}
        self.assertIn(self.base + "/sitemap-only", crawled)


class TestOrphans(SiteTestCase):
    def test_orphan_detected(self):
        """A page reachable only through the sitemap has no internal links pointing at it."""
        self.assertIn(self.base + "/sitemap-only", self.report.orphans)

    def test_orphans_are_not_double_reported_as_thin_linked(self):
        orphan_urls = {
            row["url"] for row in self.store.urls_with_issue(self.session, "site.orphan-page")
        }
        few_urls = {
            row["url"]
            for row in self.store.urls_with_issue(self.session, "site.few-internal-links")
        }
        self.assertEqual(orphan_urls & few_urls, set())


class TestIdempotence(SiteTestCase):
    def test_rerunning_does_not_duplicate_findings(self):
        """Site findings are recomputed wholesale, so a second pass must replace, not append."""
        before = self.store.count_urls_with_issue(self.session, "site.duplicate-title")
        siterules.analyse(self.store, self.session, self.crawler.settings, self.crawler.sitemap)
        after = self.store.count_urls_with_issue(self.session, "site.duplicate-title")
        self.assertEqual(before, after)


class TestExport(SiteTestCase):
    def csv(self, kind, rule=""):
        return crawl_export.collect(crawl_export.export(self.store, self.session, kind, rule))

    def test_urls_export_has_a_header_and_a_row_per_url(self):
        text = self.csv("urls")
        lines = [line for line in text.splitlines() if line.strip()]
        self.assertIn("URL,Status Code", lines[0])
        self.assertEqual(len(lines) - 1, self.store.count_urls(self.session))

    def test_export_starts_with_a_bom_for_excel(self):
        self.assertTrue(self.csv("urls").startswith("﻿"))

    def test_every_brief_column_is_present(self):
        header = self.csv("urls").splitlines()[0]
        for column in ("URL", "Status Code", "Indexability", "Title", "Title Length",
                       "Meta Description", "Meta Length", "H1", "H1 Count", "Canonical",
                       "Word Count", "Internal Links", "External Links", "Images",
                       "Missing ALT", "Hreflang", "Schema", "Crawl Depth"):
            with self.subTest(column=column):
                self.assertIn(column, header)

    def test_issue_export_lists_only_affected_urls(self):
        text = self.csv("issues", rule="site.duplicate-title")
        lines = [line for line in text.splitlines() if line.strip()]
        self.assertEqual(len(lines) - 1, 2)

    def test_links_export(self):
        self.assertIn("Source,Target,Type", self.csv("links").splitlines()[0])

    def test_broken_links_export_contains_only_failures(self):
        lines = [line for line in self.csv("broken-links").splitlines()[1:] if line.strip()]
        self.assertTrue(lines)
        for line in lines:
            with self.subTest(line=line[:60]):
                self.assertTrue(line.rstrip().endswith(("404", "500", "unreachable")))

    def test_unknown_export_rejected(self):
        with self.assertRaises(ValueError):
            crawl_export.export(self.store, self.session, "nonsense")

    def test_filenames(self):
        self.assertEqual(crawl_export.filename_for("urls"), "crawl-urls.csv")
        self.assertEqual(
            crawl_export.filename_for("", "site.duplicate-title"), "site-duplicate-title.csv"
        )

    def test_export_is_streamed_not_assembled(self):
        chunks = list(crawl_export.urls_csv(self.store, self.session))
        self.assertGreater(len(chunks), 5, "a streamed export yields many chunks")


class TestCrawlScreens(SiteTestCase):
    def test_dashboard_renders(self):
        html = crawl_pages.dashboard(self.store, self.session)
        self.assertIn("Website SEO Audit", html)
        self.assertIn("Pages crawled", html)
        self.assertNotIn("<script", html.lower())

    def test_url_table_renders_one_page_only(self):
        html = crawl_pages.url_table(self.store, self.session)
        self.assertLessEqual(html.count("<tr>"), crawl_pages.PAGE_SIZE + 2)

    def test_url_table_filters(self):
        html = crawl_pages.url_table(self.store, self.session, filter_key="4xx")
        self.assertIn("4xx Errors", html)

    def test_url_table_rejects_an_unsafe_sort_column(self):
        html = crawl_pages.url_table(
            self.store, self.session, sort="url; DROP TABLE crawl_url"
        )
        self.assertIn("<table", html)
        self.assertGreater(self.store.count_urls(self.session), 0)

    def test_issue_list_uses_generic_labels(self):
        """A group label must not state something true of only one of its URLs."""
        html = crawl_pages.issue_list(self.store, self.session)
        self.assertIn("Duplicate title", html)
        self.assertNotIn('class="t">Duplicate title shared by', html)

    def test_issue_detail_lists_affected_urls(self):
        html = crawl_pages.issue_detail(self.store, self.session, "site.duplicate-title")
        self.assertIn("duplicate-a", html)
        self.assertIn("duplicate-b", html)

    def test_url_detail_renders_findings(self):
        row = next(iter(self.store.iter_urls(self.session)))
        html = crawl_pages.url_detail(self.store, self.session, row["id"])
        self.assertIn("Basic information", html)
        self.assertIn("Metadata", html)

    def test_url_detail_links_back_to_the_single_page_audit(self):
        """The full report is the existing Mode A, not a reimplementation of it."""
        row = next(iter(self.store.iter_urls(self.session)))
        html = crawl_pages.url_detail(self.store, self.session, row["id"])
        self.assertIn("Run the full single-page audit", html)
        self.assertIn('href="/?url=', html)

    def test_url_detail_handles_a_missing_id(self):
        self.assertIn("not part of this crawl", crawl_pages.url_detail(self.store, self.session, 0))

    def test_links_page_renders(self):
        self.assertIn("Source page", crawl_pages.links_page(self.store, self.session))

    def test_technical_page_renders(self):
        html = crawl_pages.technical_page(
            self.store, self.session,
            {"url": "x", "found": True, "status": 200, "summary": "ok", "sitemaps": [],
             "rules": ["Disallow: /private/"], "crawl_delay": None},
            {"found": ["s"], "url_count": 5, "is_index": False, "duplicate_count": 0},
        )
        self.assertIn("robots.txt", html)
        self.assertIn("Disallow: /private/", html)

    def test_every_screen_is_script_free(self):
        screens = [
            crawl_pages.crawl_form(),
            crawl_pages.dashboard(self.store, self.session),
            crawl_pages.url_table(self.store, self.session),
            crawl_pages.issue_list(self.store, self.session),
            crawl_pages.links_page(self.store, self.session),
        ]
        for index, html in enumerate(screens):
            with self.subTest(screen=index):
                self.assertNotIn("<script", html.lower())
                self.assertNotIn("onclick", html.lower())

    def test_issue_label_humanises_rule_ids(self):
        self.assertEqual(crawl_pages.issue_label("site.duplicate-title"), "Duplicate title")
        self.assertEqual(
            crawl_pages.issue_label("seo.missing-meta-description"), "Missing meta description"
        )


if __name__ == "__main__":
    unittest.main()
