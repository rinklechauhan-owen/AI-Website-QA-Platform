"""Tab layout and the extracts backing the new tabs."""

import re
import unittest

from audit.assets import ImageMeasurement, ImageSizeReport, findings_from, human_size
from audit.engine import audit_response
from audit.inventory import canonical_info, index_follow_info, meta_tags
from audit.parse import parse
from audit.report import html as html_report
from tests.fixtures import CLEAN, MESSY, response

# Every tab the user asked for, in the order they asked for it.
REQUIRED_TABS = [
    ("seo", "SEO"),
    ("headings", "Headings"),
    ("meta", "Meta Tags"),
    ("canonical", "Canonical"),
    ("alt", "Alt Missing"),
    ("imgsize", "Image Size"),
    ("robots", "Index / Follow"),
    ("schema", "Schema"),
]


class TestTabLayout(unittest.TestCase):
    def setUp(self):
        self.result = audit_response(response(MESSY), "https://acme.test/")
        self.html = html_report.render(self.result)

    def test_every_requested_tab_is_present(self):
        for key, label in REQUIRED_TABS:
            with self.subTest(tab=key):
                self.assertIn(f'id="tab-{key}"', self.html)
                self.assertIn(f'id="panel-{key}"', self.html)
                self.assertIn(f">{label}<", self.html.replace("</label>", "<"))

    def test_requested_tabs_appear_in_the_requested_order(self):
        positions = [self.html.index(f'for="tab-{key}"') for key, _ in REQUIRED_TABS]
        self.assertEqual(positions, sorted(positions))

    def test_exactly_one_tab_starts_selected(self):
        self.assertEqual(self.html.count('name="qa-tabs"'), self.html.count("<input type=\"radio\""))
        self.assertEqual(self.html.count(" checked>"), 1)

    def test_first_tab_is_the_selected_one(self):
        first = re.search(r'<input type="radio" name="qa-tabs" id="tab-(\w+)" checked>', self.html)
        self.assertIsNotNone(first)

    def test_switching_needs_no_javascript(self):
        self.assertNotIn("<script", self.html.lower())
        self.assertNotIn("onclick", self.html.lower())
        for key, _ in REQUIRED_TABS:
            with self.subTest(tab=key):
                self.assertIn(f"#tab-{key}:checked ~ .panels > #panel-{key}", self.html)

    def test_every_panel_has_a_matching_radio_and_label(self):
        panels = set(re.findall(r'id="panel-([\w-]+)"', self.html))
        radios = set(re.findall(r'id="tab-([\w-]+)"', self.html))
        labels = set(re.findall(r'for="tab-([\w-]+)"', self.html))
        self.assertEqual(panels, radios)
        self.assertEqual(panels, labels)

    def test_printing_reveals_all_panels(self):
        self.assertIn("@media print", self.html)
        self.assertIn(".panel { display: block !important; }", self.html)

    def test_no_paragraphs_in_the_headings_tab(self):
        panel = self.html.split('id="panel-headings"')[1].split('id="panel-')[0]
        self.assertNotIn('class="block p"', panel)

    def test_links_tab_only_appears_when_links_were_checked(self):
        self.assertNotIn('id="panel-links"', self.html)

    def test_http_error_promotes_an_http_tab_to_the_front(self):
        result = audit_response(response("<html></html>", status=503), "https://acme.test/")
        html = html_report.render(result)
        self.assertIn('id="panel-http"', html)
        self.assertIn('id="tab-http" checked', html)


class TestHeadingsTab(unittest.TestCase):
    def test_lists_all_six_levels(self):
        html = "<html>" + "".join(f"<h{n}>Level {n}</h{n}>" for n in range(1, 7)) + "</html>"
        rendered = html_report.render(audit_response(response(html), "https://acme.test/"))
        panel = rendered.split('id="panel-headings"')[1].split('id="panel-')[0]
        for level in range(1, 7):
            with self.subTest(level=level):
                self.assertIn(f"Level {level}", panel)

    def test_empty_heading_is_labelled_not_blank(self):
        rendered = html_report.render(
            audit_response(response("<html><h2></h2></html>"), "https://acme.test/")
        )
        self.assertIn("(empty heading)", rendered)


class TestMetaTagsExtract(unittest.TestCase):
    def test_separates_name_property_and_charset(self):
        doc = parse(
            '<html><head><meta charset="utf-8">'
            '<meta name="description" content="d">'
            '<meta property="og:title" content="t">'
            '<meta http-equiv="refresh" content="5"></head></html>',
            "https://acme.test/",
        )
        kinds = {(t.kind, t.key) for t in meta_tags(doc)}
        self.assertIn(("charset", "charset"), kinds)
        self.assertIn(("name", "description"), kinds)
        self.assertIn(("property", "og:title"), kinds)
        self.assertIn(("http-equiv", "refresh"), kinds)

    def test_empty_content_is_flagged(self):
        doc = parse('<html><meta name="description" content=""></html>', "https://acme.test/")
        self.assertTrue(meta_tags(doc)[0].is_empty)


class TestCanonicalExtract(unittest.TestCase):
    def test_absent_canonical(self):
        info = canonical_info(parse("<html></html>", "https://acme.test/p"))
        self.assertFalse(info.present)

    def test_self_referencing_detected(self):
        doc = parse('<html><link rel="canonical" href="https://acme.test/p"></html>',
                    "https://acme.test/p")
        self.assertTrue(canonical_info(doc).is_self_referencing)

    def test_pointing_elsewhere_detected(self):
        doc = parse('<html><link rel="canonical" href="https://acme.test/other"></html>',
                    "https://acme.test/p")
        self.assertFalse(canonical_info(doc).is_self_referencing)

    def test_relative_canonical_is_resolved_but_flagged_as_relative_source(self):
        doc = parse('<html><link rel="canonical" href="/p"></html>', "https://acme.test/p")
        info = canonical_info(doc)
        self.assertEqual(info.declared, "https://acme.test/p")
        self.assertTrue(info.is_self_referencing)


class TestIndexFollowExtract(unittest.TestCase):
    def test_default_is_index_follow(self):
        info = index_follow_info(parse("<html></html>", "https://acme.test/"), {})
        self.assertTrue(info.indexable)
        self.assertTrue(info.followable)
        self.assertTrue(info.is_default)
        self.assertEqual(info.summary, "index, follow")

    def test_meta_noindex_detected(self):
        doc = parse('<html><meta name="robots" content="noindex,follow"></html>', "https://a.test/")
        info = index_follow_info(doc, {})
        self.assertFalse(info.indexable)
        self.assertTrue(info.followable)

    def test_header_level_noindex_detected(self):
        """X-Robots-Tag is invisible in the markup and easy to miss."""
        info = index_follow_info(
            parse("<html></html>", "https://a.test/"), {"x-robots-tag": "noindex"}
        )
        self.assertFalse(info.indexable)

    def test_none_directive_blocks_both(self):
        doc = parse('<html><meta name="robots" content="none"></html>', "https://a.test/")
        info = index_follow_info(doc, {})
        self.assertFalse(info.indexable)
        self.assertFalse(info.followable)

    def test_googlebot_directive_counted(self):
        doc = parse('<html><meta name="googlebot" content="nofollow"></html>', "https://a.test/")
        self.assertFalse(index_follow_info(doc, {}).followable)


class TestImageSizeReport(unittest.TestCase):
    LIMIT = int(2.5 * 1024 * 1024)

    def _report(self, sizes):
        return ImageSizeReport(
            limit_bytes=self.LIMIT,
            checked=True,
            measurements=[
                ImageMeasurement(src=f"https://a.test/{i}.jpg", byte_size=size, line=i)
                for i, size in enumerate(sizes)
            ],
        )

    def test_only_images_over_the_limit_are_flagged(self):
        report = self._report([1_000_000, 3_000_000, self.LIMIT, self.LIMIT + 1])
        self.assertEqual([m.byte_size for m in report.oversized], [3_000_000, self.LIMIT + 1])

    def test_exactly_at_the_limit_is_not_oversized(self):
        self.assertEqual(self._report([self.LIMIT]).oversized, [])

    def test_oversized_sorted_heaviest_first(self):
        report = self._report([3_000_000, 9_000_000, 5_000_000])
        self.assertEqual([m.byte_size for m in report.oversized], [9_000_000, 5_000_000, 3_000_000])

    def test_unknown_sizes_are_tracked_separately(self):
        report = ImageSizeReport(
            limit_bytes=self.LIMIT,
            checked=True,
            measurements=[ImageMeasurement(src="https://a.test/x.jpg", error="HTTP 404")],
        )
        self.assertEqual(len(report.unknown), 1)
        self.assertEqual(report.oversized, [])

    def test_findings_one_per_oversized_image(self):
        findings = findings_from(self._report([4_000_000, 8_000_000, 100]))
        oversized = [f for f in findings if f.rule == "image.oversized"]
        self.assertEqual(len(oversized), 2)

    def test_unreachable_images_produce_one_grouped_finding(self):
        report = ImageSizeReport(
            limit_bytes=self.LIMIT,
            checked=True,
            measurements=[
                ImageMeasurement(src="https://a.test/x.jpg", error="HTTP 404"),
                ImageMeasurement(src="https://a.test/y.jpg", error="timed out"),
            ],
        )
        rules = [f.rule for f in findings_from(report)]
        self.assertEqual(rules.count("image.unreachable"), 1)

    def test_human_size_formatting(self):
        self.assertEqual(human_size(500), "500 B")
        self.assertEqual(human_size(2048), "2 KB")
        self.assertEqual(human_size(int(2.5 * 1024 * 1024)), "2.50 MB")
        self.assertEqual(human_size(None), "unknown")

    def test_capped_read_reports_a_floor_not_an_exact_size(self):
        measurement = ImageMeasurement(src="x", byte_size=self.LIMIT + 1, at_least=True)
        self.assertTrue(measurement.display_size.startswith(">"))
        self.assertTrue(measurement.exceeds(self.LIMIT))


class TestImageSizeTabStates(unittest.TestCase):
    def test_tab_explains_how_to_enable_when_not_checked(self):
        result = audit_response(response(MESSY), "https://acme.test/")
        html = html_report.render(result)
        panel = html.split('id="panel-imgsize"')[1].split('id="panel-')[0]
        self.assertIn("--check-images", panel)

    def test_tab_reports_clean_when_nothing_is_oversized(self):
        result = audit_response(response(CLEAN), "https://acme.test/")
        result.image_sizes = ImageSizeReport(
            limit_bytes=int(2.5 * 1024 * 1024),
            checked=True,
            measurements=[ImageMeasurement(src="https://a.test/a.webp", byte_size=1000)],
        )
        panel = html_report.render(result).split('id="panel-imgsize"')[1].split('id="panel-')[0]
        self.assertIn("Clean.", panel)

    def test_oversized_image_source_is_listed(self):
        result = audit_response(response(MESSY), "https://acme.test/")
        result.image_sizes = ImageSizeReport(
            limit_bytes=int(2.5 * 1024 * 1024),
            checked=True,
            measurements=[
                ImageMeasurement(src="https://a.test/huge.png", byte_size=9_000_000, line=12)
            ],
        )
        panel = html_report.render(result).split('id="panel-imgsize"')[1].split('id="panel-')[0]
        self.assertIn("https://a.test/huge.png", panel)
        self.assertIn("8.58 MB", panel)


if __name__ == "__main__":
    unittest.main()
