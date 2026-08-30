"""URL normalisation and classification.

Real sites reach the same page by many spellings. Crawling each spelling separately wastes the
URL budget and reports the same problem repeatedly, so every URL passes through here first.

Two different jobs, deliberately kept apart:

* :func:`normalise` produces the URL to **fetch**. It is conservative — it fixes only what is
  unambiguously safe (case of scheme and host, default ports, dot segments, fragments,
  percent-encoding), because changing a path can change what a server returns.
* :func:`dedupe_key` produces the key used to decide **"have I already seen this?"**. It is
  aggressive: it additionally folds the trailing slash and strips tracking parameters, so
  ``/about``, ``/about/`` and ``/about/?utm_source=x`` collapse to one entry.

Fetching faithfully while deduplicating aggressively is what stops a crawl visiting the same
page five times without ever requesting a URL the site did not advertise.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence, Set
from urllib.parse import (
    parse_qsl,
    quote,
    unquote,
    urljoin,
    urlsplit,
    urlunsplit,
)

# Schemes a crawler must never follow.
NON_CRAWLABLE_SCHEMES = frozenset(
    {
        "mailto", "tel", "sms", "javascript", "data", "blob", "about", "file",
        "ftp", "ftps", "sftp", "gopher", "ws", "wss", "callto", "skype",
        "whatsapp", "viber", "intent", "market", "itms-apps", "magnet",
    }
)

DEFAULT_PORTS = {"http": "80", "https": "443"}

# Analytics and advertising parameters that never change what a page returns. Stripping them
# for the dedupe key stops one page being crawled once per campaign.
TRACKING_PARAMS = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "utm_id", "utm_source_platform", "utm_creative_format", "utm_marketing_tactic",
        "gclid", "gclsrc", "gad_source", "gbraid", "wbraid", "dclid",
        "fbclid", "msclkid", "yclid", "ttclid", "twclid", "igshid", "li_fat_id",
        "mc_cid", "mc_eid", "_ga", "_gl", "hsa_acc", "hsa_cam", "hsa_grp",
        "mkt_tok", "s_kwcid", "vero_id", "oly_anon_id", "oly_enc_id",
    }
)

# Extensions that are not HTML pages. Crawling them wastes budget and they cannot be parsed.
BINARY_EXTENSIONS = frozenset(
    {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico", ".bmp", ".tiff",
        ".css", ".js", ".mjs", ".map", ".json", ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ".zip", ".gz", ".tar", ".rar", ".7z", ".dmg", ".exe", ".msi", ".apk",
        ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ogg", ".wav", ".m4a",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".rtf",
        ".csv", ".txt", ".epub", ".psd", ".ai", ".eps", ".dwg",
    }
)

DOCUMENT_EXTENSIONS = frozenset({".pdf"})

_PERCENT = re.compile(r"%([0-9a-fA-F]{2})")
_MULTI_SLASH = re.compile(r"/{2,}")


def _normalise_percent_encoding(text: str) -> str:
    """Uppercase hex digits and decode octets that never needed encoding.

    ``%2f`` and ``%2F`` are the same byte, and ``%7E`` is just ``~``. Without this, two
    spellings of one URL survive as separate entries.

    The unreserved set is **ASCII only**. Decoding by Unicode category instead would split
    multi-byte sequences: ``%C3%A9`` is one character (é), but ``chr(0xC3)`` is ``Ã``, which
    Python reports as alphanumeric — decoding it corrupts the URL.
    """

    def decode_unreserved(match: "re.Match[str]") -> str:
        char = chr(int(match.group(1), 16))
        if char.isascii() and (char.isalnum() or char in "-._~"):
            return char
        return match.group(0).upper()

    return _PERCENT.sub(decode_unreserved, text)


def _resolve_dot_segments(path: str) -> str:
    """Apply RFC 3986 ``.`` and ``..`` removal."""
    out: list[str] = []
    for segment in path.split("/"):
        if segment == ".":
            continue
        if segment == "..":
            if out and out[-1] != "":
                out.pop()
            continue
        out.append(segment)
    resolved = "/".join(out)
    if path.startswith("/") and not resolved.startswith("/"):
        resolved = "/" + resolved
    return resolved or "/"


# Characters legal in a path segment (RFC 3986 pchar) plus "/" as the separator.
_PATH_SAFE = "/:@!$&'()*+,;=~-._"
_HEX_PAIR = re.compile(r"[0-9a-fA-F]{2}")


def _encode_raw_only(text: str, safe: str) -> str:
    """Percent-encode unsafe raw characters while leaving existing escapes untouched.

    Decoding first and re-encoding would destroy meaning: ``%2F`` is a slash *inside* a path
    segment, and turning it into a literal ``/`` silently points at a different resource.
    """
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "%" and _HEX_PAIR.fullmatch(text[index + 1 : index + 3] or ""):
            out.append(text[index : index + 3])
            index += 3
        else:
            out.append(quote(char, safe=safe))
            index += 1
    return "".join(out)


def _clean_path(path: str) -> str:
    if not path:
        return "/"
    path = _MULTI_SLASH.sub("/", path)
    path = _resolve_dot_segments(path)
    path = _encode_raw_only(path, _PATH_SAFE)
    return _normalise_percent_encoding(path)


def _clean_query(
    query: str,
    *,
    drop_params: Iterable[str] = (),
    drop_all: bool = False,
    sort_params: bool = False,
) -> str:
    if not query or drop_all:
        return ""

    drop = {p.lower() for p in drop_params}
    pairs = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k.lower() not in drop]
    if sort_params:
        pairs.sort()

    return "&".join(
        f"{quote(k, safe='')}={quote(v, safe='')}" if v else quote(k, safe="")
        for k, v in pairs
    )


def scheme_of(url: str) -> str:
    return urlsplit(url).scheme.lower()


def is_crawlable_scheme(url: str) -> bool:
    scheme = scheme_of(url)
    return scheme in ("http", "https", "")


def extension_of(url: str) -> str:
    path = urlsplit(url).path
    _, _, last = path.rpartition("/")
    _, dot, ext = last.rpartition(".")
    return ("." + ext.lower()) if dot and len(ext) <= 5 else ""


def looks_like_document(url: str) -> bool:
    return extension_of(url) in DOCUMENT_EXTENSIONS


def looks_like_binary(url: str) -> bool:
    return extension_of(url) in BINARY_EXTENSIONS


def normalise(url: str, base: Optional[str] = None) -> Optional[str]:
    """The URL to fetch: absolute, canonically spelled, fragment removed.

    Returns ``None`` when the URL is not something a crawler can request at all.
    """
    if url is None:
        return None

    candidate = url.strip()
    if not candidate:
        return None

    # Strip control characters and whitespace a template may have left in an href.
    candidate = "".join(ch for ch in candidate if ch.isprintable() and ch not in "\t\r\n")

    if candidate.startswith("//") and base:
        candidate = urlsplit(base).scheme + ":" + candidate

    if not is_crawlable_scheme(candidate):
        return None

    if base:
        try:
            candidate = urljoin(base, candidate)
        except ValueError:
            return None

    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        return None
    if not parts.hostname:
        return None

    host = parts.hostname.lower()
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        pass  # Leave a host that cannot be IDNA-encoded as it is.

    netloc = host
    port = parts.port
    if port is not None and str(port) != DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"
    if parts.username:
        credentials = parts.username + (f":{parts.password}" if parts.password else "")
        netloc = f"{credentials}@{netloc}"

    path = _clean_path(parts.path)
    query = _clean_query(parts.query)

    # Fragment is always dropped: it never reaches the server.
    return urlunsplit((scheme, netloc, path, query, ""))


def dedupe_key(
    url: str,
    base: Optional[str] = None,
    *,
    ignore_trailing_slash: bool = True,
    strip_tracking: bool = True,
    ignore_query: bool = False,
    extra_drop_params: Sequence[str] = (),
    case_insensitive_path: bool = False,
) -> Optional[str]:
    """The key that answers "have I seen this page before?".

    More aggressive than :func:`normalise`. Never use the result as a URL to fetch.
    """
    normalised = normalise(url, base)
    if normalised is None:
        return None

    parts = urlsplit(normalised)

    drop: Set[str] = set(extra_drop_params)
    if strip_tracking:
        drop |= TRACKING_PARAMS

    query = _clean_query(
        parts.query, drop_params=drop, drop_all=ignore_query, sort_params=True
    )

    path = parts.path
    if ignore_trailing_slash and len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    if case_insensitive_path:
        path = path.lower()

    # index pages are the same resource as the directory that contains them.
    for index in ("/index.html", "/index.htm", "/index.php", "/default.html", "/default.htm"):
        if path.lower().endswith(index):
            path = path[: -len(index)] or "/"
            break

    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def host_of(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host.lower()


def registrable_host(url: str) -> str:
    """Host without a leading ``www.``, so ``www.example.com`` and ``example.com`` match."""
    host = host_of(url)
    return host[4:] if host.startswith("www.") else host


def same_site(url: str, root: str, *, allow_subdomains: bool = False) -> bool:
    """Whether ``url`` belongs to the site rooted at ``root``."""
    target, base = registrable_host(url), registrable_host(root)
    if not target or not base:
        return False
    if target == base:
        return True
    return allow_subdomains and target.endswith("." + base)


def is_internal(url: str, root: str, *, allow_subdomains: bool = False) -> bool:
    return same_site(url, root, allow_subdomains=allow_subdomains)


def depth_of(url: str) -> int:
    """Path segment count, used as a fallback when link depth is unknown."""
    path = urlsplit(url).path.strip("/")
    return len([segment for segment in path.split("/") if segment]) if path else 0


def matches_any(url: str, patterns: Sequence[str]) -> bool:
    """Case-insensitive substring or glob match against include/exclude patterns."""
    if not patterns:
        return False
    lowered = url.lower()
    for pattern in patterns:
        candidate = pattern.strip().lower()
        if not candidate:
            continue
        if any(ch in candidate for ch in "*?["):
            from fnmatch import fnmatch

            if fnmatch(lowered, candidate if "*" in candidate else f"*{candidate}*"):
                return True
        elif candidate in lowered:
            return True
    return False


def looks_like_trap(url: str, *, max_repeats: int = 3) -> bool:
    """Detect a path that repeats one segment over and over.

    Faceted navigation and broken relative links produce ``/a/b/a/b/a/b/…`` forever. Without a
    guard the crawl spends its whole budget in one loop.
    """
    segments = [s for s in urlsplit(url).path.split("/") if s]
    if len(segments) < max_repeats * 2:
        return False
    counts: dict[str, int] = {}
    for segment in segments:
        counts[segment] = counts.get(segment, 0) + 1
        if counts[segment] > max_repeats:
            return True
    return False
