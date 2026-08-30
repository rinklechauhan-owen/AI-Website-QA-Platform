"""Holds the crawls a running server knows about.

Crawls live in memory for the life of the process — there is no database on disk and no login.
That makes eviction a real concern rather than an academic one: without a cap, every crawl a
visitor starts would be retained until the server restarted. Oldest finished crawls are dropped
once the cap is reached, and their storage is closed so the memory is actually released.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from audit.crawl.crawler import Crawler
from audit.crawl.settings import CrawlSettings
from audit.crawl.store import CrawlStore

# Each crawl of 2,000 pages costs roughly 20 MB, so this bounds the process at a few hundred.
DEFAULT_MAX_RETAINED = 8


class CrawlManager:
    """Starts crawls and keeps a bounded number of recent ones available to view."""

    def __init__(self, max_retained: int = DEFAULT_MAX_RETAINED) -> None:
        self.max_retained = max_retained
        self._lock = threading.Lock()
        self._crawls: Dict[int, Crawler] = {}
        self._order: List[int] = []
        self._next_id = 1

    def start(self, root_url: str, settings: Optional[CrawlSettings] = None) -> Crawler:
        """Begin a crawl on a background thread and return it immediately."""
        store = CrawlStore(":memory:")
        crawler = Crawler(root_url, settings or CrawlSettings(), store)

        with self._lock:
            # Session ids come from each crawl's own store, so give the manager its own key.
            key = self._next_id
            self._next_id += 1
            crawler.manager_id = key
            self._crawls[key] = crawler
            self._order.append(key)
            self._evict_locked()

        crawler.start()
        return crawler

    def get(self, key: int) -> Optional[Crawler]:
        with self._lock:
            return self._crawls.get(key)

    def list(self) -> List[Crawler]:
        with self._lock:
            return [self._crawls[k] for k in reversed(self._order) if k in self._crawls]

    def stop_all(self) -> None:
        for crawler in self.list():
            crawler.stop()

    def _evict_locked(self) -> None:
        while len(self._order) > self.max_retained:
            for index, key in enumerate(self._order):
                crawler = self._crawls.get(key)
                if crawler is None or crawler.state.is_finished:
                    self._order.pop(index)
                    dropped = self._crawls.pop(key, None)
                    if dropped is not None:
                        try:
                            dropped.store.close()
                        except Exception:  # noqa: BLE001 - eviction must never raise
                            pass
                    break
            else:
                # Every retained crawl is still running; keep them rather than killing one.
                return
