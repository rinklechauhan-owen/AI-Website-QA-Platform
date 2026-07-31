"""HTTP fetching on the standard library only.

urllib gives us redirects for free but not decompression or charset detection, so both are
handled here.
"""

from __future__ import annotations

import gzip
import re
import ssl
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass, field
from typing import Dict, Optional

DEFAULT_USER_AGENT = "AI-Website-QA-Platform/0.1 (+https://github.com/rinklechauhan-owen/AI-Website-QA-Platform)"
DEFAULT_TIMEOUT = 20

_CHARSET_IN_HEADER = re.compile(r"charset=([\w\-]+)", re.I)
_CHARSET_IN_META = re.compile(rb"""<meta[^>]+charset=["']?([\w\-]+)""", re.I)


class FetchError(Exception):
    """The request never produced a response (DNS, TLS, timeout, refused)."""


@dataclass
class Response:
    url: str
    status: int
    body: str
    headers: Dict[str, str] = field(default_factory=dict)
    elapsed_ms: int = 0
    byte_size: int = 0

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")

    @property
    def is_html(self) -> bool:
        return "html" in self.content_type.lower()


def _decompress(raw: bytes, encoding: str) -> bytes:
    encoding = (encoding or "").lower()
    try:
        if encoding == "gzip":
            return gzip.decompress(raw)
        if encoding == "deflate":
            # Some servers omit the zlib wrapper; retry raw if the standard path fails.
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
    except (OSError, zlib.error):
        # A mislabelled Content-Encoding is not worth failing the whole audit over.
        return raw
    return raw


def _decode(raw: bytes, content_type: str) -> str:
    match = _CHARSET_IN_HEADER.search(content_type or "")
    charset = match.group(1) if match else None

    if not charset:
        meta = _CHARSET_IN_META.search(raw[:4096])
        if meta:
            charset = meta.group(1).decode("ascii", "ignore")

    for candidate in (charset, "utf-8", "cp1252"):
        if not candidate:
            continue
        try:
            return raw.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue

    return raw.decode("utf-8", errors="replace")


def build_opener(verify_tls: bool) -> urllib.request.OpenerDirector:
    context = ssl.create_default_context()
    if not verify_tls:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))


def fetch(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
    method: str = "GET",
    verify_tls: bool = True,
) -> Response:
    """Fetch a URL, following redirects. Raises FetchError only if no response arrived.

    An HTTP error status is returned as a normal Response so the rules can report on it.
    """
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    opener = build_opener(verify_tls)
    started = time.monotonic()

    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
            headers = {k.lower(): v for k, v in response.headers.items()}
            final_url = response.geturl()
            status = response.status
    except urllib.error.HTTPError as exc:
        # 4xx/5xx still carry a body and headers worth reporting.
        raw = exc.read() if hasattr(exc, "read") else b""
        headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        final_url = exc.url if hasattr(exc, "url") else url
        status = exc.code
    except urllib.error.URLError as exc:
        raise FetchError(f"{url}: {exc.reason}") from exc
    except (ssl.SSLError, OSError, ValueError) as exc:
        raise FetchError(f"{url}: {exc}") from exc

    elapsed_ms = int((time.monotonic() - started) * 1000)
    decompressed = _decompress(raw, headers.get("content-encoding", ""))

    return Response(
        url=final_url,
        status=status,
        body=_decode(decompressed, headers.get("content-type", "")),
        headers=headers,
        elapsed_ms=elapsed_ms,
        byte_size=len(raw),
    )


def head_status(
    url: str,
    timeout: int = 10,
    user_agent: str = DEFAULT_USER_AGENT,
    verify_tls: bool = True,
) -> Optional[int]:
    """Status code for a URL, or None if it could not be reached.

    Tries HEAD first and falls back to GET, since plenty of servers reject HEAD outright.
    """
    for method in ("HEAD", "GET"):
        try:
            response = fetch(
                url, timeout=timeout, user_agent=user_agent, method=method, verify_tls=verify_tls
            )
        except FetchError:
            return None
        if response.status not in (405, 501):
            return response.status
    return None
