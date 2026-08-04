"""Design system: embedded assets, one type scale, and accessible brand colours."""

import re
import unittest

from audit.engine import audit_response
from audit.report import pages as page_views
from audit.report import html as html_report
from audit.report.theme import (
    ASSETS,
    BASE_CSS,
    FONT_DATA_URI,
    FONT_STACK,
    LOGO_DATA_URI,
    logo_img,
)
from tests.fixtures import MESSY, response

BRAND_PRIMARY = "#3264f5"
BRAND_SECONDARY = "#5b95d2"


def contrast(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two #rrggbb colours."""

    def luminance(colour: str) -> float:
        channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class TestEmbeddedAssets(unittest.TestCase):
    def test_font_file_ships_with_the_package(self):
        self.assertTrue((ASSETS / "montserrat-variable-latin.woff2").exists())

    def test_open_font_licence_ships_alongside_it(self):
        """OFL requires the licence to travel with any redistributed font."""
        licence = ASSETS / "Montserrat-OFL.txt"
        self.assertTrue(licence.exists())
        self.assertIn("SIL OPEN FONT LICENSE", licence.read_text(encoding="utf-8").upper())

    def test_logo_file_ships_with_the_package(self):
        self.assertTrue((ASSETS / "owen-media-logo-white.png").exists())

    def test_font_is_inlined_as_a_data_uri(self):
        self.assertTrue(FONT_DATA_URI.startswith("data:font/woff2;base64,"))
        self.assertIn("@font-face", BASE_CSS)
        self.assertIn(FONT_DATA_URI, BASE_CSS)

    def test_logo_is_inlined_as_a_data_uri(self):
        self.assertTrue(LOGO_DATA_URI.startswith("data:image/png;base64,"))
        self.assertIn(LOGO_DATA_URI, logo_img())

    def test_montserrat_is_first_in_the_stack(self):
        self.assertTrue(FONT_STACK.startswith('"Montserrat"'))
        self.assertIn("sans-serif", FONT_STACK, "a fallback must remain if the font fails")

    def test_logo_has_alt_text(self):
        self.assertIn('alt="Owen Media"', logo_img())

    def test_report_references_no_external_host(self):
        """Embedding the font and logo must not have introduced a remote fetch."""
        html = html_report.render(audit_response(response(MESSY), "https://acme.test/"))
        referenced = re.findall(r'(?:src|href)\s*=\s*"(https?://[^"]+)"', html)
        external = [u for u in referenced if not u.startswith("https://acme.test")]
        self.assertEqual(external, [])
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertNotIn("fonts.gstatic.com", html)


class TestTypeScale(unittest.TestCase):
    TOKENS = ("--fs-xs", "--fs-sm", "--fs-base", "--fs-md", "--fs-lg", "--fs-xl", "--fs-2xl")

    def test_every_scale_token_is_defined(self):
        for token in self.TOKENS:
            with self.subTest(token=token):
                self.assertRegex(BASE_CSS, re.escape(token) + r":\s*\d+px")

    def test_no_component_hardcodes_a_font_size(self):
        """One scale for the whole dashboard: every font-size must reference a token."""
        raw = set(re.findall(r"font-size:\s*(\d+(?:\.\d+)?px)", BASE_CSS))
        self.assertEqual(raw, set(), f"hardcoded font sizes: {sorted(raw)}")

    def test_standalone_pages_use_the_same_scale(self):
        raw = set(re.findall(r"font-size:\s*(\d+(?:\.\d+)?px)", page_views._PAGE_CSS))
        self.assertEqual(raw, set(), f"hardcoded font sizes: {sorted(raw)}")

    def test_font_weights_come_from_tokens(self):
        """Only 400/500/600/700 exist in the variable font; odd weights would synthesise."""
        raw = {w for w in re.findall(r"font-weight:\s*(\d+)", BASE_CSS)}
        self.assertTrue(raw <= {"400", "500", "600", "700"}, f"off-scale weights: {sorted(raw)}")

    def test_body_sets_the_base_size_once(self):
        self.assertRegex(BASE_CSS, r"body\s*\{[^}]*font-size:\s*var\(--fs-base\)")


class TestBrandColours(unittest.TestCase):
    def test_both_requested_colours_are_used(self):
        self.assertIn(BRAND_PRIMARY, BASE_CSS)
        self.assertIn(BRAND_SECONDARY, BASE_CSS)

    def test_a_gradient_combines_them(self):
        self.assertRegex(
            BASE_CSS, r"--brand-grad:\s*linear-gradient\([^)]*#3264f5[^)]*#5b95d2[^)]*\)"
        )

    def test_primary_passes_aa_against_white(self):
        self.assertGreaterEqual(contrast(BRAND_PRIMARY, "#ffffff"), 4.5)

    def test_secondary_is_not_used_for_text_on_light_backgrounds(self):
        """#5b95d2 is 3.15:1 on white, so it must stay decorative in light mode."""
        self.assertLess(contrast(BRAND_SECONDARY, "#ffffff"), 4.5)
        light_accent = re.search(r"--accent:\s*(#[0-9a-fA-F]{6});", BASE_CSS).group(1)
        self.assertEqual(light_accent.lower(), BRAND_PRIMARY)

    def test_secondary_becomes_the_accent_in_dark_mode_where_it_passes(self):
        dark_block = BASE_CSS.split("prefers-color-scheme: dark", 1)[1]
        dark_accent = re.search(r"--accent:\s*(#[0-9a-fA-F]{6});", dark_block).group(1)
        self.assertEqual(dark_accent.lower(), BRAND_SECONDARY)
        self.assertGreaterEqual(contrast(BRAND_SECONDARY, "#141a24"), 4.5)

    def test_accent_stat_card_uses_the_solid_primary_not_the_gradient(self):
        """White text on the gradient's light end would fail contrast."""
        rule = re.search(r"\.stat\.accent\s*\{([^}]*)\}", BASE_CSS).group(1)
        self.assertIn("var(--brand-1)", rule)
        self.assertNotIn("brand-grad", rule)


class TestBrandMarkPlacement(unittest.TestCase):
    def test_white_logo_sits_on_the_gradient_panel(self):
        """The wordmark is white on transparent, so a white sidebar would hide it."""
        rule = re.search(r"\.brand\s*\{([^}]*)\}", BASE_CSS).group(1)
        self.assertIn("var(--brand-grad)", rule)

    def test_report_and_tool_pages_both_show_the_logo(self):
        report = html_report.render(audit_response(response(MESSY), "https://acme.test/"))
        self.assertIn(LOGO_DATA_URI, report)
        self.assertIn(LOGO_DATA_URI, page_views.audit_form())
        self.assertIn(LOGO_DATA_URI, page_views.schema_generator())


if __name__ == "__main__":
    unittest.main()
