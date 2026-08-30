"""XML sitemap discovery and parsing.

Handles plain sitemaps, sitemap indexes that point at further sitemaps, and gzipped files.
Parsing is namespace-agnostic because real sitemaps declare the namespace inconsistently, and
a sitemap that fails to parse is reported rather than silently treated as empty.
"""

from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from urllib.parse import urlsplit, urlunsplit

from audit.crawl import urlnorm
from audit.fetch import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT, FetchError, fetch

# Conventional locations to try when robots.txt names none.
COMMON_PATHS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemap/sitemap.xml",
    "/wp-sitemap.xml",
    "/sitemap.xml.gz",
)

# A sitemap index may nest; without a cap a malformed one could recurse indefinitely.
MAX_SITEMAP_FILES = 50
MAX_URLS = 100_000


@dataclass
class SitemapEntry:
    loc: str
    lastmod: Optional[str] = None
    changefreq: Optional[str] = None
    priority: Optional[str] = None
    source: str = ""


@dataclass
class SitemapReport:
    checked: List[str] = field(default_factory=list)
    found: List[str] = field(default_factory=list)
    errors: Dict[str, str] = field(default_factory=dict)
    entries: List[SitemapEntry] = field(default_factory=list)
    duplicate_locs: List[str] = field(default_factory=list)
    is_index: bool = False

    @property
    def any_found(self) -> bool:
        return bool(self.found)

    @property
    def urls(self) -> List[str]:
        return [entry.loc for entry in self.entries]

    def url_set(self, **dedupe_options) -> Set[str]:
        keys = set()
        for entry in self.entries:
            key = urlnorm.dedupe_key(entry.loc, **dedupe_options)
            if key:
                keys.add(key)
        return keys

    def to_dict(self) -> Dict:
        return {
            "checked": self.checked,
            "found": self.found,
            "errors": self.errors,
            "is_index": self.is_index,
            "url_count": len(self.entries),
            "duplicate_count": len(self.duplicate_locs),
        }


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _maybe_decompress(body: str, url: str, raw_hint: bytes = b"") -> str:
    if not url.lower().endswith(".gz"):
        return body
    try:
        return gzip.decompress(raw_hint or body.encode("latin-1", "ignore")).decode(
            "utf-8", "replace"
        )
    except (OSError, ValueError, UnicodeDecodeError):
        return body


def parse_xml(text: str, source: str = "") -> Dict[str, List]:
    """Parse sitemap XML into ``{"entries": [...], "sitemaps": [...]}``.

    Raises ``ET.ParseError`` for malformed XML so the caller can report it.
    """
    root = ET.fromstring(text.strip())
    entries: List[SitemapEntry] = []
    sitemaps: List[str] = []
    root_name = _localname(root.tag)

    for child in root:
        name = _localname(child.tag)
        if name not in ("url", "sitemap"):
            continue

        values: Dict[str, str] = {}
        for leaf in child:
            values[_localname(leaf.tag)] = (leaf.text or "").strip()

        loc = values.get("loc", "").strip()
        if not loc:
            continue

        if name == "sitemap":
            sitemaps.append(loc)
        else:
            entries.append(
                SitemapEntry(
                    loc=loc,
                    lastmod=values.get("lastmod"),
                    changefreq=values.get("changefreq"),
                    priority=values.get("priority"),
                    source=source,
                )
            )

    return {"entries": entries, "sitemaps": sitemaps, "root": root_name}


def _candidate_urls(site_url: str, from_robots: List[str]) -> List[str]:
    parts = urlsplit(site_url)
    candidates: List[str] = []
    seen: Set[str] = set()

    for url in list(from_robots) + [
        urlunsplit((parts.scheme, parts.netloc, path, "", "")) for path in COMMON_PATHS
    ]:
        normalised = urlnorm.normalise(url, site_url)
        if normalised and normalised not in seen:
            seen.add(normalised)
            candidates.append(normalised)

    return candidates


def discover(
    site_url: str,
    from_robots: Optional[List[str]] = None,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = DEFAULT_TIMEOUT,
    verify_tls: bool = True,
    max_files: int = MAX_SITEMAP_FILES,
) -> SitemapReport:
    """Find and read the site's sitemaps.

    Locations named by robots.txt are tried first; conventional paths are only tried when
    robots.txt named none, to avoid pointless 404s against sites that already told us.
    """
    report = SitemapReport()
    robots_locations = list(from_robots or [])

    # If robots.txt named sitemaps, trust it and do not guess.
    if robots_locations:
        queue = [u for u in (urlnorm.normalise(x, site_url) for x in robots_locations) if u]
    else:
        queue = _candidate_urls(site_url, [])

    seen_files: Set[str] = set()
    seen_locs: Set[str] = set()
    processed = 0

    while queue and processed < max_files and len(report.entries) < MAX_URLS:
        url = queue.pop(0)
        if url in seen_files:
            continue
        seen_files.add(url)
        report.checked.append(url)
        processed += 1

        try:
            response = fetch(url, timeout=timeout, user_agent=user_agent, verify_tls=verify_tls)
        except FetchError as exc:
            report.errors[url] = str(exc)
            continue

        if response.status >= 400:
            # A guessed location returning 404 is expected, not an error worth reporting.
            if robots_locations:
                report.errors[url] = f"HTTP {response.status}"
            continue

        body = _maybe_decompress(response.body, url)

        try:
            parsed = parse_xml(body, source=url)
        except ET.ParseError as exc:
            report.errors[url] = f"Malformed XML: {exc}"
            continue

        report.found.append(url)

        if parsed["sitemaps"]:
            report.is_index = True
            for child in parsed["sitemaps"]:
                child_url = urlnorm.normalise(child, url)
                if child_url and child_url not in seen_files:
                    queue.append(child_url)

        for entry in parsed["entries"]:
            if entry.loc in seen_locs:
                report.duplicate_locs.append(entry.loc)
                continue
            seen_locs.add(entry.loc)
            report.entries.append(entry)

    return report
