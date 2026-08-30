"""Site-wide analysis: the findings that only exist once the whole crawl is known.

`rules/seo.py` sees one document at a time by design, so it cannot know that two pages share a
title or that nothing links to a third. Those questions are answered here, after the crawl,
against the stored rows.

Findings use the same :class:`audit.findings.Finding` shape and the same severities as the
per-page rules, so the dashboard, issue filtering and export treat them identically.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from audit.crawl import urlnorm
from audit.crawl.fetcher import status_only
from audit.crawl.settings import CrawlSettings
from audit.crawl.store import CrawlStore
from audit.findings import Finding, Severity

MODULE = "site"

# Below this, a page is likely too thin to rank on its own.
LOW_WORD_COUNT = 200
# A page reachable by this many internal links or fewer is hard for crawlers to find.
LOW_INLINK_COUNT = 1
# Redirect chains at or beyond this waste crawl budget and lose link equity.
LONG_CHAIN_HOPS = 2
# Cap on external links verified, so a page of outbound links cannot dominate the run.
MAX_EXTERNAL_CHECKS = 300
EXTERNAL_WORKERS = 8


@dataclass
class DuplicateGroup:
    value: str
    urls: List[str]

    @property
    def count(self) -> int:
        return len(self.urls)


@dataclass
class BrokenLink:
    target: str
    status: Optional[int]
    internal: bool
    sources: List[str] = field(default_factory=list)

    @property
    def status_label(self) -> str:
        return str(self.status) if self.status else "unreachable"


@dataclass
class RedirectRow:
    url: str
    final_url: str
    hops: int
    status: Optional[int]


@dataclass
class SitemapComparison:
    in_sitemap_not_crawled: List[str] = field(default_factory=list)
    crawled_not_in_sitemap: List[str] = field(default_factory=list)
    sitemap_errors: List[Tuple[str, int]] = field(default_factory=list)
    sitemap_redirects: List[Tuple[str, str]] = field(default_factory=list)
    sitemap_noindex: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)
    checked: bool = False


@dataclass
class SiteReport:
    findings: List[Finding] = field(default_factory=list)
    duplicate_titles: List[DuplicateGroup] = field(default_factory=list)
    duplicate_descriptions: List[DuplicateGroup] = field(default_factory=list)
    duplicate_h1s: List[DuplicateGroup] = field(default_factory=list)
    broken_links: List[BrokenLink] = field(default_factory=list)
    redirects: List[RedirectRow] = field(default_factory=list)
    orphans: List[str] = field(default_factory=list)
    client_rendered: List[str] = field(default_factory=list)
    sitemap: SitemapComparison = field(default_factory=SitemapComparison)
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def broken_internal(self) -> List[BrokenLink]:
        return [link for link in self.broken_links if link.internal]

    @property
    def broken_external(self) -> List[BrokenLink]:
        return [link for link in self.broken_links if not link.internal]


def _finding(rule: str, severity: Severity, title: str, **kwargs) -> Finding:
    return Finding(rule=rule, module=MODULE, severity=severity, title=title, **kwargs)


def _groups(rows) -> List[DuplicateGroup]:
    return [
        DuplicateGroup(value=row["value"], urls=(row["urls"] or "").split("\n")) for row in rows
    ]


# --- individual checks -----------------------------------------------------------------

_DUPLICATE_CHECKS = (
    (
        "title",
        "site.duplicate-title",
        Severity.HIGH,
        "title",
        "duplicate_titles",
        "Two pages competing on the same title split their own ranking signals. Give each page "
        "a title describing what only that page covers.",
    ),
    (
        "meta_description",
        "site.duplicate-meta-description",
        Severity.MEDIUM,
        "meta description",
        "duplicate_descriptions",
        "Search engines usually rewrite duplicated descriptions, so the snippet stops being "
        "something you control. Write one per page.",
    ),
    (
        "h1",
        "site.duplicate-h1",
        Severity.LOW,
        "H1",
        "duplicate_h1s",
        "Repeated H1s usually mean templated pages that have not been given their own subject.",
    ),
)


def _check_duplicates(store: CrawlStore, session_id: int, report: SiteReport) -> None:
    for column, rule, severity, label, attribute, advice in _DUPLICATE_CHECKS:
        groups = _groups(store.duplicates(session_id, column))
        setattr(report, attribute, groups)

        for group in groups:
            preview = group.value if len(group.value) <= 70 else group.value[:69] + "…"
            for url in group.urls:
                others = [other for other in group.urls if other != url]
                report.findings.append(
                    _finding(
                        rule,
                        severity,
                        f"Duplicate {label} shared by {group.count} pages: {preview!r}",
                        detail="Also on: " + ", ".join(others)[:400],
                        recommendation=advice,
                        meta={"value": group.value, "urls": group.urls, "url": url},
                    )
                )


def _check_orphans(store: CrawlStore, session_id: int, report: SiteReport) -> None:
    orphan_rows = store.orphans(session_id)
    report.orphans = [row["url"] for row in orphan_rows]

    for row in orphan_rows:
        # A page found only in the sitemap is a different problem from one found nowhere.
        via_sitemap = bool(row["in_sitemap"])
        report.findings.append(
            _finding(
                "site.orphan-page",
                Severity.MEDIUM,
                f"No internal links point to {row['url']}",
                detail="Discovered through the sitemap only."
                if via_sitemap
                else "Discovered during the crawl, but nothing links to it.",
                recommendation="Link to it from a relevant page. A page nothing links to "
                "receives no internal link equity and is hard for crawlers and visitors to reach.",
                meta={"url": row["url"]},
            )
        )


def _check_inlinks(store: CrawlStore, session_id: int, report: SiteReport) -> None:
    counts = store.inlink_counts(session_id)
    rows = store.rows_where(session_id, "depth > 0 AND status_code >= 200 AND status_code < 300")
    orphaned = set(report.orphans)

    for row in rows:
        inlinks = counts.get(row["url"], 0)
        if inlinks > LOW_INLINK_COUNT or row["url"] in orphaned:
            continue  # Orphans are already reported; do not say it twice.
        report.findings.append(
            _finding(
                "site.few-internal-links",
                Severity.LOW,
                f"Only {inlinks} internal link(s) to {row['url']}",
                recommendation="Pages with very few internal links are crawled less often and "
                "rank less well. Add links from related content.",
                meta={"url": row["url"], "inlinks": inlinks},
            )
        )


def _check_redirects(store: CrawlStore, session_id: int, report: SiteReport) -> None:
    for row in store.redirect_rows(session_id):
        report.redirects.append(
            RedirectRow(
                url=row["url"],
                final_url=row["final_url"] or "",
                hops=row["redirect_hops"],
                status=row["status_code"],
            )
        )
        if row["redirect_hops"] >= LONG_CHAIN_HOPS:
            report.findings.append(
                _finding(
                    "site.redirect-chain",
                    Severity.MEDIUM,
                    f"{row['redirect_hops']} redirects before reaching {row['final_url']}",
                    detail=f"Starting at {row['url']}",
                    recommendation="Point the first URL straight at the final destination. Every "
                    "extra hop costs time and loses a little link equity.",
                    meta={
                        "url": row["url"],
                        "hops": row["redirect_hops"],
                        "final_url": row["final_url"],
                    },
                )
            )

    # Internal links pointing at a URL that redirects: cheap to fix, easy to miss.
    redirecting = sorted({row.url for row in report.redirects})
    for link in store.links_by_target(session_id, redirecting):
        report.findings.append(
            _finding(
                "site.link-to-redirect",
                Severity.LOW,
                f"Link to a redirecting URL: {link['target_url']}",
                detail=f"Linked from {link['source_url']}",
                recommendation="Update the link to the final destination so visitors and "
                "crawlers skip the hop.",
                meta={"url": link["source_url"], "target": link["target_url"]},
            )
        )


def _check_broken_links(
    store: CrawlStore, session_id: int, settings: CrawlSettings, report: SiteReport
) -> None:
    statuses = store.url_status_map(session_id)
    broken: Dict[str, BrokenLink] = {}

    # Internal targets need no extra requests: the crawl already knows their status.
    for row in store.distinct_link_targets(session_id, internal=True):
        target = row["target_url"]
        status = statuses.get(target)
        if status is not None and status >= 400:
            broken[target] = BrokenLink(target=target, status=status, internal=True)

    external_statuses: Dict[str, Optional[int]] = {}
    if settings.check_external_links:
        external = [row["target_url"] for row in store.distinct_link_targets(session_id, False)]
        checked = external[:MAX_EXTERNAL_CHECKS]
        report.stats["external_links_found"] = len(external)
        report.stats["external_links_checked"] = len(checked)
        report.stats["external_links_skipped"] = max(0, len(external) - len(checked))

        if checked:
            def probe(url: str) -> Tuple[str, Optional[int]]:
                status, _ = status_only(
                    url,
                    timeout=min(settings.timeout, 10),
                    user_agent=settings.user_agent,
                    verify_tls=settings.verify_tls,
                )
                return url, status

            with ThreadPoolExecutor(max_workers=min(EXTERNAL_WORKERS, len(checked))) as pool:
                external_statuses = dict(pool.map(probe, checked))

            for url, status in external_statuses.items():
                if status is None or status >= 400:
                    broken[url] = BrokenLink(target=url, status=status, internal=False)

        if external_statuses:
            store.set_link_status(session_id, external_statuses)

    for link in store.links_by_target(session_id, sorted(broken)):
        broken[link["target_url"]].sources.append(link["source_url"])

    report.broken_links = sorted(broken.values(), key=lambda b: (not b.internal, b.target))

    for link in report.broken_links:
        rule = "site.broken-internal-link" if link.internal else "site.broken-external-link"
        severity = Severity.HIGH if link.internal else Severity.MEDIUM
        for source in (link.sources or ["(source not recorded)"])[:50]:
            report.findings.append(
                _finding(
                    rule,
                    severity,
                    f"{link.status_label} — {link.target}",
                    detail=f"Linked from {source}",
                    recommendation="Update or remove the link. Broken links waste crawl budget "
                    "and are among the most visible quality problems to a visitor.",
                    meta={"url": source, "target": link.target, "status": link.status},
                )
            )


def _check_indexability(store: CrawlStore, session_id: int, report: SiteReport) -> None:
    for row in store.rows_where(session_id, "indexable = 0"):
        report.findings.append(
            _finding(
                "site.noindex-page",
                Severity.MEDIUM,
                f"Not indexable: {row['url']}",
                detail=row["robots_directives"] or "",
                recommendation="Correct for thank-you pages and internal search results, and a "
                "serious problem anywhere else. Check this was deliberate.",
                meta={"url": row["url"]},
            )
        )

    for row in store.rows_where(
        session_id,
        "(canonical IS NULL OR canonical = '') AND status_code >= 200 AND status_code < 300",
    ):
        report.findings.append(
            _finding(
                "site.missing-canonical",
                Severity.LOW,
                f"No canonical declared: {row['url']}",
                recommendation="Add a self-referencing canonical so query-string and slash "
                "variants cannot be indexed as separate pages.",
                meta={"url": row["url"]},
            )
        )

    for row in store.rows_where(
        session_id,
        "word_count IS NOT NULL AND word_count < ? AND status_code >= 200 AND status_code < 300",
        (LOW_WORD_COUNT,),
    ):
        report.findings.append(
            _finding(
                "site.low-word-count",
                Severity.LOW,
                f"{row['word_count']} words on {row['url']}",
                recommendation=f"Pages under about {LOW_WORD_COUNT} words rarely rank on their "
                "own. Expand the page, or consolidate it into a stronger one.",
                meta={"url": row["url"], "word_count": row["word_count"]},
            )
        )


def _check_sitemap(
    store: CrawlStore,
    session_id: int,
    settings: CrawlSettings,
    sitemap_report,
    report: SiteReport,
) -> None:
    if sitemap_report is None or not sitemap_report.any_found:
        return

    comparison = report.sitemap
    comparison.checked = True
    comparison.duplicates = list(dict.fromkeys(sitemap_report.duplicate_locs))

    options = settings.dedupe_options()
    sitemap_keys = sitemap_report.url_set(**options)
    crawled = {row["dedupe_key"]: row for row in store.iter_urls(session_id)}

    for key in sorted(sitemap_keys):
        row = crawled.get(key)
        if row is None:
            comparison.in_sitemap_not_crawled.append(key)
            continue
        status = row["status_code"]
        if status is not None and status >= 400:
            comparison.sitemap_errors.append((row["url"], status))
        elif row["redirect_hops"]:
            comparison.sitemap_redirects.append((row["url"], row["final_url"] or ""))
        if row["indexable"] == 0:
            comparison.sitemap_noindex.append(row["url"])

    for key, row in crawled.items():
        status = row["status_code"]
        if key not in sitemap_keys and status is not None and 200 <= status < 300:
            comparison.crawled_not_in_sitemap.append(row["url"])

    for url, status in comparison.sitemap_errors:
        report.findings.append(
            _finding(
                "site.sitemap-url-error",
                Severity.HIGH,
                f"Sitemap lists a URL returning {status}: {url}",
                recommendation="Remove it from the sitemap or fix the page. Submitting broken "
                "URLs erodes trust in the whole sitemap.",
                meta={"url": url, "status": status},
            )
        )

    for url, final in comparison.sitemap_redirects:
        report.findings.append(
            _finding(
                "site.sitemap-url-redirects",
                Severity.MEDIUM,
                f"Sitemap lists a redirecting URL: {url}",
                detail=f"Redirects to {final}",
                recommendation="A sitemap should list final destinations only.",
                meta={"url": url, "final_url": final},
            )
        )

    for url in comparison.sitemap_noindex:
        report.findings.append(
            _finding(
                "site.sitemap-url-noindex",
                Severity.MEDIUM,
                f"Sitemap lists a noindex URL: {url}",
                recommendation="Listing a page you have asked not to be indexed sends "
                "contradictory signals. Remove one or the other.",
                meta={"url": url},
            )
        )

    for url in comparison.crawled_not_in_sitemap[:500]:
        report.findings.append(
            _finding(
                "site.missing-from-sitemap",
                Severity.LOW,
                f"Not in the sitemap: {url}",
                recommendation="Add indexable pages to the sitemap so they are discovered "
                "without relying on internal links alone.",
                meta={"url": url},
            )
        )

    for url in comparison.in_sitemap_not_crawled[:500]:
        report.findings.append(
            _finding(
                "site.sitemap-url-not-reached",
                Severity.LOW,
                f"In the sitemap but not reached by the crawl: {url}",
                recommendation="Either nothing links to it, or the crawl limit stopped first. "
                "Check whether it is reachable.",
                meta={"url": url},
            )
        )


def _check_rendering(store: CrawlStore, session_id: int, report: SiteReport) -> None:
    """Flag pages whose content is assembled in the browser.

    Without this, a client-rendered site reports as having no headings and no content, and an
    SEO team would spend its time fixing findings that describe this tool's blind spot rather
    than the site. The caveat has to travel with the results.
    """
    rows = store.rows_where(session_id, "client_rendered = 1")
    report.client_rendered = [row["url"] for row in rows]

    for row in rows:
        report.findings.append(
            _finding(
                "site.javascript-rendered",
                Severity.HIGH,
                f"Content appears to be rendered in the browser: {row['url']}",
                detail=row["render_note"] or "",
                recommendation="This audit reads the HTML the server sends, which is what a "
                "crawler sees before scripts run. Treat this page's other findings with "
                "caution — missing headings or thin content here may simply be content this "
                "tool cannot see. Confirm with Google Search Console's URL Inspection, which "
                "shows the rendered DOM.",
                meta={"url": row["url"]},
            )
        )


# --- entry point -----------------------------------------------------------------------


def analyse(
    store: CrawlStore,
    session_id: int,
    settings: Optional[CrawlSettings] = None,
    sitemap_report=None,
    persist: bool = True,
) -> SiteReport:
    """Run every site-wide check and, by default, store the findings for issue filtering."""
    settings = settings or CrawlSettings()
    report = SiteReport()

    _check_duplicates(store, session_id, report)
    _check_orphans(store, session_id, report)
    _check_inlinks(store, session_id, report)
    _check_redirects(store, session_id, report)
    _check_broken_links(store, session_id, settings, report)
    _check_indexability(store, session_id, report)
    _check_sitemap(store, session_id, settings, sitemap_report, report)
    _check_rendering(store, session_id, report)

    report.stats.update(
        {
            "duplicate_title_groups": len(report.duplicate_titles),
            "duplicate_description_groups": len(report.duplicate_descriptions),
            "duplicate_h1_groups": len(report.duplicate_h1s),
            "broken_internal": len(report.broken_internal),
            "broken_external": len(report.broken_external),
            "redirects": len(report.redirects),
            "orphans": len(report.orphans),
            "site_findings": len(report.findings),
            "client_rendered": len(report.client_rendered),
        }
    )

    if persist:
        # Recomputed wholesale, so the previous pass is cleared rather than appended to.
        store.clear_issues_for_module(session_id, MODULE)
        by_url: Dict[str, List[Finding]] = {}
        for finding in report.findings:
            by_url.setdefault(str(finding.meta.get("url", "")), []).append(finding)

        options = settings.dedupe_options()
        for url, findings in by_url.items():
            row = None
            if url:
                key = urlnorm.dedupe_key(url, **options) or url
                row = store.get_url_by_key(session_id, key)
            store.add_issues(session_id, row["id"] if row else None, url, findings)

    return report
