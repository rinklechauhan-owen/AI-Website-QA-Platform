"""Sitemap XML parsing."""

import unittest
import xml.etree.ElementTree as ET

from audit.crawl import sitemap

URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/</loc>
    <lastmod>2026-07-01</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url><loc>https://example.com/about</loc></url>
  <url><loc>https://example.com/contact</loc></url>
</urlset>"""

INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-posts.xml</loc></sitemap>
</sitemapindex>"""

NO_NAMESPACE = """<urlset>
  <url><loc>https://example.com/a</loc></url>
</urlset>"""


class TestParsing(unittest.TestCase):
    def test_urlset_entries(self):
        parsed = sitemap.parse_xml(URLSET)
        self.assertEqual(len(parsed["entries"]), 3)
        self.assertEqual(parsed["entries"][0].loc, "https://example.com/")
        self.assertEqual(parsed["sitemaps"], [])

    def test_metadata_captured(self):
        first = sitemap.parse_xml(URLSET)["entries"][0]
        self.assertEqual(first.lastmod, "2026-07-01")
        self.assertEqual(first.changefreq, "daily")
        self.assertEqual(first.priority, "1.0")

    def test_index_yields_child_sitemaps_not_urls(self):
        parsed = sitemap.parse_xml(INDEX)
        self.assertEqual(parsed["entries"], [])
        self.assertEqual(len(parsed["sitemaps"]), 2)
        self.assertEqual(parsed["root"], "sitemapindex")

    def test_namespace_is_not_required(self):
        """Real sitemaps declare the namespace inconsistently."""
        self.assertEqual(len(sitemap.parse_xml(NO_NAMESPACE)["entries"]), 1)

    def test_entries_without_loc_are_skipped(self):
        xml = "<urlset><url><lastmod>2026-01-01</lastmod></url>" \
              "<url><loc>https://example.com/a</loc></url></urlset>"
        self.assertEqual(len(sitemap.parse_xml(xml)["entries"]), 1)

    def test_whitespace_around_loc_trimmed(self):
        xml = "<urlset><url><loc>\n  https://example.com/a  \n</loc></url></urlset>"
        self.assertEqual(sitemap.parse_xml(xml)["entries"][0].loc, "https://example.com/a")

    def test_malformed_xml_raises_for_the_caller_to_report(self):
        with self.assertRaises(ET.ParseError):
            sitemap.parse_xml("<urlset><url><loc>broken")

    def test_empty_sitemap(self):
        self.assertEqual(sitemap.parse_xml("<urlset></urlset>")["entries"], [])


class TestReport(unittest.TestCase):
    def _report(self):
        report = sitemap.SitemapReport()
        report.found = ["https://example.com/sitemap.xml"]
        report.entries = sitemap.parse_xml(URLSET, source="s")["entries"]
        return report

    def test_urls_listed(self):
        self.assertEqual(len(self._report().urls), 3)

    def test_url_set_uses_dedupe_keys(self):
        """Sitemap URLs must be comparable with crawled URLs, so both are normalised."""
        report = self._report()
        keys = report.url_set()
        self.assertIn("https://example.com/about", keys)

    def test_url_set_folds_trailing_slash_variants(self):
        report = sitemap.SitemapReport()
        report.entries = [
            sitemap.SitemapEntry(loc="https://example.com/about"),
            sitemap.SitemapEntry(loc="https://example.com/about/"),
        ]
        self.assertEqual(len(report.url_set()), 1)

    def test_any_found_flag(self):
        self.assertTrue(self._report().any_found)
        self.assertFalse(sitemap.SitemapReport().any_found)

    def test_serialisable(self):
        payload = self._report().to_dict()
        self.assertEqual(payload["url_count"], 3)


if __name__ == "__main__":
    unittest.main()
