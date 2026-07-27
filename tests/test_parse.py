"""Parser tests — the document model everything else is built on."""

import unittest

from audit.parse import parse
from tests.fixtures import TRICKY


class TestDocumentParsing(unittest.TestCase):
    def setUp(self):
        self.doc = parse(TRICKY, "https://acme.test/page")

    def test_title_is_collapsed_and_unescaped(self):
        self.assertEqual(self.doc.title, "Acme Widgets & Gears")

    def test_lang_attribute(self):
        self.assertEqual(self.doc.lang, "en-GB")

    def test_canonical_resolved_to_absolute(self):
        self.assertEqual(self.doc.canonical, "https://acme.test/home")

    def test_meta_lookup_is_case_insensitive(self):
        self.assertEqual(self.doc.meta("DESCRIPTION"), "We sell widgets.")

    def test_open_graph_uses_property_not_name(self):
        self.assertEqual(self.doc.meta_property("og:title"), "Acme")
        self.assertIsNone(self.doc.meta("og:title"))

    def test_jsonld_captured(self):
        self.assertEqual(len(self.doc.jsonld_blocks), 1)
        self.assertIn("Organization", self.doc.jsonld_blocks[0])

    def test_heading_levels_in_document_order(self):
        self.assertEqual([h.level for h in self.doc.headings], [1, 2, 4])

    def test_nested_inline_markup_in_heading(self):
        self.assertEqual(self.doc.headings[0].text, "Main Heading")

    def test_heading_wrapping_a_link_keeps_its_text(self):
        # Regression: capturing only the innermost frame left the heading empty.
        self.assertEqual(self.doc.headings[1].text, "Products")

    def test_script_content_is_not_parsed_as_markup(self):
        self.assertNotIn("not a heading", [h.text for h in self.doc.headings])

    def test_alt_states_are_distinguishable(self):
        alts = [img.alt for img in self.doc.images]
        self.assertEqual(alts[0], "Hero banner")
        self.assertIsNone(alts[1], "a missing alt attribute must be None")
        self.assertEqual(alts[2], "", 'an explicit alt="" must be the empty string')

    def test_image_src_resolved_against_base(self):
        self.assertEqual(self.doc.images[1].src, "https://acme.test/img/a.jpg")

    def test_picture_sources_collected(self):
        self.assertEqual(self.doc.picture_sources, ["d.avif"])

    def test_fragment_and_scheme_links_excluded(self):
        self.assertEqual(len(self.doc.links), 3)
        self.assertNotIn("#skip", [link.href for link in self.doc.links])

    def test_internal_and_external_link_split(self):
        self.assertEqual(len(self.doc.internal_links()), 2)
        self.assertEqual(len(self.doc.external_links()), 1)

    def test_rel_attribute_preserved(self):
        about = [link for link in self.doc.links if link.href.endswith("/about")][0]
        self.assertEqual(about.rel, "nofollow")


class TestParserResilience(unittest.TestCase):
    def test_empty_document(self):
        doc = parse("", "https://acme.test/")
        self.assertIsNone(doc.title)
        self.assertEqual(doc.images, [])

    def test_unclosed_tags_do_not_raise(self):
        doc = parse("<html><body><h1>Open<img src=x.png><a href=/y>text", "https://acme.test/")
        self.assertEqual(len(doc.images), 1)

    def test_mismatched_close_tags_do_not_raise(self):
        doc = parse("<h1>a</h2></div></h1>", "https://acme.test/")
        self.assertIsInstance(doc.headings, list)

    def test_plain_text_input(self):
        doc = parse("just some text, no tags at all", "https://acme.test/")
        self.assertGreater(doc.text_length, 0)


if __name__ == "__main__":
    unittest.main()
