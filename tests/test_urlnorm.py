"""URL normalisation — the foundation the whole crawl depends on."""

import unittest

from audit.crawl import urlnorm

ROOT = "https://example.com"


class TestNormalise(unittest.TestCase):
    def test_absolute_url_passes_through(self):
        self.assertEqual(urlnorm.normalise("https://example.com/a"), "https://example.com/a")

    def test_relative_resolved_against_base(self):
        self.assertEqual(
            urlnorm.normalise("/about", "https://example.com/team/"),
            "https://example.com/about",
        )

    def test_document_relative_resolved(self):
        self.assertEqual(
            urlnorm.normalise("page.html", "https://example.com/blog/index.html"),
            "https://example.com/blog/page.html",
        )

    def test_protocol_relative_takes_the_base_scheme(self):
        self.assertEqual(
            urlnorm.normalise("//cdn.example.com/x", "https://example.com/"),
            "https://cdn.example.com/x",
        )

    def test_fragment_is_dropped(self):
        self.assertEqual(
            urlnorm.normalise("https://example.com/about#section"),
            "https://example.com/about",
        )

    def test_scheme_and_host_lowercased(self):
        self.assertEqual(
            urlnorm.normalise("HTTPS://Example.COM/Path"), "https://example.com/Path"
        )

    def test_path_case_is_preserved(self):
        """Paths are case-sensitive on most servers; folding them would fetch the wrong page."""
        self.assertEqual(
            urlnorm.normalise("https://example.com/CaseSensitive"),
            "https://example.com/CaseSensitive",
        )

    def test_default_ports_removed(self):
        self.assertEqual(urlnorm.normalise("https://example.com:443/a"), "https://example.com/a")
        self.assertEqual(urlnorm.normalise("http://example.com:80/a"), "http://example.com/a")

    def test_non_default_port_kept(self):
        self.assertEqual(
            urlnorm.normalise("http://example.com:8080/a"), "http://example.com:8080/a"
        )

    def test_dot_segments_resolved(self):
        self.assertEqual(
            urlnorm.normalise("https://example.com/a/b/../c"), "https://example.com/a/c"
        )
        self.assertEqual(
            urlnorm.normalise("https://example.com/a/./b"), "https://example.com/a/b"
        )

    def test_duplicate_slashes_collapsed(self):
        self.assertEqual(urlnorm.normalise("https://example.com//a///b"), "https://example.com/a/b")

    def test_empty_path_becomes_root(self):
        self.assertEqual(urlnorm.normalise("https://example.com"), "https://example.com/")

    def test_percent_encoding_hex_uppercased(self):
        self.assertEqual(
            urlnorm.normalise("https://example.com/a%2fb"), "https://example.com/a%2Fb"
        )

    def test_needlessly_encoded_characters_decoded(self):
        """%7E is just '~'; leaving both spellings alive would duplicate the page."""
        self.assertEqual(urlnorm.normalise("https://example.com/%7Euser"),
                         "https://example.com/~user")

    def test_multibyte_escapes_survive_intact(self):
        """%C3%A9 is one character (é). Decoding it bytewise corrupts the URL."""
        self.assertEqual(
            urlnorm.normalise("https://example.com/caf%C3%A9"),
            "https://example.com/caf%C3%A9",
        )

    def test_raw_non_ascii_is_encoded_consistently(self):
        self.assertEqual(
            urlnorm.normalise("https://example.com/café"), "https://example.com/caf%C3%A9"
        )

    def test_encoded_and_raw_non_ascii_agree(self):
        self.assertEqual(
            urlnorm.normalise("https://example.com/café"),
            urlnorm.normalise("https://example.com/caf%C3%A9"),
        )

    def test_encoded_slash_is_not_a_path_separator(self):
        """%2F sits inside a segment; turning it into '/' points at a different resource."""
        self.assertEqual(
            urlnorm.normalise("https://example.com/a%2Fb"), "https://example.com/a%2Fb"
        )
        self.assertNotEqual(
            urlnorm.dedupe_key("https://example.com/a%2Fb"),
            urlnorm.dedupe_key("https://example.com/a/b"),
        )

    def test_spaces_encoded(self):
        self.assertEqual(
            urlnorm.normalise("https://example.com/my page"), "https://example.com/my%20page"
        )

    def test_whitespace_and_newlines_stripped(self):
        self.assertEqual(
            urlnorm.normalise("  https://example.com/a\n  "), "https://example.com/a"
        )

    def test_query_is_preserved_when_fetching(self):
        self.assertEqual(
            urlnorm.normalise("https://example.com/s?q=1&p=2"), "https://example.com/s?q=1&p=2"
        )

    def test_non_crawlable_schemes_rejected(self):
        for url in (
            "mailto:a@b.com", "tel:+441610000000", "javascript:void(0)",
            "data:text/html,<h1>x</h1>", "ftp://files.example.com/x", "file:///etc/passwd",
        ):
            with self.subTest(url=url):
                self.assertIsNone(urlnorm.normalise(url))

    def test_empty_and_none_rejected(self):
        self.assertIsNone(urlnorm.normalise(""))
        self.assertIsNone(urlnorm.normalise("   "))
        self.assertIsNone(urlnorm.normalise(None))

    def test_missing_host_rejected(self):
        self.assertIsNone(urlnorm.normalise("https://"))


class TestDedupeKey(unittest.TestCase):
    def key(self, url, **kwargs):
        return urlnorm.dedupe_key(url, **kwargs)

    def test_trailing_slash_folded(self):
        """The brief's example: /about and /about/ are one page."""
        self.assertEqual(self.key(f"{ROOT}/about"), self.key(f"{ROOT}/about/"))

    def test_fragment_folded(self):
        self.assertEqual(self.key(f"{ROOT}/about"), self.key(f"{ROOT}/about#section"))

    def test_root_slash_preserved(self):
        self.assertEqual(self.key(ROOT), f"{ROOT}/")

    def test_index_page_folds_into_its_directory(self):
        self.assertEqual(self.key(f"{ROOT}/blog/index.html"), self.key(f"{ROOT}/blog/"))
        self.assertEqual(self.key(f"{ROOT}/index.php"), self.key(ROOT))

    def test_tracking_parameters_stripped(self):
        self.assertEqual(
            self.key(f"{ROOT}/p?utm_source=news&utm_campaign=x"), self.key(f"{ROOT}/p")
        )
        self.assertEqual(self.key(f"{ROOT}/p?fbclid=abc"), self.key(f"{ROOT}/p"))
        self.assertEqual(self.key(f"{ROOT}/p?gclid=abc"), self.key(f"{ROOT}/p"))

    def test_meaningful_parameters_kept(self):
        self.assertNotEqual(self.key(f"{ROOT}/s?q=shoes"), self.key(f"{ROOT}/s"))

    def test_parameter_order_does_not_matter(self):
        self.assertEqual(self.key(f"{ROOT}/s?a=1&b=2"), self.key(f"{ROOT}/s?b=2&a=1"))

    def test_tracking_mixed_with_real_parameters(self):
        self.assertEqual(
            self.key(f"{ROOT}/s?q=shoes&utm_source=news"), self.key(f"{ROOT}/s?q=shoes")
        )

    def test_ignore_query_option(self):
        self.assertEqual(
            self.key(f"{ROOT}/s?q=1", ignore_query=True), self.key(f"{ROOT}/s", ignore_query=True)
        )

    def test_extra_drop_params(self):
        self.assertEqual(
            self.key(f"{ROOT}/p?sessionid=9", extra_drop_params=["sessionid"]),
            self.key(f"{ROOT}/p"),
        )

    def test_trailing_slash_folding_can_be_disabled(self):
        self.assertNotEqual(
            self.key(f"{ROOT}/about", ignore_trailing_slash=False),
            self.key(f"{ROOT}/about/", ignore_trailing_slash=False),
        )

    def test_case_insensitive_path_option(self):
        self.assertEqual(
            self.key(f"{ROOT}/About", case_insensitive_path=True),
            self.key(f"{ROOT}/about", case_insensitive_path=True),
        )

    def test_http_and_https_are_different_keys(self):
        """Different scheme is genuinely a different resource; folding would hide redirects."""
        self.assertNotEqual(self.key("http://example.com/a"), self.key("https://example.com/a"))

    def test_uncrawlable_returns_none(self):
        self.assertIsNone(self.key("mailto:a@b.com"))


class TestSiteClassification(unittest.TestCase):
    def test_same_host_is_internal(self):
        self.assertTrue(urlnorm.is_internal(f"{ROOT}/a", ROOT))

    def test_www_matches_bare_domain(self):
        self.assertTrue(urlnorm.is_internal("https://www.example.com/a", ROOT))
        self.assertTrue(urlnorm.is_internal("https://example.com/a", "https://www.example.com"))

    def test_other_domain_is_external(self):
        self.assertFalse(urlnorm.is_internal("https://other.test/a", ROOT))

    def test_subdomain_excluded_by_default(self):
        self.assertFalse(urlnorm.is_internal("https://blog.example.com/a", ROOT))

    def test_subdomain_included_when_enabled(self):
        self.assertTrue(
            urlnorm.is_internal("https://blog.example.com/a", ROOT, allow_subdomains=True)
        )

    def test_lookalike_domain_is_not_a_subdomain(self):
        """notexample.com must not match example.com."""
        self.assertFalse(
            urlnorm.is_internal("https://notexample.com/a", ROOT, allow_subdomains=True)
        )


class TestResourceClassification(unittest.TestCase):
    def test_binary_extensions_detected(self):
        for url in (f"{ROOT}/a.jpg", f"{ROOT}/b.css", f"{ROOT}/c.zip", f"{ROOT}/d.MP4"):
            with self.subTest(url=url):
                self.assertTrue(urlnorm.looks_like_binary(url))

    def test_pdf_is_a_document_not_a_binary(self):
        self.assertTrue(urlnorm.looks_like_document(f"{ROOT}/report.pdf"))
        self.assertFalse(urlnorm.looks_like_binary(f"{ROOT}/report.pdf"))

    def test_html_pages_are_neither(self):
        for url in (f"{ROOT}/about", f"{ROOT}/about/", f"{ROOT}/page.html"):
            with self.subTest(url=url):
                self.assertFalse(urlnorm.looks_like_binary(url))
                self.assertFalse(urlnorm.looks_like_document(url))

    def test_extension_detection_ignores_query(self):
        self.assertEqual(urlnorm.extension_of(f"{ROOT}/a.jpg?v=2"), ".jpg")

    def test_dot_in_path_is_not_an_extension(self):
        self.assertEqual(urlnorm.extension_of(f"{ROOT}/version-1.2.3-notes"), "")


class TestPatternMatching(unittest.TestCase):
    def test_substring_match(self):
        self.assertTrue(urlnorm.matches_any(f"{ROOT}/blog/post", ["/blog/"]))
        self.assertFalse(urlnorm.matches_any(f"{ROOT}/about", ["/blog/"]))

    def test_glob_match(self):
        self.assertTrue(urlnorm.matches_any(f"{ROOT}/tag/x", ["*/tag/*"]))

    def test_case_insensitive(self):
        self.assertTrue(urlnorm.matches_any(f"{ROOT}/Blog/Post", ["/blog/"]))

    def test_empty_patterns_never_match(self):
        self.assertFalse(urlnorm.matches_any(f"{ROOT}/a", []))
        self.assertFalse(urlnorm.matches_any(f"{ROOT}/a", ["  "]))


class TestTrapDetection(unittest.TestCase):
    def test_repeating_segments_flagged(self):
        self.assertTrue(urlnorm.looks_like_trap(f"{ROOT}/a/b/a/b/a/b/a/b"))

    def test_normal_deep_path_not_flagged(self):
        self.assertFalse(urlnorm.looks_like_trap(f"{ROOT}/services/seo/technical/audits"))

    def test_short_path_not_flagged(self):
        self.assertFalse(urlnorm.looks_like_trap(f"{ROOT}/a/a"))


if __name__ == "__main__":
    unittest.main()
