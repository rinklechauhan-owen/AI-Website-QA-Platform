"""Fetching for the crawler: the same request handling, plus the redirect chain.

`audit.fetch.fetch` follows redirects silently, which is right for a single-page audit but
loses information a crawl needs — how many hops, through which URLs, and whether they loop.
This module records the chain while producing the identical :class:`audit.fetch.Response` the
audit engine already consumes, so nothing downstream has to change.

Decompression and charset detection are imported rather than reimplemented. Duplicating that
logic would be exactly the kind of drift the brief warns against.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from audit.fetch import (
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    FetchError,
    Response,
    build_opener,
)
from audit.fetch import _decode as decode_body       # noqa: PLC2701 - reuse, do not duplicate
from audit.fetch import _decompress as decompress    # noqa: PLC2701 - reuse, do not duplicate

MAX_REDIRECT_HOPS = 10


@dataclass
class Hop:
    """One step of a redirect chain."""

    url: str
    status: int
    location: str


@dataclass
class FetchOutcome:
    response: Optional[Response] = None
    chain: List[Hop] = field(default_factory=list)
    error: Optional[str] = None
    looped: bool = False

    @property
    def ok(self) -> bool:
        return self.response is not None

    @property
    def hops(self) -> int:
        return len(self.chain)

    @property
    def redirected(self) -> bool:
        return bool(self.chain)

    @property
    def chain_urls(self) -> List[str]:
        return [hop.url for hop in self.chain] + (
            [self.response.url] if self.response else []
        )


class _ChainRecorder(urllib.request.HTTPRedirectHandler):
    """Records each redirect while letting urllib do the actual following."""

    def __init__(self) -> None:
        self.chain: List[Hop] = []
        self.looped = False
        self._seen: set = set()

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        source = req.full_url
        self.chain.append(Hop(url=source, status=code, location=newurl))

        if newurl in self._seen or len(self.chain) > MAX_REDIRECT_HOPS:
            self.looped = True
            return None  # Stops the chain; urllib raises the 3xx as an HTTPError.
        self._seen.add(newurl)

        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Used when the crawl is configured not to follow redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_page(
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
    verify_tls: bool = True,
    follow_redirects: bool = True,
    method: str = "GET",
) -> FetchOutcome:
    """Fetch a URL, recording any redirect chain.

    Never raises. A connection failure comes back as ``FetchOutcome.error`` so one unreachable
    page cannot end a crawl.
    """
    recorder = _ChainRecorder() if follow_redirects else _NoRedirect()

    # The opener has to be built *with* the recorder rather than having it added afterwards.
    # urllib installs its own HTTPRedirectHandler by default and calls handlers in
    # registration order, so an added handler never sees the redirect. Passing a subclass of
    # the default at construction time makes urllib skip installing the default one.
    # The TLS handler is taken from audit.fetch so verification behaviour stays identical.
    base_opener = build_opener(verify_tls)
    https_handler = next(
        (h for h in base_opener.handlers if isinstance(h, urllib.request.HTTPSHandler)),
        urllib.request.HTTPSHandler(),
    )
    opener = urllib.request.build_opener(https_handler, recorder)

    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    started = time.monotonic()
    chain = getattr(recorder, "chain", [])

    try:
        with opener.open(request, timeout=timeout) as raw:
            body = raw.read()
            headers = {k.lower(): v for k, v in raw.headers.items()}
            final_url, status = raw.geturl(), raw.status
    except urllib.error.HTTPError as exc:
        # 3xx surfaces here when redirects are off or the chain was cut; 4xx/5xx always do.
        body = exc.read() if hasattr(exc, "read") else b""
        headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        final_url = getattr(exc, "url", url)
        status = exc.code
    except urllib.error.URLError as exc:
        return FetchOutcome(
            chain=list(chain),
            error=str(getattr(exc, "reason", exc)),
            looped=getattr(recorder, "looped", False),
        )
    except (OSError, ValueError, FetchError) as exc:
        return FetchOutcome(
            chain=list(chain), error=str(exc), looped=getattr(recorder, "looped", False)
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    decoded = decode_body(
        decompress(body, headers.get("content-encoding", "")), headers.get("content-type", "")
    )

    return FetchOutcome(
        response=Response(
            url=final_url,
            status=status,
            body=decoded,
            headers=headers,
            elapsed_ms=elapsed_ms,
            byte_size=len(body),
        ),
        chain=list(getattr(recorder, "chain", [])),
        looped=getattr(recorder, "looped", False),
    )


def status_only(
    url: str,
    *,
    timeout: int = 10,
    user_agent: str = DEFAULT_USER_AGENT,
    verify_tls: bool = True,
) -> Tuple[Optional[int], Optional[str]]:
    """(status, error) for a URL, without downloading a body where the server allows it.

    Used to check external links and to resolve links to pages outside the crawl scope.
    """
    for method in ("HEAD", "GET"):
        outcome = fetch_page(
            url, timeout=timeout, user_agent=user_agent, verify_tls=verify_tls, method=method
        )
        if outcome.error:
            return None, outcome.error
        if outcome.response and outcome.response.status not in (405, 501):
            return outcome.response.status, None
    return None, "no response"
