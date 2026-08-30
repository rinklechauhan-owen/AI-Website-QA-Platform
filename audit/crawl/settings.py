"""Crawl configuration.

Every limit lives here rather than being written into the crawl loop, so the 2,000-URL ceiling
is a default that can be raised from a form field or a CLI flag without touching logic.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from audit.assets import DEFAULT_SIZE_LIMIT
from audit.fetch import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT

# The headline limit from the brief. A default, not a hard-coded constant.
DEFAULT_MAX_URLS = 2000
# Ceiling on what a single crawl may be configured to do, as a safety rail.
ABSOLUTE_MAX_URLS = 50_000


@dataclass
class CrawlSettings:
    """Controls presented in the settings panel, with sensible defaults."""

    # --- scope -----------------------------------------------------------------
    max_urls: int = DEFAULT_MAX_URLS
    max_depth: Optional[int] = None            # None = unlimited
    crawl_subdomains: bool = False
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)

    # --- politeness ------------------------------------------------------------
    respect_robots: bool = True
    concurrency: int = 5
    delay_ms: int = 0                          # extra pause between requests per worker
    timeout: int = DEFAULT_TIMEOUT
    max_retries: int = 2
    user_agent: str = DEFAULT_USER_AGENT

    # --- fetching --------------------------------------------------------------
    follow_redirects: bool = True
    verify_tls: bool = True
    render_javascript: bool = False            # requires a renderer; see crawler.Renderer

    # --- what to include -------------------------------------------------------
    check_external_links: bool = True
    include_images: bool = True
    include_pdfs: bool = False
    check_image_sizes: bool = False            # one request per image; off for large crawls
    image_size_limit: int = DEFAULT_SIZE_LIMIT

    # --- URL handling ----------------------------------------------------------
    ignore_query: bool = False
    ignore_trailing_slash: bool = True
    strip_tracking_params: bool = True
    extra_drop_params: List[str] = field(default_factory=list)
    case_insensitive_paths: bool = False

    # --- sitemap ---------------------------------------------------------------
    discover_sitemaps: bool = True
    crawl_sitemap_urls: bool = True            # seed the frontier from the sitemap too

    def __post_init__(self) -> None:
        self.max_urls = max(1, min(int(self.max_urls), ABSOLUTE_MAX_URLS))
        self.concurrency = max(1, min(int(self.concurrency), 20))
        self.timeout = max(1, int(self.timeout))
        self.max_retries = max(0, min(int(self.max_retries), 5))
        self.delay_ms = max(0, int(self.delay_ms))
        if self.max_depth is not None:
            self.max_depth = max(0, int(self.max_depth))

    # --- URL policy shared with urlnorm ---------------------------------------

    def dedupe_options(self) -> Dict[str, Any]:
        return {
            "ignore_trailing_slash": self.ignore_trailing_slash,
            "strip_tracking": self.strip_tracking_params,
            "ignore_query": self.ignore_query,
            "extra_drop_params": tuple(self.extra_drop_params),
            "case_insensitive_path": self.case_insensitive_paths,
        }

    # --- persistence -----------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrawlSettings":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (data or {}).items() if k in known})

    @classmethod
    def from_json(cls, text: str) -> "CrawlSettings":
        try:
            return cls.from_dict(json.loads(text))
        except (ValueError, TypeError):
            return cls()

    def describe(self) -> List[tuple]:
        """(label, value) rows for the settings summary shown above a crawl."""
        return [
            ("Maximum URLs", f"{self.max_urls:,}"),
            ("Crawl depth", "Unlimited" if self.max_depth is None else str(self.max_depth)),
            ("Respect robots.txt", "On" if self.respect_robots else "OFF"),
            ("Follow redirects", "On" if self.follow_redirects else "Off"),
            ("Crawl subdomains", "On" if self.crawl_subdomains else "Off"),
            ("Render JavaScript", "On" if self.render_javascript else "Off"),
            ("Check external links", "On" if self.check_external_links else "Off"),
            ("Include images", "On" if self.include_images else "Off"),
            ("Include PDFs", "On" if self.include_pdfs else "Off"),
            ("Concurrency", str(self.concurrency)),
        ]
