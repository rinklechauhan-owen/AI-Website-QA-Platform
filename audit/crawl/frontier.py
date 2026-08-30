"""The crawl frontier: what to fetch next, and what to refuse.

Every scope decision lives here rather than in the crawl loop, so the reason a URL was skipped
is a value that can be counted and displayed rather than a branch buried in a worker thread.

Thread-safe, because the crawler runs several workers against one frontier.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional, Set, Tuple

from audit.crawl import urlnorm
from audit.crawl.settings import CrawlSettings


class SkipReason(str, Enum):
    DUPLICATE = "duplicate"
    EXTERNAL = "external"
    TOO_DEEP = "too_deep"
    ROBOTS = "robots"
    EXCLUDED = "excluded"
    NOT_INCLUDED = "not_included"
    BINARY = "binary"
    DOCUMENT = "document"
    BAD_SCHEME = "bad_scheme"
    TRAP = "trap"
    LIMIT_REACHED = "limit_reached"

    @property
    def label(self) -> str:
        return {
            SkipReason.DUPLICATE: "Already seen",
            SkipReason.EXTERNAL: "External site",
            SkipReason.TOO_DEEP: "Beyond crawl depth",
            SkipReason.ROBOTS: "Blocked by robots.txt",
            SkipReason.EXCLUDED: "Matched an exclude pattern",
            SkipReason.NOT_INCLUDED: "Did not match an include pattern",
            SkipReason.BINARY: "Not an HTML page",
            SkipReason.DOCUMENT: "Document (PDFs not included)",
            SkipReason.BAD_SCHEME: "Not an http(s) URL",
            SkipReason.TRAP: "Looks like a crawler trap",
            SkipReason.LIMIT_REACHED: "URL limit reached",
        }[self]


@dataclass(frozen=True)
class QueuedURL:
    url: str
    key: str
    depth: int
    discovered_from: Optional[str] = None


@dataclass
class FrontierStats:
    discovered: int = 0
    queued: int = 0
    taken: int = 0
    skipped: Dict[str, int] = field(default_factory=dict)
    external: Set[str] = field(default_factory=set)

    def note_skip(self, reason: SkipReason) -> None:
        self.skipped[reason.value] = self.skipped.get(reason.value, 0) + 1


class Frontier:
    """Queue of URLs to crawl, with deduplication and scope rules applied on entry."""

    def __init__(
        self,
        root_url: str,
        settings: Optional[CrawlSettings] = None,
        robots=None,
    ) -> None:
        self.settings = settings or CrawlSettings()
        self.robots = robots

        normalised_root = urlnorm.normalise(root_url)
        if normalised_root is None:
            raise ValueError(f"Not a crawlable URL: {root_url!r}")
        self.root_url = normalised_root

        self._lock = threading.Lock()
        self._queue: Deque[QueuedURL] = deque()
        self._seen: Set[str] = set()
        self._in_progress: Set[str] = set()
        self.stats = FrontierStats()

    # --- introspection ---------------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def seen_count(self) -> int:
        with self._lock:
            return len(self._seen)

    @property
    def remaining(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def in_flight(self) -> int:
        with self._lock:
            return len(self._in_progress)

    def is_exhausted(self) -> bool:
        with self._lock:
            return not self._queue and not self._in_progress

    def key_for(self, url: str, base: Optional[str] = None) -> Optional[str]:
        return urlnorm.dedupe_key(url, base, **self.settings.dedupe_options())

    # --- policy ----------------------------------------------------------------

    def classify(
        self, url: str, base: Optional[str] = None, depth: int = 0
    ) -> Tuple[Optional[QueuedURL], Optional[SkipReason]]:
        """Decide whether a URL may be queued. Pure — makes no changes."""
        settings = self.settings

        absolute = urlnorm.normalise(url, base)
        if absolute is None:
            return None, SkipReason.BAD_SCHEME

        if not urlnorm.is_internal(
            absolute, self.root_url, allow_subdomains=settings.crawl_subdomains
        ):
            return None, SkipReason.EXTERNAL

        if urlnorm.looks_like_binary(absolute):
            return None, SkipReason.BINARY

        if urlnorm.looks_like_document(absolute) and not settings.include_pdfs:
            return None, SkipReason.DOCUMENT

        if settings.max_depth is not None and depth > settings.max_depth:
            return None, SkipReason.TOO_DEEP

        if urlnorm.matches_any(absolute, settings.exclude_patterns):
            return None, SkipReason.EXCLUDED

        if settings.include_patterns and not urlnorm.matches_any(
            absolute, settings.include_patterns
        ):
            return None, SkipReason.NOT_INCLUDED

        if urlnorm.looks_like_trap(absolute):
            return None, SkipReason.TRAP

        if settings.respect_robots and self.robots is not None and not self.robots.allows(absolute):
            return None, SkipReason.ROBOTS

        key = self.key_for(absolute)
        if key is None:
            return None, SkipReason.BAD_SCHEME

        return QueuedURL(url=absolute, key=key, depth=depth, discovered_from=base), None

    # --- mutation --------------------------------------------------------------

    def add(
        self, url: str, base: Optional[str] = None, depth: int = 0
    ) -> Tuple[bool, Optional[SkipReason]]:
        """Queue a URL. Returns (queued, reason it was not)."""
        candidate, reason = self.classify(url, base, depth)

        if candidate is None:
            if reason is SkipReason.EXTERNAL:
                absolute = urlnorm.normalise(url, base)
                if absolute:
                    with self._lock:
                        self.stats.external.add(absolute)
            if reason is not None:
                self.stats.note_skip(reason)
            return False, reason

        with self._lock:
            if candidate.key in self._seen:
                self.stats.note_skip(SkipReason.DUPLICATE)
                return False, SkipReason.DUPLICATE

            if len(self._seen) >= self.settings.max_urls:
                self.stats.note_skip(SkipReason.LIMIT_REACHED)
                return False, SkipReason.LIMIT_REACHED

            self._seen.add(candidate.key)
            self._queue.append(candidate)
            self.stats.discovered += 1
            self.stats.queued += 1

        return True, None

    def add_many(self, urls, base: Optional[str] = None, depth: int = 0) -> int:
        return sum(1 for url in urls if self.add(url, base, depth)[0])

    def seed(self, url: Optional[str] = None) -> bool:
        """Queue the starting URL at depth 0, bypassing include-pattern filtering.

        A root that does not match the user's include patterns would otherwise leave the crawl
        with nothing to do.
        """
        target = urlnorm.normalise(url or self.root_url)
        if target is None:
            return False

        key = self.key_for(target)
        if key is None:
            return False

        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            self._queue.append(QueuedURL(url=target, key=key, depth=0))
            self.stats.discovered += 1
            self.stats.queued += 1
        return True

    def take(self) -> Optional[QueuedURL]:
        """Next URL to crawl, or None if the queue is momentarily empty."""
        with self._lock:
            if not self._queue:
                return None
            item = self._queue.popleft()
            self._in_progress.add(item.key)
            self.stats.taken += 1
            return item

    def done(self, item: QueuedURL) -> None:
        with self._lock:
            self._in_progress.discard(item.key)

    def requeue(self, item: QueuedURL) -> None:
        """Put a URL back after a retryable failure, without re-counting it as discovered."""
        with self._lock:
            self._in_progress.discard(item.key)
            self._queue.appendleft(item)

    # --- persistence -----------------------------------------------------------

    def snapshot(self) -> Dict[str, List]:
        """State needed to resume a paused crawl."""
        with self._lock:
            # URLs taken but not finished go back on the queue, or a pause would lose them.
            pending = list(self._queue)
            return {
                "queued": [
                    {
                        "url": q.url,
                        "key": q.key,
                        "depth": q.depth,
                        "discovered_from": q.discovered_from,
                    }
                    for q in pending
                ],
                "in_progress": sorted(self._in_progress),
                "seen": sorted(self._seen),
                "external": sorted(self.stats.external),
            }

    def restore(self, snapshot: Dict[str, List]) -> None:
        with self._lock:
            self._queue.clear()
            for row in snapshot.get("queued", []):
                self._queue.append(
                    QueuedURL(
                        url=row["url"],
                        key=row["key"],
                        depth=int(row.get("depth", 0)),
                        discovered_from=row.get("discovered_from"),
                    )
                )
            self._seen = set(snapshot.get("seen", []))
            self.stats.external = set(snapshot.get("external", []))
            self.stats.discovered = len(self._seen)
            self.stats.queued = len(self._queue)
