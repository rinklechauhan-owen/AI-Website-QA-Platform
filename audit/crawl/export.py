"""CSV export.

Streamed rather than assembled in memory: a 2,000-row export builds one row at a time, so the
export costs no more memory than a single page does. CSV is written with a UTF-8 BOM because
Excel misreads accented characters without one, and "Excel-compatible" was the requirement.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from audit.crawl.store import CrawlStore

# The Screaming-Frog-style column set from the brief, in the order it lists them.
URL_COLUMNS: List[tuple] = [
    ("url", "URL"),
    ("status_code", "Status Code"),
    ("error", "Status"),
    ("indexable", "Indexability"),
    ("robots_directives", "Robots Directives"),
    ("title", "Title"),
    ("title_length", "Title Length"),
    ("meta_description", "Meta Description"),
    ("meta_length", "Meta Length"),
    ("h1", "H1"),
    ("h1_count", "H1 Count"),
    ("canonical", "Canonical"),
    ("word_count", "Word Count"),
    ("internal_links", "Internal Links"),
    ("external_links", "External Links"),
    ("images", "Images"),
    ("missing_alt", "Missing ALT"),
    ("hreflang", "Hreflang"),
    ("schema_types", "Schema"),
    ("depth", "Crawl Depth"),
    ("redirect_hops", "Redirect Hops"),
    ("final_url", "Final URL"),
    ("response_ms", "Response (ms)"),
    ("byte_size", "Size (bytes)"),
    ("content_type", "Content Type"),
    ("in_sitemap", "In Sitemap"),
    ("score", "Score"),
    ("issue_count", "Issues"),
    ("discovered_from", "Discovered From"),
]

BOM = "﻿"


def _writer() -> tuple:
    buffer = io.StringIO()
    return buffer, csv.writer(buffer, lineterminator="\r\n")


def _flush(buffer: io.StringIO) -> str:
    value = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    return value


def _cell(row, column: str) -> Any:
    value = row[column] if column in row.keys() else ""
    if column == "indexable":
        return "" if value is None else ("Indexable" if value else "Non-Indexable")
    if column == "in_sitemap":
        return "Yes" if value else "No"
    if column == "error":
        return value or "OK"
    return "" if value is None else value


def urls_csv(store: CrawlStore, session_id: int) -> Iterator[str]:
    """Every crawled URL, streamed a row at a time."""
    buffer, writer = _writer()
    writer.writerow([label for _, label in URL_COLUMNS])
    yield BOM + _flush(buffer)

    for row in store.iter_urls(session_id):
        writer.writerow([_cell(row, column) for column, _ in URL_COLUMNS])
        yield _flush(buffer)


def issue_csv(store: CrawlStore, session_id: int, rule: str) -> Iterator[str]:
    """The URLs affected by one issue — the export beside a filtered issue view."""
    buffer, writer = _writer()
    writer.writerow(["URL", "Status Code", "Title", "Issue", "Detail"])
    yield BOM + _flush(buffer)

    offset = 0
    while True:
        rows = store.urls_with_issue(session_id, rule, limit=500, offset=offset)
        if not rows:
            return
        for row in rows:
            writer.writerow(
                [
                    row["url"],
                    row["status_code"] if "status_code" in row.keys() else "",
                    row["title"] if "title" in row.keys() else "",
                    rule,
                    "",
                ]
            )
            yield _flush(buffer)
        offset += len(rows)


def issues_csv(store: CrawlStore, session_id: int) -> Iterator[str]:
    """Every issue on every URL."""
    buffer, writer = _writer()
    writer.writerow(["URL", "Rule", "Module", "Severity", "Issue", "Detail"])
    yield BOM + _flush(buffer)

    for summary in store.issue_summary(session_id):
        rule = summary["rule"]
        offset = 0
        while True:
            rows = store.urls_with_issue(session_id, rule, limit=500, offset=offset)
            if not rows:
                break
            for row in rows:
                writer.writerow(
                    [
                        row["url"],
                        rule,
                        summary["module"],
                        summary["severity"],
                        summary["title"],
                        "",
                    ]
                )
                yield _flush(buffer)
            offset += len(rows)


def links_csv(store: CrawlStore, session_id: int, broken_only: bool = False) -> Iterator[str]:
    """The link graph, optionally limited to links that resolve to an error."""
    buffer, writer = _writer()
    writer.writerow(["Source", "Target", "Type", "Anchor Text", "Rel", "Status"])
    yield BOM + _flush(buffer)

    statuses = store.url_status_map(session_id)
    for row in store._query(  # noqa: SLF001 - streaming read, deliberately not paginated twice
        "SELECT * FROM crawl_link WHERE session_id = ? ORDER BY source_url", (session_id,)
    ):
        status = row["status_code"] or statuses.get(row["target_url"])
        if broken_only and not (status is None or status >= 400):
            continue
        writer.writerow(
            [
                row["source_url"],
                row["target_url"],
                "Internal" if row["is_internal"] else "External",
                row["anchor_text"] or "",
                row["rel"] or "",
                status if status is not None else "unreachable",
            ]
        )
        yield _flush(buffer)


EXPORTS: Dict[str, Dict[str, Any]] = {
    "urls": {"label": "All URLs", "filename": "crawl-urls.csv", "fn": urls_csv},
    "issues": {"label": "All issues", "filename": "crawl-issues.csv", "fn": issues_csv},
    "links": {"label": "All links", "filename": "crawl-links.csv", "fn": links_csv},
    "broken-links": {
        "label": "Broken links",
        "filename": "crawl-broken-links.csv",
        "fn": lambda store, session_id: links_csv(store, session_id, broken_only=True),
    },
}


def export(store: CrawlStore, session_id: int, kind: str, rule: str = "") -> Iterator[str]:
    """Stream one of the named exports, or the URLs affected by a single rule."""
    if rule:
        return issue_csv(store, session_id, rule)
    entry = EXPORTS.get(kind)
    if entry is None:
        raise ValueError(f"Unknown export: {kind!r}")
    return entry["fn"](store, session_id)


def filename_for(kind: str, rule: str = "") -> str:
    if rule:
        return f"{rule.replace('.', '-')}.csv"
    entry = EXPORTS.get(kind)
    return entry["filename"] if entry else "crawl.csv"


def collect(chunks: Iterable[str]) -> str:
    """Join a stream into one string. For tests and small exports only."""
    return "".join(chunks)
