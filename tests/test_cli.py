"""CLI tests. The network is stubbed out so the suite runs offline."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from audit import cli
from audit.engine import audit_response
from audit.fetch import FetchError
from tests.fixtures import CLEAN, MESSY, response


def _fake_audit(html, url="https://acme.test/"):
    """Return a stand-in for audit_url that never touches the network."""

    def run(target_url, **kwargs):
        return audit_response(response(html, url), url, check_links=False)

    return run


class TestCliOutput(unittest.TestCase):
    def test_text_output_to_stdout(self):
        out = io.StringIO()
        with mock.patch.object(cli, "audit_url", _fake_audit(MESSY)):
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = cli.main(["acme.test"])
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("WEBSITE QA AUDIT", out.getvalue())

    def test_json_output_is_valid(self):
        out = io.StringIO()
        with mock.patch.object(cli, "audit_url", _fake_audit(MESSY)):
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                cli.main(["acme.test", "--format", "json"])
        payload = json.loads(out.getvalue())
        self.assertIn("packs", payload)
        self.assertIn("overall_score", payload)

    def test_html_written_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "report.html"
            with mock.patch.object(cli, "audit_url", _fake_audit(MESSY)):
                with redirect_stderr(io.StringIO()):
                    code = cli.main(["acme.test", "--format", "html", "--out", str(target)])
            self.assertEqual(code, cli.EXIT_OK)
            self.assertTrue(target.exists(), "parent directories should be created")
            self.assertIn("<!DOCTYPE html>", target.read_text(encoding="utf-8"))

    def test_no_color_flag_strips_ansi(self):
        out = io.StringIO()
        with mock.patch.object(cli, "audit_url", _fake_audit(MESSY)):
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                cli.main(["acme.test", "--no-color"])
        self.assertNotIn("\033[", out.getvalue())


class TestCliExitCodes(unittest.TestCase):
    def test_clean_page_exits_zero_without_fail_on(self):
        with mock.patch.object(cli, "audit_url", _fake_audit(CLEAN)):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["acme.test"]), cli.EXIT_OK)

    def test_messy_page_exits_zero_without_fail_on(self):
        """Findings alone must not fail the run — only --fail-on makes it non-zero."""
        with mock.patch.object(cli, "audit_url", _fake_audit(MESSY)):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["acme.test"]), cli.EXIT_OK)

    def test_fail_on_high_trips_on_messy_page(self):
        with mock.patch.object(cli, "audit_url", _fake_audit(MESSY)):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = cli.main(["acme.test", "--fail-on", "high"])
        self.assertEqual(code, cli.EXIT_FINDINGS)

    def test_fail_on_high_passes_on_clean_page(self):
        with mock.patch.object(cli, "audit_url", _fake_audit(CLEAN)):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = cli.main(["acme.test", "--fail-on", "high"])
        self.assertEqual(code, cli.EXIT_OK)

    def test_fail_on_is_inclusive_of_more_severe_findings(self):
        """--fail-on medium must also trip on a critical finding."""
        with mock.patch.object(cli, "audit_url", _fake_audit(MESSY)):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = cli.main(["acme.test", "--fail-on", "medium"])
        self.assertEqual(code, cli.EXIT_FINDINGS)

    def test_unreachable_page_exits_error(self):
        def boom(*args, **kwargs):
            raise FetchError("acme.test: Name or service not known")

        err = io.StringIO()
        with mock.patch.object(cli, "audit_url", boom):
            with redirect_stderr(err):
                code = cli.main(["acme.test"])
        self.assertEqual(code, cli.EXIT_ERROR)
        self.assertIn("could not fetch", err.getvalue())


class TestCliArguments(unittest.TestCase):
    def test_open_implies_html_and_default_filename(self):
        parser = cli.build_parser()
        args = parser.parse_args(["acme.test", "--open"])
        self.assertTrue(args.open_after)
        self.assertIsNone(args.out)  # filled in by main()

    def test_defaults(self):
        args = cli.build_parser().parse_args(["acme.test"])
        self.assertEqual(args.format, "text")
        self.assertEqual(args.max_links, 40)
        self.assertFalse(args.check_links)
        self.assertFalse(args.insecure)

    def test_invalid_format_rejected(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["acme.test", "--format", "xml"])

    def test_invalid_fail_on_rejected(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["acme.test", "--fail-on", "catastrophic"])


if __name__ == "__main__":
    unittest.main()
