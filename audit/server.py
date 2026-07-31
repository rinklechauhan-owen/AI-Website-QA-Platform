"""Local web UI so a URL can be pasted into a browser instead of typed on a command line.

Built on http.server to keep the zero-dependency promise — no Flask, no Docker, no Node.
It binds to the loopback interface only: the audit engine fetches whatever URL it is given,
so exposing this on a network would hand out a request proxy.
"""

from __future__ import annotations

import html as html_module
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

DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"

# Refuse absurd inputs before spending a network round trip on them.
MAX_URL_LENGTH = 2048

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

_FORM_CSS = """
* { box-sizing: border-box; }
:root {
  color-scheme: light dark;
  --bg: #f7f8fa; --card: #fff; --border: #e4e7ec; --ink: #101828;
  --ink-muted: #667085; --ink-faint: #98a2b3; --accent: #2563eb; --bad: #d92d20;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #0c111d; --card: #161b26; --border: #262b37; --ink: #f5f5f6;
          --ink-muted: #94969c; --ink-faint: #6c6f7a; --accent: #60a5fa; --bad: #f97066; }
}
body { margin: 0; min-height: 100vh; display: flex; align-items: center;
       justify-content: center; padding: 32px 20px; background: var(--bg); color: var(--ink);
       font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.card { width: 100%; max-width: 560px; background: var(--card); border: 1px solid var(--border);
        border-radius: 16px; padding: 36px; box-shadow: 0 1px 3px rgba(16,24,40,.1); }
.eyebrow { font-size: 11px; letter-spacing: .09em; text-transform: uppercase;
           color: var(--ink-faint); font-weight: 600; margin: 0 0 8px; }
h1 { font-size: 23px; margin: 0 0 8px; font-weight: 650; letter-spacing: -.01em; }
.lede { margin: 0 0 26px; color: var(--ink-muted); font-size: 14px; }
label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 7px; }
input[type=url] { width: 100%; padding: 13px 15px; font-size: 15px; border-radius: 10px;
                  border: 1px solid var(--border); background: var(--bg); color: var(--ink); }
input[type=url]:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
.opts { margin: 18px 0 24px; display: flex; flex-direction: column; gap: 11px; }
.opt { display: flex; gap: 9px; align-items: flex-start; font-size: 13.5px;
       color: var(--ink-muted); }
.opt input { margin-top: 3px; }
.opt b { color: var(--ink); font-weight: 600; }
button { width: 100%; padding: 13px; font-size: 15px; font-weight: 600; border: none;
         border-radius: 10px; background: var(--accent); color: #fff; cursor: pointer; }
button:hover { filter: brightness(1.08); }
.err { margin: 0 0 20px; padding: 13px 15px; border-radius: 10px; font-size: 13.5px;
       background: color-mix(in srgb, var(--bad) 12%, transparent);
       border: 1px solid var(--bad); color: var(--bad); word-break: break-word; }
.hint { margin: 22px 0 0; font-size: 12px; color: var(--ink-faint); line-height: 1.7; }
.back { display: inline-block; margin: 0 0 18px; font-size: 13px; color: var(--accent);
        text-decoration: none; }
.back:hover { text-decoration: underline; }
"""


def _form_page(error: Optional[str] = None, url_value: str = "") -> str:
    error_block = f'<p class="err">{html_module.escape(error)}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Website QA Audit</title>
<style>{_FORM_CSS}</style>
</head>
<body>
<div class="card">
  <p class="eyebrow">AI Website QA Platform</p>
  <h1>Audit a page</h1>
  <p class="lede">Paste a URL. You will get SEO, image, and structure findings, a content
  listing, and generated schema.org markup.</p>
  {error_block}
  <form method="post" action="/audit">
    <label for="url">Website URL</label>
    <input id="url" name="url" type="url" required autofocus
           placeholder="https://example.com"
           value="{html_module.escape(url_value, quote=True)}">
    <div class="opts">
      <label class="opt">
        <input type="checkbox" name="check_links" value="1">
        <span><b>Check every link</b> — verifies each link resolves. Slower, makes extra
        requests to the target site.</span>
      </label>
      <label class="opt">
        <input type="checkbox" name="check_images" value="1" checked>
        <span><b>Check image sizes</b> — measures each image to find any over 2.5&nbsp;MB.
        One extra request per image.</span>
      </label>
    </div>
    <button type="submit">Run audit</button>
  </form>
  <p class="hint">Analyses the served HTML. Performance, accessibility rules, and visual
  review need the browser-based modules and are not included. Version {__version__}.</p>
</div>
</body>
</html>
"""


def _error_page(message: str, url_value: str) -> str:
    return _form_page(error=message, url_value=url_value)


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
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
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
                self._send(_form_page())
            return

        if parsed.path == "/health":
            self._send(json.dumps({"status": "ok", "version": __version__}), content_type="application/json")
            return

        self._send(_form_page(error="Page not found."), status=404)

    def do_POST(self) -> None:  # noqa: N802 - name fixed by the base class
        if urlparse(self.path).path != "/audit":
            self._send(_form_page(error="Page not found."), status=404)
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0

        if length <= 0 or length > 64 * 1024:
            self._send(_error_page("Malformed request.", ""), status=400)
            return

        fields = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
        self._run_audit(
            (fields.get("url") or [""])[0],
            check_links=bool(fields.get("check_links")),
            check_images=bool(fields.get("check_images")),
        )

    def _run_audit(self, raw_url: str, check_links: bool, check_images: bool = False) -> None:
        url, error = _validate(raw_url)
        if error:
            self._send(_error_page(error, raw_url), status=400)
            return

        try:
            result = audit_url(url, check_links=check_links, check_images=check_images)
        except FetchError as exc:
            self._send(_error_page(f"Could not fetch that page — {exc}", raw_url), status=502)
            return
        except Exception as exc:  # noqa: BLE001 - never take the server down for one bad page
            self._send(
                _error_page(f"Audit failed: {exc.__class__.__name__}: {exc}", raw_url), status=500
            )
            return

        page = html_report.render(result)
        # Give the reader a route back to the form without using the browser's back button.
        page = page.replace(
            '<div class="wrap">',
            '<div class="wrap">\n<a class="back" href="/">&larr; Audit another page</a>',
            1,
        )
        self._send(page)


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
