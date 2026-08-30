"""robots.txt parsing and rule matching."""

import unittest

from audit.crawl import robots

UA = "AI-Website-QA-Platform/0.1"


def build(text: str, user_agent: str = UA) -> robots.RobotsTxt:
    rules, sitemaps, delay, group = robots.parse(text, user_agent)
    return robots.RobotsTxt(
        url="https://example.com/robots.txt",
        found=True,
        status=200,
        body=text,
        rules=rules,
        sitemaps=sitemaps,
        crawl_delay=delay,
        matched_group=group,
    )


class TestParsing(unittest.TestCase):
    def test_wildcard_group_applies(self):
        rt = build("User-agent: *\nDisallow: /private/")
        self.assertEqual(rt.matched_group, "*")
        self.assertFalse(rt.allows("https://example.com/private/x"))
        self.assertTrue(rt.allows("https://example.com/public/x"))

    def test_named_group_beats_wildcard(self):
        rt = build(
            "User-agent: *\nDisallow: /\n\n"
            "User-agent: AI-Website-QA-Platform\nDisallow: /admin/\n"
        )
        self.assertEqual(rt.matched_group, "ai-website-qa-platform")
        self.assertTrue(rt.allows("https://example.com/anything"))
        self.assertFalse(rt.allows("https://example.com/admin/x"))

    def test_comments_and_blank_lines_ignored(self):
        rt = build("# a comment\n\nUser-agent: *  # trailing\nDisallow: /x  # here\n")
        self.assertFalse(rt.allows("https://example.com/x"))

    def test_sitemaps_collected(self):
        rt = build(
            "Sitemap: https://example.com/sitemap.xml\n"
            "User-agent: *\nDisallow:\n"
            "Sitemap: https://example.com/news.xml\n"
        )
        self.assertEqual(
            rt.sitemaps, ["https://example.com/sitemap.xml", "https://example.com/news.xml"]
        )

    def test_crawl_delay_read(self):
        self.assertEqual(build("User-agent: *\nCrawl-delay: 2.5").crawl_delay, 2.5)

    def test_empty_disallow_allows_everything(self):
        rt = build("User-agent: *\nDisallow:")
        self.assertTrue(rt.allows("https://example.com/anything"))

    def test_multiple_agents_share_one_group(self):
        rt = build("User-agent: googlebot\nUser-agent: *\nDisallow: /x")
        self.assertFalse(rt.allows("https://example.com/x"))

    def test_empty_file_allows_everything(self):
        self.assertTrue(build("").allows("https://example.com/anything"))


class TestMatching(unittest.TestCase):
    def test_prefix_match(self):
        rt = build("User-agent: *\nDisallow: /admin")
        self.assertFalse(rt.allows("https://example.com/admin"))
        self.assertFalse(rt.allows("https://example.com/administrator"))
        self.assertTrue(rt.allows("https://example.com/adm"))

    def test_wildcard_in_pattern(self):
        rt = build("User-agent: *\nDisallow: /*.pdf")
        self.assertFalse(rt.allows("https://example.com/files/report.pdf"))
        self.assertTrue(rt.allows("https://example.com/files/report.html"))

    def test_end_anchor(self):
        rt = build("User-agent: *\nDisallow: /page$")
        self.assertFalse(rt.allows("https://example.com/page"))
        self.assertTrue(rt.allows("https://example.com/page/sub"))

    def test_longest_pattern_wins(self):
        rt = build("User-agent: *\nDisallow: /a/\nAllow: /a/b/")
        self.assertFalse(rt.allows("https://example.com/a/x"))
        self.assertTrue(rt.allows("https://example.com/a/b/x"))

    def test_allow_wins_a_tie(self):
        rt = build("User-agent: *\nDisallow: /page\nAllow: /page")
        self.assertTrue(rt.allows("https://example.com/page"))

    def test_query_string_is_part_of_the_path(self):
        rt = build("User-agent: *\nDisallow: /*?sort=")
        self.assertFalse(rt.allows("https://example.com/list?sort=price"))
        self.assertTrue(rt.allows("https://example.com/list"))

    def test_disallow_all(self):
        rt = build("User-agent: *\nDisallow: /")
        self.assertTrue(rt.blocks_everything)
        self.assertFalse(rt.allows("https://example.com/"))

    def test_root_only_pattern_still_blocks_subpaths(self):
        rt = build("User-agent: *\nDisallow: /")
        self.assertFalse(rt.allows("https://example.com/deep/page"))


class TestExplanation(unittest.TestCase):
    def test_blocked_url_names_the_rule(self):
        rt = build("User-agent: *\nDisallow: /private/")
        message = rt.explain("https://example.com/private/x")
        self.assertIn("Blocked", message)
        self.assertIn("Disallow: /private/", message)

    def test_allowed_url_with_no_rule(self):
        rt = build("User-agent: *\nDisallow: /x")
        self.assertIn("no matching", rt.explain("https://example.com/y"))

    def test_decision_returns_the_rule(self):
        rt = build("User-agent: *\nDisallow: /private/")
        allowed, rule = rt.decision("https://example.com/private/x")
        self.assertFalse(allowed)
        self.assertEqual(rule.pattern, "/private/")


class TestMissingFile(unittest.TestCase):
    def test_absent_robots_allows_everything(self):
        rt = robots.RobotsTxt(url="https://example.com/robots.txt", found=False, status=404)
        self.assertTrue(rt.allows("https://example.com/anything"))
        self.assertIn("Not found", rt.summary())

    def test_unreadable_robots_allows_everything(self):
        rt = robots.RobotsTxt(url="https://example.com/robots.txt", error="timed out")
        self.assertTrue(rt.allows("https://example.com/anything"))
        self.assertIn("Could not be read", rt.summary())

    def test_robots_url_derived_from_any_page(self):
        self.assertEqual(
            robots.robots_url_for("https://example.com/deep/page?x=1"),
            "https://example.com/robots.txt",
        )


if __name__ == "__main__":
    unittest.main()
