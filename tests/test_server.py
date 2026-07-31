"""Web UI tests. A real server is started on a free loopback port; audits are stubbed."""

import json
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from audit import server
from audit.engine import audit_response
from audit.fetch import FetchError
from tests.fixtures import MESSY, response


def _stub_audit(target_url, **kwargs):
    """Stand in for audit_url so tests never reach the network."""
    return audit_response(response(MESSY, target_url), target_url)


class TestUrlValidation(unittest.TestCase):
    def test_scheme_added_when_missing(self):
        url, error = server._validate("example.com")
        self.assertIsNone(error)
        self.assertEqual(url, "https://example.com")

    def test_existing_scheme_preserved(self):
        self.assertEqual(server._validate("http://example.com")[0], "http://example.com")

    def test_host_and_port_is_not_mistaken_for_a_scheme(self):
        """'localhost:3000' must reach the fetcher, not be rejected as scheme 'localhost'."""
        url, error = server._validate("localhost:3000/page")
        self.assertIsNone(error)
        self.assertEqual(url, "https://localhost:3000/page")

    def test_file_scheme_rejected(self):
        """Regression: prepending https:// blindly turned this into a confusing 502."""
        url, error = server._validate("file:///C:/Windows/win.ini")
        self.assertIsNone(url)
        self.assertIn("Only http and https", error)

    def test_javascript_scheme_rejected(self):
        self.assertIsNone(server._validate("javascript:alert(1)")[0])

    def test_data_scheme_rejected(self):
        self.assertIsNone(server._validate("data:text/html,<h1>x</h1>")[0])

    def test_ftp_scheme_rejected(self):
        self.assertIsNone(server._validate("ftp://files.example.com/x")[0])

    def test_empty_input_rejected(self):
        self.assertIn("Enter a URL", server._validate("  ")[1])

    def test_overlong_input_rejected(self):
        self.assertIn("too long", server._validate("https://x.test/" + "a" * 4000)[1])

    def test_missing_host_rejected(self):
        self.assertIsNotNone(server._validate("https://")[1])


class TestServerRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = server.find_port(start=8900)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", cls.port), server._Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=30) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")

    def _post(self, data):
        request = urllib.request.Request(
            self.base + "/audit", data=urllib.parse.urlencode(data).encode(), method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")

    def test_form_is_served(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn('<input id="url"', body)

    def test_health_endpoint(self):
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "ok")

    def test_unknown_path_returns_404(self):
        self.assertEqual(self._get("/nope")[0], 404)

    def test_empty_url_returns_form_with_error(self):
        status, body = self._post({"url": ""})
        self.assertEqual(status, 400)
        self.assertIn("Enter a URL", body)

    def test_blocked_scheme_returns_400(self):
        status, body = self._post({"url": "file:///etc/passwd"})
        self.assertEqual(status, 400)
        self.assertIn("Only http and https", body)

    def test_unfetchable_page_returns_502(self):
        with mock.patch.object(server, "audit_url", side_effect=FetchError("no such host")):
            status, body = self._post({"url": "https://nope.invalid"})
        self.assertEqual(status, 502)
        self.assertIn("Could not fetch", body)

    def test_unexpected_error_does_not_kill_the_server(self):
        with mock.patch.object(server, "audit_url", side_effect=RuntimeError("boom")):
            status, _ = self._post({"url": "https://example.com"})
        self.assertEqual(status, 500)
        self.assertEqual(self._get("/")[0], 200, "server should still be serving")

    def test_successful_audit_renders_every_section(self):
        with mock.patch.object(server, "audit_url", _stub_audit):
            status, body = self._post({"url": "example.com"})
        self.assertEqual(status, 200)
        for section in (
            "Page content",
            "Page structure",
            "Image alt text",
            "Suggested schema.org markup",
            "Audit another page",
        ):
            with self.subTest(section=section):
                self.assertIn(section, body)

    def test_served_report_contains_no_live_script(self):
        with mock.patch.object(server, "audit_url", _stub_audit):
            _, body = self._post({"url": "example.com"})
        self.assertNotIn("<script", body.lower())

    def test_generated_jsonld_is_escaped_not_executed(self):
        with mock.patch.object(server, "audit_url", _stub_audit):
            _, body = self._post({"url": "example.com"})
        self.assertIn("&lt;script type=&quot;application/ld+json&quot;&gt;", body)

    def test_query_string_shortcut(self):
        with mock.patch.object(server, "audit_url", _stub_audit):
            status, body = self._get("/?url=example.com")
        self.assertEqual(status, 200)
        self.assertIn("Page content", body)

    def test_csp_header_blocks_scripts(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as resp:
            self.assertIn("default-src 'none'", resp.headers.get("Content-Security-Policy", ""))


class TestPortSelection(unittest.TestCase):
    def test_find_port_returns_a_bindable_port(self):
        port = server.find_port(start=8940)
        self.assertTrue(server._port_available("127.0.0.1", port))

    def test_find_port_skips_a_port_in_use(self):
        taken = server.find_port(start=8960)
        httpd = ThreadingHTTPServer(("127.0.0.1", taken), server._Handler)
        try:
            self.assertNotEqual(server.find_port(start=taken), taken)
        finally:
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
