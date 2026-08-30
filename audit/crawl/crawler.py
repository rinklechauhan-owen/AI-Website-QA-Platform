"""The crawl loop.

Pulls URLs from the frontier, fetches them, and hands each response to
:func:`audit.engine.audit_response` — the same function the single-page audit calls. The
crawler decides *what* to analyse; it never decides *how*, so one URL and two thousand get
identical results.

Three properties the brief calls out, and where they are enforced:

* **One bad page never stops the crawl.** Every fetch, parse and analysis step is wrapped;
  a failure becomes a stored row with an error and the loop continues.
* **Nothing accumulates in memory.** Each page is written to the store and released. The
  stored result is trimmed — enough for the tables and the detail view, without holding a
  full outline for every page.
* **The interface stays responsive.** The crawl runs on worker threads and exposes a
  snapshot of progress that can be read at any moment without locking the workers.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from audit.crawl import robots as robots_module
from audit.crawl import siterules
from audit.crawl import sitemap as sitemap_module
from audit.crawl import urlnorm
from audit.crawl.fetcher import FetchOutcome, fetch_page
from audit.crawl.frontier import Frontier, QueuedURL
from audit.crawl.settings import CrawlSettings
from audit.crawl.store import CrawlStore
from audit.engine import audit_response
from audit.findings import Severity


class CrawlState(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_finished(self) -> bool:
        return self in (CrawlState.STOPPED, CrawlState.COMPLETED, CrawlState.FAILED)

    @property
    def label(self) -> str:
        return {
            CrawlState.IDLE: "Not started",
            CrawlState.PREPARING: "Reading robots.txt and sitemaps",
            CrawlState.RUNNING: "Crawling",
            CrawlState.PAUSED: "Paused",
            CrawlState.STOPPING: "Stopping",
            CrawlState.STOPPED: "Stopped",
            CrawlState.COMPLETED: "Completed",
            CrawlState.FAILED: "Failed",
        }[self]


@dataclass
class CrawlProgress:
    """A snapshot for the progress screen. Plain values — safe to read mid-crawl."""

    session_id: int
    root_url: str
    state: CrawlState = CrawlState.IDLE
    max_urls: int = 0
    discovered: int = 0
    crawled: int = 0
    remaining: int = 0
    in_flight: int = 0
    errors: int = 0
    warnings: int = 0
    redirects: int = 0
    current_url: str = ""
    started_at: Optional[float] = None
    elapsed_s: float = 0.0
    message: str = ""

    @property
    def percent(self) -> float:
        target = min(self.max_urls, self.discovered) or self.max_urls
        if not target:
            return 0.0
        return round(min(100.0, self.crawled / target * 100), 1)

    @property
    def urls_per_second(self) -> float:
        if not self.elapsed_s or not self.crawled:
            return 0.0
        return round(self.crawled / self.elapsed_s, 2)

    @property
    def eta_seconds(self) -> Optional[int]:
        rate = self.urls_per_second
        if not rate or self.state is not CrawlState.RUNNING:
            return None
        outstanding = min(self.max_urls - self.crawled, self.remaining + self.in_flight)
        return int(outstanding / rate) if outstanding > 0 else 0

    @property
    def eta_label(self) -> str:
        seconds = self.eta_seconds
        if seconds is None:
            return "—"
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"

    @property
    def bar(self, width: int = 20) -> str:
        filled = int(round(self.percent / 100 * width))
        return "█" * filled + "░" * (width - filled)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "root_url": self.root_url,
            "state": self.state.value,
            "state_label": self.state.label,
            "max_urls": self.max_urls,
            "discovered": self.discovered,
            "crawled": self.crawled,
            "remaining": self.remaining,
            "in_flight": self.in_flight,
            "errors": self.errors,
            "warnings": self.warnings,
            "redirects": self.redirects,
            "current_url": self.current_url,
            "percent": self.percent,
            "urls_per_second": self.urls_per_second,
            "eta_seconds": self.eta_seconds,
            "elapsed_s": round(self.elapsed_s, 1),
            "message": self.message,
        }


class Renderer:
    """Seam for JavaScript rendering.

    The default returns nothing, so the crawler uses the served HTML. A headless-browser
    renderer can be supplied without the crawler changing, and without the project taking on
    a browser dependency it does not otherwise need.
    """

    def render(self, url: str, timeout: int) -> Optional[str]:  # pragma: no cover - seam
        return None


def _first_heading(document) -> str:
    headings = document.headings_at(1) if document else []
    return headings[0].text if headings else ""


def _word_count(document) -> int:
    return sum(block.word_count for block in document.blocks) if document else 0


def compact_result(result) -> Dict[str, Any]:
    """Trim an AuditResult for storage.

    The full payload carries a structure outline of up to 400 nodes per page; keeping that for
    2,000 pages would cost hundreds of megabytes for data the crawl tables never read. What is
    kept is enough for the URL detail view; the full single-page report is one click away and
    re-runs the existing audit live.
    """
    payload = result.to_dict()
    inventory = payload.get("inventory")
    if isinstance(inventory, dict):
        inventory.pop("outline", None)
        content = inventory.get("content")
        if isinstance(content, dict):
            content.pop("blocks", None)
    return payload


class Crawler:
    """Crawls a site, analysing every page with the existing audit engine."""

    def __init__(
        self,
        root_url: str,
        settings: Optional[CrawlSettings] = None,
        store: Optional[CrawlStore] = None,
        renderer: Optional[Renderer] = None,
        session_id: Optional[int] = None,
    ) -> None:
        self.settings = settings or CrawlSettings()
        # Defaults to an in-memory database: a crawl is a working set, not saved data.
        self.store = store or CrawlStore(":memory:")
        self.renderer = renderer

        normalised = urlnorm.normalise(root_url)
        if normalised is None:
            raise ValueError(f"Not a crawlable URL: {root_url!r}")
        self.root_url = normalised

        self.robots: Optional[robots_module.RobotsTxt] = None
        self.site_report: Optional[siterules.SiteReport] = None
        self.sitemap: Optional[sitemap_module.SitemapReport] = None
        self.frontier = Frontier(self.root_url, self.settings)

        self.session_id = session_id or self.store.create_session(
            self.root_url, self.settings.to_json()
        )

        self._state = CrawlState.IDLE
        self._prepared = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._threads: List[threading.Thread] = []
        self._started_at: Optional[float] = None
        self._finished_at: Optional[float] = None
        self._current_url = ""
        self._crawled = 0
        self._errors = 0
        self._warnings = 0
        self._redirects = 0
        self._message = ""

    # --- progress --------------------------------------------------------------

    @property
    def state(self) -> CrawlState:
        with self._lock:
            return self._state

    def _set_state(self, state: CrawlState, message: str = "") -> None:
        with self._lock:
            self._state = state
            if message:
                self._message = message

    @property
    def progress(self) -> CrawlProgress:
        with self._lock:
            state = self._state
            started = self._started_at
            finished = self._finished_at
            elapsed = ((finished or time.monotonic()) - started) if started else 0.0
            return CrawlProgress(
                session_id=self.session_id,
                root_url=self.root_url,
                state=state,
                max_urls=self.settings.max_urls,
                discovered=self.frontier.stats.discovered,
                crawled=self._crawled,
                remaining=self.frontier.remaining,
                in_flight=self.frontier.in_flight,
                errors=self._errors,
                warnings=self._warnings,
                redirects=self._redirects,
                current_url=self._current_url,
                started_at=started,
                elapsed_s=elapsed,
                message=self._message,
            )

    # --- controls --------------------------------------------------------------

    def pause(self) -> None:
        if self.state is CrawlState.RUNNING:
            self._pause.set()
            self._set_state(CrawlState.PAUSED)
            self.store.save_frontier(self.session_id, self.frontier.snapshot())
            self.store.update_session(self.session_id, status="paused")

    def resume(self) -> None:
        if self.state is CrawlState.PAUSED:
            self._pause.clear()
            self._set_state(CrawlState.RUNNING)
            self.store.update_session(self.session_id, status="running")

    def stop(self) -> None:
        """Ask the crawl to finish. Workers notice between pages, never mid-write."""
        if not self.state.is_finished:
            self._set_state(CrawlState.STOPPING)
        self._stop.set()
        self._pause.clear()

    # --- preparation -----------------------------------------------------------

    def prepare(self) -> None:
        """Read robots.txt and sitemaps before the first page is fetched.

        Idempotent, so a caller may prepare, adjust the frontier, and then run without the
        preparation happening twice.
        """
        if self._prepared:
            return
        self._prepared = True
        self._set_state(CrawlState.PREPARING)

        self.robots = robots_module.load(
            self.root_url,
            user_agent=self.settings.user_agent,
            timeout=self.settings.timeout,
            verify_tls=self.settings.verify_tls,
        )
        self.frontier.robots = self.robots
        self.store.update_session(
            self.session_id,
            robots_json=_json({
                "url": self.robots.url,
                "found": self.robots.found,
                "status": self.robots.status,
                "summary": self.robots.summary(),
                "sitemaps": self.robots.sitemaps,
                "rules": [str(rule) for rule in self.robots.rules],
                "crawl_delay": self.robots.crawl_delay,
            }),
        )

        if self.settings.discover_sitemaps:
            self.sitemap = sitemap_module.discover(
                self.root_url,
                from_robots=self.robots.sitemaps,
                user_agent=self.settings.user_agent,
                timeout=self.settings.timeout,
                verify_tls=self.settings.verify_tls,
            )
            self.store.update_session(self.session_id, sitemap_json=_json(self.sitemap.to_dict()))

        self.frontier.seed()

        if self.sitemap and self.settings.crawl_sitemap_urls:
            for entry in self.sitemap.entries:
                self.frontier.add(entry.loc, depth=1)

    # --- the loop --------------------------------------------------------------

    def run(self) -> CrawlProgress:
        """Crawl to completion. Blocking; use :meth:`start` for a background crawl."""
        try:
            self.prepare()
        except Exception as exc:  # noqa: BLE001 - preparation must not raise into the caller
            self._set_state(CrawlState.FAILED, f"Preparation failed: {exc}")
            self.store.update_session(self.session_id, status="failed", error=str(exc))
            return self.progress

        with self._lock:
            self._started_at = time.monotonic()
            self._state = CrawlState.RUNNING
        self.store.update_session(self.session_id, status="running")

        workers = max(1, min(self.settings.concurrency, self.settings.max_urls))
        self._threads = [
            threading.Thread(target=self._worker, name=f"crawl-{i}", daemon=True)
            for i in range(workers)
        ]
        for thread in self._threads:
            thread.start()
        for thread in self._threads:
            thread.join()

        return self._finish()

    def start(self) -> None:
        """Run the crawl on a background thread so an interface stays responsive."""
        thread = threading.Thread(target=self.run, name="crawl-runner", daemon=True)
        thread.start()
        self._runner = thread

    def wait(self, timeout: Optional[float] = None) -> None:
        runner = getattr(self, "_runner", None)
        if runner is not None:
            runner.join(timeout)

    def _finish(self) -> CrawlProgress:
        with self._lock:
            self._finished_at = time.monotonic()
            if self._state is CrawlState.STOPPING or self._stop.is_set():
                self._state = CrawlState.STOPPED
            elif self._state is CrawlState.RUNNING:
                self._state = CrawlState.COMPLETED

        self.store.update_session(
            self.session_id, urls_discovered=self.frontier.stats.discovered
        )
        if self.sitemap:
            self._mark_sitemap_coverage()

        # Site-wide analysis runs last, because duplicate titles and orphan pages are only
        # knowable once every page has been seen. A failure here must not lose the crawl.
        try:
            self.site_report = siterules.analyse(
                self.store, self.session_id, self.settings, self.sitemap
            )
        except Exception as exc:  # noqa: BLE001 - the crawl results still stand
            self._message = f"Site-wide analysis failed: {exc}"

        self.store.finish_session(
            self.session_id,
            status="stopped" if self.state is CrawlState.STOPPED else "completed",
        )
        return self.progress

    def _mark_sitemap_coverage(self) -> None:
        keys = self.sitemap.url_set(**self.settings.dedupe_options())
        if keys:
            self.store.mark_in_sitemap(self.session_id, keys)

    def _worker(self) -> None:
        idle_since: Optional[float] = None

        while not self._stop.is_set():
            if self._pause.is_set():
                time.sleep(0.1)
                continue

            if self._crawled >= self.settings.max_urls:
                return

            item = self.frontier.take()
            if item is None:
                if self.frontier.is_exhausted():
                    return
                # Another worker is still fetching and may queue more URLs.
                idle_since = idle_since or time.monotonic()
                if time.monotonic() - idle_since > 120:
                    return  # A stuck peer must not hang the crawl forever.
                time.sleep(0.05)
                continue

            idle_since = None
            try:
                self._process(item)
            except Exception as exc:  # noqa: BLE001 - the crawl outlives any single page
                self._record_failure(item, f"{exc.__class__.__name__}: {exc}")
            finally:
                self.frontier.done(item)
                if self.settings.delay_ms:
                    time.sleep(self.settings.delay_ms / 1000)

    # --- per-page --------------------------------------------------------------

    def _process(self, item: QueuedURL) -> None:
        with self._lock:
            self._current_url = item.url

        outcome = self._fetch_with_retries(item)

        if outcome.error or outcome.response is None:
            self._record_failure(item, outcome.error or "no response", outcome)
            return

        response = outcome.response
        if outcome.redirected:
            with self._lock:
                self._redirects += 1

        html_like = "html" in (response.headers.get("content-type", "") or "").lower()

        result = None
        if response.status < 400 and html_like and response.body:
            try:
                result = audit_response(
                    response,
                    item.url,
                    # Link checking is site-wide in a crawl: the graph already knows every
                    # URL's status, so per-page checking would repeat the same requests.
                    check_links=False,
                    check_images=self.settings.check_image_sizes,
                    image_size_limit=self.settings.image_size_limit,
                )
            except Exception as exc:  # noqa: BLE001 - a parse failure is a finding, not a crash
                self._record_failure(item, f"Analysis failed: {exc}", outcome)
                return

        self._store_page(item, outcome, result)

        if result is not None and result.document is not None:
            self._queue_links(item, result.document)

    def _fetch_with_retries(self, item: QueuedURL) -> FetchOutcome:
        attempts = self.settings.max_retries + 1
        outcome = FetchOutcome(error="not attempted")

        for attempt in range(attempts):
            if self._stop.is_set():
                break
            outcome = fetch_page(
                item.url,
                timeout=self.settings.timeout,
                user_agent=self.settings.user_agent,
                verify_tls=self.settings.verify_tls,
                follow_redirects=self.settings.follow_redirects,
            )
            if outcome.ok:
                return outcome
            if attempt < attempts - 1:
                time.sleep(min(2 ** attempt * 0.25, 2.0))

        return outcome

    def _store_page(self, item: QueuedURL, outcome: FetchOutcome, result) -> None:
        response = outcome.response
        document = result.document if result is not None else None
        inventory = result.inventory if result is not None else None
        findings = result.findings if result is not None else []

        warnings = sum(
            1 for f in findings if f.severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM)
        )

        record = {
            "url": item.url,
            "dedupe_key": item.key,
            "depth": item.depth,
            "discovered_from": item.discovered_from,
            "status_code": response.status if response else None,
            "final_url": response.url if response else None,
            "redirect_hops": outcome.hops,
            "content_type": (response.headers.get("content-type") if response else None),
            "response_ms": response.elapsed_ms if response else None,
            "byte_size": response.byte_size if response else None,
            "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "issue_count": len(findings),
            "score": result.overall_score if result is not None else None,
            "result_json": _json(compact_result(result)) if result is not None else None,
        }

        if document is not None:
            record.update(
                {
                    "title": document.title or "",
                    "title_length": len(document.title or ""),
                    "meta_description": document.meta("description") or "",
                    "meta_length": len(document.meta("description") or ""),
                    "h1": _first_heading(document),
                    "h1_count": len(document.headings_at(1)),
                    "canonical": document.canonical or "",
                    "word_count": _word_count(document),
                    "internal_links": len(document.internal_links()),
                    "external_links": len(document.external_links()),
                    "images": len(document.images),
                    "missing_alt": sum(1 for i in document.images if i.alt_state != "present"),
                    "hreflang": ",".join(
                        sorted({tag.get("hreflang", "") for tag in document.hreflang})
                    )
                    if getattr(document, "hreflang", None)
                    else "",
                }
            )

        if inventory is not None:
            record["indexable"] = 1 if inventory.index_follow.indexable else 0
            record["robots_directives"] = inventory.index_follow.summary
            record["schema_types"] = ",".join(inventory.schema.existing_types)

        url_id = self.store.add_url(self.session_id, record)
        if findings:
            self.store.add_issues(self.session_id, url_id, item.url, findings)

        with self._lock:
            self._crawled += 1
            self._warnings += warnings
            if response and response.status >= 400:
                self._errors += 1

    def _record_failure(
        self, item: QueuedURL, error: str, outcome: Optional[FetchOutcome] = None
    ) -> None:
        """A page that could not be fetched or analysed still gets a row.

        Dropping it would lose the evidence that the URL is broken, which is precisely the
        thing an SEO audit is looking for.
        """
        self.store.add_url(
            self.session_id,
            {
                "url": item.url,
                "dedupe_key": item.key,
                "depth": item.depth,
                "discovered_from": item.discovered_from,
                "status_code": outcome.response.status if outcome and outcome.response else None,
                "redirect_hops": outcome.hops if outcome else 0,
                "error": error[:500],
                "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        )
        with self._lock:
            self._crawled += 1
            self._errors += 1

    def _queue_links(self, item: QueuedURL, document) -> None:
        rows: List[Dict[str, Any]] = []
        depth = item.depth + 1

        for link in document.links:
            absolute = urlnorm.normalise(link.href, item.url)
            if absolute is None:
                continue

            internal = urlnorm.is_internal(
                absolute, self.root_url, allow_subdomains=self.settings.crawl_subdomains
            )
            rows.append(
                {
                    "source_url": item.url,
                    "target_url": absolute,
                    "is_internal": internal,
                    "anchor_text": (link.text or "")[:300],
                    "rel": link.rel or "",
                }
            )
            # Offered to the frontier whatever its origin: it queues internal URLs and
            # records external ones, so the external-link list comes from one place.
            self.frontier.add(absolute, base=item.url, depth=depth)

        if rows:
            self.store.add_links(self.session_id, rows)


def _json(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "{}"


def crawl(
    root_url: str,
    settings: Optional[CrawlSettings] = None,
    store: Optional[CrawlStore] = None,
) -> Crawler:
    """Run a crawl to completion and return the crawler holding its results."""
    crawler = Crawler(root_url, settings, store)
    crawler.run()
    return crawler
