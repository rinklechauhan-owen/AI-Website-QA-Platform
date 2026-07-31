"""Inventory tests: content listing, structure outline, image alt states, schema.org output."""

import json
import unittest

from audit.inventory import (
    build,
    content_inventory,
    image_alt_inventory,
    structure_outline,
    suggest_schema,
)
from audit.parse import parse

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>Pricing | Acme Ltd</title>
  <meta name="description" content="Acme pricing plans and what each tier includes.">
  <meta property="og:image" content="https://acme.test/og.png">
  <link rel="canonical" href="https://acme.test/plans/pricing">
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Acme"}</script>
</head>
<body>
  <header><img src="/img/acme-logo.svg" alt="Acme logo"></header>
  <main>
    <h1>Pricing</h1>
    <p>Simple plans that scale with your team.
    <p>No setup fees, cancel any time.
    <section id="faq" class="faq wide">
      <h2>How does billing work?</h2>
      <p>You are billed monthly in arrears.</p>
      <h2>Can I change plan later?</h2>
      <p>Yes, at any point from the dashboard.</p>
      <h3>Deep detail</h3>
      <p>Prorated automatically.</p>
    </section>
    <img src="/img/chart.png">
    <img src="/img/divider.png" alt="">
    <img src="/img/team.jpg" alt="The Acme team">
  </main>
</body></html>"""

URL = "https://acme.test/plans/pricing"


class TestContentInventory(unittest.TestCase):
    def setUp(self):
        self.doc = parse(PAGE, URL)

    def test_lists_requested_tags_in_document_order(self):
        inventory = content_inventory(self.doc, ("h2", "h3", "p"))
        self.assertEqual(
            [block.tag for block in inventory.blocks],
            ["p", "p", "h2", "p", "h2", "p", "h3", "p"],
        )

    def test_unclosed_paragraphs_are_separate_blocks(self):
        """<p>a<p>b is valid HTML; the two must not merge into one block."""
        texts = [b.text for b in content_inventory(self.doc, ("p",)).blocks]
        self.assertIn("Simple plans that scale with your team.", texts)
        self.assertIn("No setup fees, cancel any time.", texts)

    def test_counts_and_word_total(self):
        inventory = content_inventory(self.doc, ("h2", "h3", "p"))
        self.assertEqual(inventory.counts, {"h2": 2, "h3": 1, "p": 5})
        self.assertGreater(inventory.total_words, 20)

    def test_tag_selection_is_respected(self):
        inventory = content_inventory(self.doc, ("h1",))
        self.assertEqual([b.text for b in inventory.blocks], ["Pricing"])

    def test_empty_blocks_are_excluded(self):
        doc = parse("<html><p></p><p>   </p><p>real</p></html>", URL)
        self.assertEqual([b.text for b in content_inventory(doc, ("p",)).blocks], ["real"])


class TestStructureOutline(unittest.TestCase):
    def setUp(self):
        self.doc = parse(PAGE, URL)
        self.outline = structure_outline(self.doc)

    def test_captures_nesting_depth(self):
        by_tag = {row.tag: row.depth for row in self.outline.rows}
        self.assertLess(by_tag["html"], by_tag["body"])
        self.assertLess(by_tag["body"], by_tag["main"])
        self.assertLess(by_tag["main"], by_tag["section"])

    def test_selector_includes_id_and_classes(self):
        section = next(row for row in self.outline.rows if row.tag == "section")
        self.assertEqual(section.selector, "section#faq.faq.wide")

    def test_inline_formatting_is_excluded(self):
        doc = parse("<html><body><p>a <em>b</em> <strong>c</strong></p></body></html>", URL)
        tags = {row.tag for row in structure_outline(doc).rows}
        self.assertNotIn("em", tags)
        self.assertNotIn("strong", tags)

    def test_unclosed_paragraph_does_not_nest_siblings(self):
        """An unclosed <p> must not swallow everything after it in the outline."""
        doc = parse("<html><body><p>one<div id=after>x</div></body></html>", URL)
        rows = {row.tag: row.depth for row in structure_outline(doc).rows}
        self.assertEqual(rows["p"], rows["div"])

    def test_depth_cap_truncates_and_reports(self):
        deep = "<html><body>" + "<div>" * 20 + "x" + "</div>" * 20 + "</body></html>"
        outline = structure_outline(parse(deep, URL), max_depth=4)
        self.assertTrue(outline.was_truncated)
        self.assertGreater(outline.truncated_depth, 0)
        self.assertTrue(all(row.depth <= 4 for row in outline.rows))

    def test_node_cap_truncates_and_reports(self):
        wide = "<html><body>" + "<div>x</div>" * 50 + "</body></html>"
        outline = structure_outline(parse(wide, URL), max_nodes=10)
        self.assertLessEqual(len(outline.rows), 10)
        self.assertGreater(outline.truncated_count, 0)

    def test_empty_document(self):
        outline = structure_outline(parse("", URL))
        self.assertEqual(outline.rows, [])
        self.assertFalse(outline.was_truncated)


class TestImageAltInventory(unittest.TestCase):
    def setUp(self):
        self.inventory = image_alt_inventory(parse(PAGE, URL))

    def test_missing_alt_sources(self):
        self.assertEqual(
            [i.src for i in self.inventory.missing], ["https://acme.test/img/chart.png"]
        )

    def test_empty_alt_sources(self):
        self.assertEqual(
            [i.src for i in self.inventory.empty], ["https://acme.test/img/divider.png"]
        )

    def test_described_images(self):
        self.assertEqual(len(self.inventory.present), 2)

    def test_needs_attention_combines_missing_and_empty(self):
        self.assertEqual(len(self.inventory.needs_attention), 2)

    def test_whitespace_only_alt_counts_as_empty(self):
        doc = parse('<html><img src="a.png" alt="   "></html>', URL)
        self.assertEqual(len(image_alt_inventory(doc).empty), 1)

    def test_coverage_percentage(self):
        self.assertEqual(self.inventory.coverage, 50.0)

    def test_page_with_no_images_is_fully_covered(self):
        self.assertEqual(image_alt_inventory(parse("<html></html>", URL)).coverage, 100.0)


class TestSchemaSuggestion(unittest.TestCase):
    def setUp(self):
        self.schema = suggest_schema(parse(PAGE, URL))
        self.graph = {item["@type"]: item for item in self.schema.generated["@graph"]}

    def test_detects_structured_data_already_present(self):
        self.assertEqual(self.schema.existing_types, ["Organization"])

    def test_warns_about_duplicating_existing_types(self):
        self.assertTrue(any("merge rather than duplicate" in n for n in self.schema.notes))

    def test_organization_name_from_title_suffix(self):
        self.assertEqual(self.graph["Organization"]["name"], "Acme Ltd")

    def test_logo_detected_from_image_source(self):
        self.assertTrue(self.graph["Organization"]["logo"]["url"].endswith("acme-logo.svg"))

    def test_webpage_uses_canonical_and_language(self):
        self.assertEqual(self.graph["WebPage"]["url"], URL)
        self.assertEqual(self.graph["WebPage"]["inLanguage"], "en")

    def test_breadcrumbs_derived_from_path(self):
        names = [i["name"] for i in self.graph["BreadcrumbList"]["itemListElement"]]
        self.assertEqual(names, ["Home", "Plans", "Pricing"])

    def test_faq_pairs_questions_with_following_paragraph(self):
        entries = self.graph["FAQPage"]["mainEntity"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["name"], "How does billing work?")
        self.assertEqual(entries[0]["acceptedAnswer"]["text"], "You are billed monthly in arrears.")

    def test_no_faq_when_fewer_than_two_questions(self):
        doc = parse("<html><h2>Only one?</h2><p>Yes.</p></html>", URL)
        types = [i["@type"] for i in suggest_schema(doc).generated["@graph"]]
        self.assertNotIn("FAQPage", types)

    def test_article_not_claimed_for_a_thin_page(self):
        doc = parse("<html lang=en><h1>Hi</h1><p>Short.</p></html>", URL)
        types = [i["@type"] for i in suggest_schema(doc).generated["@graph"]]
        self.assertNotIn("Article", types)

    def test_article_claimed_when_article_element_present(self):
        doc = parse("<html lang=en><article><h1>Story</h1><p>Body.</p></article></html>", URL)
        types = [i["@type"] for i in suggest_schema(doc).generated["@graph"]]
        self.assertIn("Article", types)

    def test_missing_description_is_omitted_not_invented(self):
        doc = parse("<html lang=en><title>T</title><h1>x</h1></html>", URL)
        schema = suggest_schema(doc)
        page = next(i for i in schema.generated["@graph"] if i["@type"] == "WebPage")
        self.assertNotIn("description", page)
        self.assertTrue(any("no meta description" in n for n in schema.notes))

    def test_output_is_valid_json(self):
        json.loads(self.schema.json_ld)

    def test_script_block_is_pasteable(self):
        self.assertTrue(self.schema.script_block.startswith('<script type="application/ld+json">'))
        self.assertTrue(self.schema.script_block.rstrip().endswith("</script>"))

    def test_unparseable_existing_jsonld_is_reported(self):
        doc = parse(
            '<html><script type="application/ld+json">{not json}</script></html>', URL
        )
        self.assertIn("(unparseable)", suggest_schema(doc).existing_types)


class TestCombinedInventory(unittest.TestCase):
    def test_build_returns_all_four_extracts(self):
        inventory = build(parse(PAGE, URL))
        self.assertTrue(inventory.content.blocks)
        self.assertTrue(inventory.outline.rows)
        self.assertTrue(inventory.images.needs_attention)
        self.assertTrue(inventory.schema.suggested_types)

    def test_serialises_to_json(self):
        json.dumps(build(parse(PAGE, URL)).to_dict())


if __name__ == "__main__":
    unittest.main()
