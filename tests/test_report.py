"""Report renderer tests, including escaping of page-controlled content."""

import re
import unittest
from html.parser import HTMLParser

from audit.engine import audit_response
from audit.report import html as html_report
from audit.report import terminal as terminal_report
from tests.fixtures import CLEAN, HOSTILE, MESSY, response

VOID_ELEMENTS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr", "circle",
    }
)


class _BalanceChecker(HTMLParser):
    """Confirms every non-void element is closed in the right order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID_ELEMENTS:
            return
        if not self.stack:
            self.errors.append(f"</{tag}> with nothing open")
        elif self.stack[-1] != tag:
            self.errors.append(f"expected </{self.stack[-1]}>, got </{tag}>")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()


class TestHtmlReport(unittest.TestCase):
    def setUp(self):
        self.result = audit_response(response(MESSY), "https://acme.test/")
        self.html = html_report.render(self.result)

    def test_is_well_formed(self):
        checker = _BalanceChecker()
        checker.feed(self.html)
        self.assertEqual(checker.errors, [])
        self.assertEqual(checker.stack, [])

    def test_is_self_contained(self):
        """No external CSS, fonts, scripts, or images — the file must render offline."""
        referenced = re.findall(r'(?:src|href)\s*=\s*"(https?://[^"]+)"', self.html)
        external = [url for url in referenced if not url.startswith("https://acme.test")]
        self.assertEqual(external, [], f"external resources referenced: {external}")
        self.assertEqual(self.html.count("<style>"), 1)

    def test_contains_no_script_tags(self):
        self.assertEqual(re.findall(r"<script", self.html, re.I), [])

    def test_renders_every_finding(self):
        for finding in self.result.findings:
            with self.subTest(rule=finding.rule):
                self.assertIn(finding.rule, self.html)

    def test_supports_both_colour_schemes(self):
        self.assertIn("prefers-color-scheme: dark", self.html)

    def test_clean_page_renders_clean_state(self):
        clean = audit_response(response(CLEAN), "https://acme.test/")
        markup = html_report.render(clean)
        self.assertIn("Clean.", markup)


class TestHtmlEscaping(unittest.TestCase):
    """The report embeds page-controlled text (titles, alt text, link text, URLs).

    If any of it were interpolated raw, opening a report for a hostile page would run
    that page's script in the reviewer's browser.
    """

    def setUp(self):
        self.result = audit_response(response(HOSTILE, url="https://evil.test/"), "https://evil.test/")
        self.html = html_report.render(self.result)

    def test_no_live_script_element(self):
        self.assertEqual(re.findall(r"<script", self.html, re.I), [])

    def test_no_event_handler_attribute(self):
        self.assertNotIn("onerror=", self.html)

    def test_payload_appears_escaped_not_live(self):
        checker = _BalanceChecker()
        checker.feed(self.html)
        self.assertEqual(checker.errors, [], "injected markup broke the document structure")


class TestScoreRing(unittest.TestCase):
    def _offset(self, score):
        match = re.search(r'stroke-dashoffset="([\d.-]+)"', html_report._ring(score))
        return float(match.group(1))

    def test_zero_leaves_ring_empty(self):
        self.assertAlmostEqual(self._offset(0.0), html_report._RING_CIRCUMFERENCE, places=2)

    def test_full_score_closes_the_ring(self):
        self.assertAlmostEqual(self._offset(100.0), 0.0, places=2)

    def test_half_score_is_half_the_ring(self):
        self.assertAlmostEqual(self._offset(50.0), html_report._RING_CIRCUMFERENCE / 2, places=2)

    def test_out_of_range_scores_are_clamped(self):
        self.assertAlmostEqual(self._offset(150.0), 0.0, places=2)
        self.assertAlmostEqual(self._offset(-20.0), html_report._RING_CIRCUMFERENCE, places=2)


class TestTerminalReport(unittest.TestCase):
    def setUp(self):
        self.result = audit_response(response(MESSY), "https://acme.test/")

    def test_plain_output_has_no_ansi_codes(self):
        text = terminal_report.render(self.result, color=False)
        self.assertNotIn("\033[", text)

    def test_colour_output_has_ansi_codes(self):
        text = terminal_report.render(self.result, color=True)
        self.assertIn("\033[", text)

    def test_includes_scores_and_scope_disclaimer(self):
        text = terminal_report.render(self.result, color=False)
        self.assertIn("OVERALL", text)
        self.assertIn("Static HTML analysis only", text)

    def test_long_text_is_wrapped(self):
        text = terminal_report.render(self.result, color=False)
        overlong = [line for line in text.splitlines() if len(line) > terminal_report.WIDTH + 2]
        self.assertEqual(overlong, [], f"unwrapped lines: {overlong[:3]}")


if __name__ == "__main__":
    unittest.main()
