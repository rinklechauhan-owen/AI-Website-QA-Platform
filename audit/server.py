"""Local web UI so a URL can be pasted into a browser instead of typed on a command line.

Built on http.server to keep the zero-dependency promise — no Flask, no Docker, no Node.
It binds to the loopback interface only: the audit engine fetches whatever URL it is given,
so exposing this on a network would hand out a request proxy.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

from audit import __version__
from audit.engine import audit_url
from audit.fetch import FetchError
from audit.report import html as html_report
from audit.report import pages as page_views
from audit.schemagen import VALID_TYPES, GeneratedSchema, generate

DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"

# Refuse absurd inputs before spending a network round trip on them.
MAX_URL_LENGTH = 2048

# Room for a pasted page of markup in the schema generator.
MAX_BODY_BYTES = 512 * 1024

# Schemes that must never reach the fetcher, even though it would fail on them anyway —
# a clear rejection beats a confusing connection error.
BLOCKED_SCHEMES = frozenset(
    {
        "file", "javascript", "data", "vbscript", "about", "blob",
        "ftp", "ftps", "sftp", "gopher", "mailto", "tel", "view-source", "chrome",
    }
)

# A leading "<scheme>:" — note this also matches "example.com:8080", which is a host and
# port rather than a scheme, so the two cases are told apart below.
_LEADING_SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")
_SCHEME_WITH_AUTHORITY = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")

def _validate(raw_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (url, error). Adds https:// when no scheme is given.

    The scheme has to be checked *before* defaulting it. Prepending https:// unconditionally
    would turn "file:///etc/passwd" into "https://file:///etc/passwd" — mangled into something
    that merely fails to connect, rather than refused outright.
    """
    candidate = (raw_url or "").strip()
    if not candidate:
        return None, "Enter a URL."
    if len(candidate) > MAX_URL_LENGTH:
        return None, "That URL is too long."

    match = _LEADING_SCHEME.match(candidate)
    if match:
        scheme = match.group(1).lower()
        if scheme not in ("http", "https"):
            # "https://x" style, or a scheme we explicitly refuse. Anything else with a
            # colon — "example.com:8080" — is a host and port, so it falls through.
            if _SCHEME_WITH_AUTHORITY.match(candidate) or scheme in BLOCKED_SCHEMES:
                return None, f"Only http and https URLs can be audited (got '{scheme}:')."

    if not candidate.lower().startswith(("http://", "https://")):
        candidate = "https://" + candidate

    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https"):
        return None, "Only http and https URLs can be audited."
    if not parsed.netloc:
        return None, "That does not look like a valid URL."

    return candidate, None


class _Handler(BaseHTTPRequestHandler):
    server_version = f"WebsiteQAAudit/{__version__}"

    # Quieten the default one-line-per-request logging; the CLI prints its own summary.
    def log_message(self, fmt, *args):  # noqa: A002 - signature fixed by the base class
        return

    def _send(self, body: str, status: int = 200, content_type: str = "text/html") -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        # The report embeds text from the audited page; block any script regardless.
        self.send_header(
            "Content-Security-Policy",
            # The font and logo are inlined as data: URIs; everything else stays blocked,
            # and script-src is absent so no script can run whatever the page contains.
            "default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - name fixed by the base class
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            # Support /?url=... so a URL can be linked or bookmarked directly.
            params = parse_qs(parsed.query)
            requested = (params.get("url") or [""])[0]
            if requested:
                self._run_audit(
                    requested,
                    check_links=bool(params.get("check_links")),
                    check_images=bool(params.get("check_images")),
                )
            else:
                self._send(page_views.audit_form())
            return

        if parsed.path == "/schema":
            self._send(page_views.schema_generator())
            return

        if parsed.path == "/health":
            self._send(json.dumps({"status": "ok", "version": __version__}), content_type="application/json")
            return

        self._send(page_views.audit_form(error="Page not found."), status=404)

    def do_POST(self) -> None:  # noqa: N802 - name fixed by the base class
        route = urlparse(self.path).path
        if route not in ("/audit", "/schema"):
            self._send(page_views.audit_form(error="Page not found."), status=404)
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0

        if length <= 0 or length > MAX_BODY_BYTES:
            self._send(page_views.audit_form(error="Malformed request."), status=400)
            return

        fields = parse_qs(
            self.rfile.read(length).decode("utf-8", errors="replace"), keep_blank_values=True
        )

        if route == "/schema":
            self._generate_schema(fields)
            return

        self._run_audit(
            (fields.get("url") or [""])[0],
            check_links=bool(fields.get("check_links")),
            check_images=bool(fields.get("check_images")),
        )

    def _generate_schema(self, fields) -> None:
        content = (fields.get("content") or [""])[0]
        schema_type = (fields.get("schema_type") or ["auto"])[0]
        if schema_type not in VALID_TYPES:
            schema_type = "auto"

        try:
            result = generate(content, schema_type)
        except Exception as exc:  # noqa: BLE001 - a bad paste must not kill the server
            result = GeneratedSchema(schema_type=schema_type)
            result.warnings.append(
                f"Could not process that content — {exc.__class__.__name__}: {exc}"
            )
            self._send(page_views.schema_generator(content, schema_type, result), status=500)
            return

        self._send(page_views.schema_generator(content, schema_type, result))

    def _run_audit(self, raw_url: str, check_links: bool, check_images: bool = False) -> None:
        url, error = _validate(raw_url)
        if error:
            self._send(page_views.audit_form(error, raw_url), status=400)
            return

        try:
            result = audit_url(url, check_links=check_links, check_images=check_images)
        except FetchError as exc:
            self._send(page_views.audit_form(f"Could not fetch that page — {exc}", raw_url),
                       status=502)
            return
        except Exception as exc:  # noqa: BLE001 - never take the server down for one bad page
            self._send(
                page_views.audit_form(f"Audit failed: {exc.__class__.__name__}: {exc}", raw_url),
                status=500,
            )
            return

        # serving=True adds the sidebar links only a running server can honour.
        self._send(html_report.render(result, serving=True))


def _port_available(host: str, port: int) -> bool:
    """Whether a listener can take this port.

    Deliberately does not set SO_REUSEADDR: on Windows that flag permits binding a port
    another socket is already listening on, so the probe would report every port free.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def find_port(host: str = DEFAULT_HOST, start: int = DEFAULT_PORT, attempts: int = 20) -> int:
    """First free port at or after ``start``."""
    for offset in range(attempts):
        if _port_available(host, start + offset):
            return start + offset
    raise OSError(f"No free port between {start} and {start + attempts - 1}")


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    auto_port: bool = True,
) -> int:
    """Run the local UI until interrupted. Returns a process exit code."""
    if auto_port and not _port_available(host, port):
        try:
            port = find_port(host, port)
        except OSError as exc:
            print(f"error: {exc}")
            return 2

    httpd = ThreadingHTTPServer((host, port), _Handler)
    address = f"http://{host}:{port}"

    print(f"Website QA audit UI running at {address}")
    print("Paste a URL in the browser. Press Ctrl+C to stop.")

    if open_browser:
        # Delay slightly so the listener is definitely accepting before the tab opens.
        threading.Timer(0.4, webbrowser.open, args=(address,)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()

    return 0
