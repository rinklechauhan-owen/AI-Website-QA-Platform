"""Schema generator: content in, JSON-LD out."""

import json
import unittest

from audit.schemagen import SCHEMA_TYPES, generate, looks_like_html, split_fields


class TestInputParsing(unittest.TestCase):
    def test_html_is_recognised(self):
        self.assertTrue(looks_like_html("<p>hello</p>"))
        self.assertTrue(looks_like_html("  <!DOCTYPE html><html>"))

    def test_plain_text_is_not_html(self):
        self.assertFalse(looks_like_html("Name: Acme\nPrice: 10"))
        self.assertFalse(looks_like_html("2 < 3 and 5 > 4"))

    def test_key_value_lines_become_fields(self):
        fields, prose = split_fields("Name: Acme\nPrice: 10\nJust some prose here.")
        self.assertEqual(fields["name"], "Acme")
        self.assertEqual(fields["price"], "10")
        self.assertEqual(prose, ["Just some prose here."])

    def test_prose_containing_a_colon_is_not_treated_as_a_field(self):
        """A long lead-in before the colon is a sentence, not metadata."""
        _, prose = split_fields(
            "There is one thing every buyer asks about first: how long delivery takes."
        )
        self.assertEqual(len(prose), 1)


class TestFaqGeneration(unittest.TestCase):
    def test_question_answer_pairs_from_plain_text(self):
        result = generate(
            "How long does delivery take?\nTwo to three working days.\n"
            "Can I return an item?\nYes, within 30 days.",
        )
        self.assertEqual(result.schema_type, "FAQPage")
        entities = result.data["mainEntity"]
        self.assertEqual(len(entities), 2)
        self.assertEqual(entities[0]["name"], "How long does delivery take?")
        self.assertEqual(entities[0]["acceptedAnswer"]["text"], "Two to three working days.")

    def test_pairs_from_html_headings(self):
        result = generate(
            "<h2>Is it waterproof?</h2><p>Yes, rated IP67.</p>"
            "<h2>What is the warranty?</h2><p>Five years.</p>",
            "FAQPage",
        )
        self.assertEqual(len(result.data["mainEntity"]), 2)

    def test_single_pair_still_generates_but_warns(self):
        result = generate("Is it good?\nYes.", "FAQPage")
        self.assertTrue(result.ok)
        self.assertTrue(any("several" in note for note in result.notes))

    def test_no_pairs_produces_a_warning_not_empty_markup(self):
        result = generate("Just a sentence with no questions.", "FAQPage")
        self.assertFalse(result.ok)
        self.assertTrue(result.warnings)


class TestHowToGeneration(unittest.TestCase):
    SOURCE = (
        "Name: Replace an inner tube\nTime: PT20M\n"
        "1. Remove the wheel.\n2. Unseat the tyre.\n3. Fit the new tube."
    )

    def test_numbered_steps(self):
        result = generate(self.SOURCE, "HowTo")
        self.assertEqual(len(result.data["step"]), 3)
        self.assertEqual(result.data["step"][0]["position"], 1)
        self.assertEqual(result.data["totalTime"], "PT20M")

    def test_bulleted_steps_also_work(self):
        result = generate("Name: Brew tea\n- Boil water.\n- Add a bag.\n- Wait.", "HowTo")
        self.assertEqual(len(result.data["step"]), 3)

    def test_missing_duration_is_noted_not_invented(self):
        result = generate("Name: Do a thing\n1. Step one.\n2. Step two.", "HowTo")
        self.assertNotIn("totalTime", result.data)
        self.assertTrue(any("duration" in note for note in result.notes))


class TestProductGeneration(unittest.TestCase):
    def test_price_and_offer(self):
        result = generate(
            "Name: Desk Lamp\nPrice: £89.00\nCurrency: GBP\nBrand: Northgate\n"
            "SKU: NG-1\nAvailability: InStock",
            "Product",
        )
        self.assertEqual(result.data["name"], "Desk Lamp")
        self.assertEqual(result.data["offers"]["price"], "89.00")
        self.assertEqual(result.data["offers"]["priceCurrency"], "GBP")
        self.assertTrue(result.data["offers"]["availability"].endswith("InStock"))
        self.assertEqual(result.data["brand"]["name"], "Northgate")

    def test_currency_assumption_is_disclosed(self):
        result = generate("Name: Lamp\nPrice: 20", "Product")
        self.assertEqual(result.data["offers"]["priceCurrency"], "GBP")
        self.assertTrue(any("GBP was assumed" in note for note in result.notes))

    def test_missing_price_is_noted(self):
        result = generate("Name: Lamp", "Product")
        self.assertNotIn("offers", result.data)
        self.assertTrue(any("price" in note.lower() for note in result.notes))


class TestLocalBusinessGeneration(unittest.TestCase):
    def test_address_assembled_from_parts(self):
        result = generate(
            "Name: Northgate Studio\nStreet: 14 Bridge Street\nCity: Manchester\n"
            "Postcode: M3 3AB\nCountry: GB\nPhone: +44 161 000 0000",
            "LocalBusiness",
        )
        address = result.data["address"]
        self.assertEqual(address["streetAddress"], "14 Bridge Street")
        self.assertEqual(address["addressLocality"], "Manchester")
        self.assertEqual(address["postalCode"], "M3 3AB")
        self.assertEqual(result.data["telephone"], "+44 161 000 0000")

    def test_missing_address_blocks_output(self):
        """A LocalBusiness without an address is invalid, so nothing is emitted."""
        result = generate("Name: Northgate Studio", "LocalBusiness")
        self.assertTrue(any("address" in w for w in result.warnings))
        self.assertFalse(result.ok)


class TestBreadcrumbGeneration(unittest.TestCase):
    def test_trail_with_urls(self):
        result = generate("URL: https://acme.test\nHome > Services > Branding", "BreadcrumbList")
        items = result.data["itemListElement"]
        self.assertEqual([i["name"] for i in items], ["Home", "Services", "Branding"])
        self.assertEqual(items[0]["item"], "https://acme.test/")
        self.assertEqual(items[2]["item"], "https://acme.test/branding")

    def test_trail_without_a_base_url_omits_links_and_says_so(self):
        result = generate("Home / Blog / Post", "BreadcrumbList")
        self.assertNotIn("item", result.data["itemListElement"][0])
        self.assertTrue(any("URL" in note for note in result.notes))

    def test_single_level_is_rejected(self):
        self.assertFalse(generate("Home", "BreadcrumbList").ok)


class TestEventGeneration(unittest.TestCase):
    def test_start_date_and_location(self):
        result = generate(
            "Name: Launch Night\nStart: 2026-09-18T18:30\nLocation: Bridgewater Hall",
            "Event",
        )
        self.assertEqual(result.data["startDate"], "2026-09-18T18:30")
        self.assertEqual(result.data["location"]["name"], "Bridgewater Hall")

    def test_missing_start_date_blocks_output(self):
        """startDate is required, so incomplete Event markup must not be emitted at all."""
        result = generate("Name: Launch Night", "Event")
        self.assertTrue(any("start date" in w for w in result.warnings))
        self.assertFalse(result.ok)
        self.assertEqual(result.data, {})


class TestArticleGeneration(unittest.TestCase):
    def test_headline_and_author(self):
        result = generate(
            "Title: Why print is not dead\nAuthor: Sam Reed\nDate: 2026-04-01\n"
            "Print budgets fell for a decade and then stopped falling.",
            "Article",
        )
        self.assertEqual(result.data["headline"], "Why print is not dead")
        self.assertEqual(result.data["author"]["name"], "Sam Reed")
        self.assertEqual(result.data["datePublished"], "2026-04-01")

    def test_missing_author_and_date_are_noted_not_invented(self):
        result = generate("Title: A post\nSome body copy goes here.", "Article")
        self.assertNotIn("author", result.data)
        self.assertNotIn("datePublished", result.data)
        self.assertEqual(len(result.notes), 2)


class TestHtmlInput(unittest.TestCase):
    def test_html_produces_output(self):
        """Regression: HTML input yielded nothing because prose was left empty."""
        result = generate(
            "<article><h1>Why print is not dead</h1><p>Budgets stopped falling.</p></article>"
        )
        self.assertTrue(result.ok)

    def test_title_tag_is_used(self):
        result = generate("<html><head><title>Pricing</title></head><body>"
                          "<p>Plans and tiers.</p></body></html>", "WebPage")
        self.assertEqual(result.data["name"], "Pricing")


class TestAutoDetection(unittest.TestCase):
    def test_questions_detect_faq(self):
        self.assertEqual(generate("A?\nYes.\nB?\nNo.").schema_type, "FAQPage")

    def test_steps_detect_howto(self):
        self.assertEqual(generate("Make tea\n1. Boil.\n2. Steep.").schema_type, "HowTo")

    def test_price_detects_product(self):
        self.assertEqual(generate("Name: Lamp\nPrice: 20").schema_type, "Product")

    def test_address_detects_local_business(self):
        self.assertEqual(generate("Name: Cafe\nCity: Leeds").schema_type, "LocalBusiness")

    def test_short_content_falls_back_to_webpage(self):
        self.assertEqual(generate("Title: Contact\nGet in touch.").schema_type, "WebPage")

    def test_detection_is_reported_to_the_user(self):
        result = generate("A?\nYes.\nB?\nNo.")
        self.assertTrue(any("Detected" in note for note in result.notes))


class TestGuardsAndOutput(unittest.TestCase):
    def test_empty_input_warns(self):
        result = generate("   ")
        self.assertFalse(result.ok)
        self.assertTrue(result.warnings)

    def test_unknown_type_is_rejected(self):
        self.assertFalse(generate("anything", "Nonsense").ok)

    def test_every_advertised_type_is_buildable(self):
        """Every option in the dropdown must have a builder behind it."""
        source = (
            "Name: Acme\nTitle: Acme\nPrice: 10\nStart: 2026-01-01\nCity: Leeds\n"
            "Home > A > B\nIs it good?\nYes.\nAlso good?\nYes.\n1. Step one.\n2. Step two.\n"
        )
        for key, _ in SCHEMA_TYPES:
            with self.subTest(schema_type=key):
                generate(source, key)  # must not raise

    def test_output_is_valid_json(self):
        result = generate("Name: Acme\nPrice: 10", "Product")
        json.loads(result.json_ld)

    def test_script_block_is_pasteable(self):
        result = generate("Name: Acme\nPrice: 10", "Product")
        self.assertTrue(result.script_block.startswith('<script type="application/ld+json">'))
        self.assertTrue(result.script_block.rstrip().endswith("</script>"))

    def test_failed_generation_has_no_script_block(self):
        self.assertEqual(generate("", "Product").script_block, "")

    def test_notes_are_advisory_and_do_not_block_output(self):
        result = generate("Name: Lamp", "Product")  # no price: a note, not a warning
        self.assertTrue(result.ok)
        self.assertTrue(result.notes)
        self.assertEqual(result.warnings, [])

    def test_warnings_always_suppress_markup(self):
        for content, kind in (
            ("Name: X", "Event"),
            ("Name: X", "LocalBusiness"),
            ("Home", "BreadcrumbList"),
            ("no questions here", "FAQPage"),
        ):
            with self.subTest(kind=kind):
                result = generate(content, kind)
                self.assertTrue(result.warnings)
                self.assertEqual(result.data, {})

    def test_serialisable(self):
        json.dumps(generate("Name: Acme\nPrice: 10", "Product").to_dict())


if __name__ == "__main__":
    unittest.main()
