"""Rule pack tests — the messy fixture should trip rules, the clean one should not."""

import unittest

from audit.engine import audit_response
from audit.findings import Severity, score_from_findings
from audit.parse import parse
from audit.rules import images, seo
from tests.fixtures import CLEAN, MESSY, response


def rules_for(html, url="https://acme.test/"):
    return {finding.rule for finding in audit_response(response(html, url), url).findings}


class TestSeoRules(unittest.TestCase):
    def setUp(self):
        self.messy = rules_for(MESSY)
        self.clean = rules_for(CLEAN)

    def test_noindex_is_critical(self):
        doc = parse(MESSY, "https://acme.test/")
        findings, _ = seo.run(doc)
        noindex = [f for f in findings if f.rule == "seo.noindex"]
        self.assertEqual(len(noindex), 1)
        self.assertEqual(noindex[0].severity, Severity.CRITICAL)

    def test_messy_page_trips_expected_seo_rules(self):
        for rule in (
            "seo.noindex",
            "seo.nofollow-page",
            "seo.missing-h1",
            "seo.missing-meta-description",
            "seo.missing-canonical",
            "seo.missing-viewport",
            "seo.missing-lang",
            "seo.title-too-short",
            "seo.thin-content",
            "seo.heading-level-skip",
            "seo.empty-heading",
            "seo.non-descriptive-link-text",
            "seo.no-structured-data",
            "seo.missing-open-graph",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.messy)

    def test_clean_page_trips_no_seo_rules(self):
        offenders = {rule for rule in self.clean if rule.startswith("seo.")}
        self.assertEqual(offenders, set())

    def test_heading_skip_detects_h2_to_h5(self):
        doc = parse(MESSY, "https://acme.test/")
        findings, _ = seo.run(doc)
        skip = [f for f in findings if f.rule == "seo.heading-level-skip"]
        self.assertTrue(any("H2 to H5" in f.title for f in skip), [f.title for f in skip])

    def test_consecutive_heading_levels_are_not_flagged(self):
        doc = parse("<html lang=en><h1>a</h1><h2>b</h2><h3>c</h3></html>", "https://acme.test/")
        findings, _ = seo.run(doc)
        self.assertNotIn("seo.heading-level-skip", {f.rule for f in findings})

    def test_stats_reported(self):
        doc = parse(CLEAN, "https://acme.test/")
        _, stats = seo.run(doc)
        self.assertEqual(stats["h1_count"], 1)
        self.assertEqual(stats["structured_data_blocks"], 1)
        self.assertGreater(stats["text_length"], 300)


class TestImageRules(unittest.TestCase):
    def setUp(self):
        self.messy = rules_for(MESSY)
        self.clean = rules_for(CLEAN)

    def test_messy_page_trips_expected_image_rules(self):
        for rule in (
            "image.missing-alt",
            "image.generic-alt",
            "image.empty-alt",
            "image.alt-too-long",
            "image.duplicate-src",
            "image.no-dimensions",
            "image.legacy-format",
            "image.no-lazy-loading",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.messy)

    def test_clean_page_trips_no_image_rules(self):
        offenders = {rule for rule in self.clean if rule.startswith("image.")}
        self.assertEqual(offenders, set())

    def test_one_finding_per_image_missing_alt(self):
        doc = parse(MESSY, "https://acme.test/")
        findings, _ = images.run(doc)
        missing = [f for f in findings if f.rule == "image.missing-alt"]
        self.assertEqual(len(missing), 2, "both alt-less images should be reported individually")

    def test_missing_alt_is_high_but_empty_alt_is_info(self):
        doc = parse(MESSY, "https://acme.test/")
        findings, _ = images.run(doc)
        by_rule = {f.rule: f for f in findings}
        self.assertEqual(by_rule["image.missing-alt"].severity, Severity.HIGH)
        # alt="" is legitimate for decorative images, so it must not be punished.
        self.assertEqual(by_rule["image.empty-alt"].severity, Severity.INFO)

    def test_first_images_are_not_expected_to_lazy_load(self):
        doc = parse(
            '<html><img src="a.webp" alt="a"><img src="b.webp" alt="b"></html>',
            "https://acme.test/",
        )
        findings, _ = images.run(doc)
        self.assertNotIn("image.no-lazy-loading", {f.rule for f in findings})

    def test_picture_source_suppresses_legacy_format_warning(self):
        html = '<html><picture><source srcset="a.avif"><img src="a.png" alt="a"></picture></html>'
        doc = parse(html, "https://acme.test/")
        findings, _ = images.run(doc)
        self.assertNotIn("image.legacy-format", {f.rule for f in findings})

    def test_page_without_images_produces_no_image_findings(self):
        doc = parse("<html lang=en><h1>Text only</h1></html>", "https://acme.test/")
        findings, stats = images.run(doc)
        self.assertEqual(findings, [])
        self.assertEqual(stats["total_images"], 0)


class TestScoring(unittest.TestCase):
    def test_info_findings_do_not_reduce_score(self):
        doc = parse('<html lang=en><img src="a.webp" alt=""></html>', "https://acme.test/")
        findings, _ = images.run(doc)
        info_only = [f for f in findings if f.severity == Severity.INFO]
        self.assertEqual(score_from_findings(info_only), 100.0)

    def test_score_floors_at_zero(self):
        doc = parse(MESSY, "https://acme.test/")
        findings, _ = seo.run(doc)
        self.assertGreaterEqual(score_from_findings(findings), 0.0)

    def test_clean_page_scores_full_marks(self):
        result = audit_response(response(CLEAN), "https://acme.test/")
        self.assertEqual(result.overall_score, 100.0)

    def test_messy_page_scores_poorly(self):
        result = audit_response(response(MESSY), "https://acme.test/")
        self.assertLess(result.overall_score, 50.0)

    def test_findings_sorted_most_severe_first(self):
        result = audit_response(response(MESSY), "https://acme.test/")
        severities = [f.severity for f in result.findings]
        self.assertEqual(severities[0], Severity.CRITICAL)
        self.assertEqual(severities[-1], Severity.INFO)


class TestHttpLevelHandling(unittest.TestCase):
    def test_error_status_short_circuits_the_audit(self):
        result = audit_response(response("<html></html>", status=404), "https://acme.test/")
        self.assertEqual([p.module for p in result.packs], ["http"])
        self.assertEqual(result.findings[0].rule, "http.error-status")
        self.assertEqual(result.overall_score, 0.0)

    def test_non_html_response_short_circuits_the_audit(self):
        resp = response("{}", headers={"content-type": "application/json"})
        result = audit_response(resp, "https://acme.test/")
        self.assertEqual(result.findings[0].rule, "http.not-html")

    def test_redirect_is_detected(self):
        resp = response(CLEAN, url="https://acme.test/home")
        result = audit_response(resp, "https://acme.test/start")
        self.assertTrue(result.was_redirected)

    def test_result_is_json_serialisable(self):
        import json

        result = audit_response(response(MESSY), "https://acme.test/")
        json.dumps(result.to_dict())


if __name__ == "__main__":
    unittest.main()
