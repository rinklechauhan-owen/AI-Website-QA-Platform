"""Crawl storage, on `sqlite3` from the standard library.

**In memory by default — nothing is written to disk.** A crawl is a working set that lives as
long as the tool is open and then disappears; CSV export is how results leave. There are no
accounts and no login anywhere in the tool.

Storage is still needed while a crawl runs: 2,000 pages cannot sit in a browser, and they are
written incrementally rather than accumulated in Python objects, so tables can be read a page
at a time without a large crawl blocking the interface. SQLite's in-memory mode gives that for
no dependency and no file. Measured on a real 2,000-page crawl: 19.7 MB, 10.1 KB per page.

Rows carry both flat columns and the full ``AuditResult`` JSON. The columns let tables sort,
filter and aggregate in SQL; the JSON lets the URL detail view re-render a page exactly as the
single-page audit would, with no second fetch.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

SCHEMA_VERSION = 1

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crawl_session (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    root_url         TEXT    NOT NULL,
    label            TEXT,
    started_at       TEXT    NOT NULL,
    finished_at      TEXT,
    status           TEXT    NOT NULL DEFAULT 'running',
    settings_json    TEXT    NOT NULL DEFAULT '{}',
    robots_json      TEXT    NOT NULL DEFAULT '{}',
    sitemap_json     TEXT    NOT NULL DEFAULT '{}',
    urls_crawled     INTEGER NOT NULL DEFAULT 0,
    urls_discovered  INTEGER NOT NULL DEFAULT 0,
    health_score     REAL,
    error            TEXT
);

CREATE TABLE IF NOT EXISTS crawl_url (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER NOT NULL REFERENCES crawl_session(id) ON DELETE CASCADE,
    url               TEXT    NOT NULL,
    dedupe_key        TEXT    NOT NULL,
    depth             INTEGER NOT NULL DEFAULT 0,
    discovered_from   TEXT,
    status_code       INTEGER,
    final_url         TEXT,
    redirect_hops     INTEGER NOT NULL DEFAULT 0,
    content_type      TEXT,
    response_ms       INTEGER,
    byte_size         INTEGER,
    title             TEXT,
    title_length      INTEGER,
    meta_description  TEXT,
    meta_length       INTEGER,
    h1                TEXT,
    h1_count          INTEGER,
    canonical         TEXT,
    indexable         INTEGER,
    robots_directives TEXT,
    word_count        INTEGER,
    internal_links    INTEGER,
    external_links    INTEGER,
    images            INTEGER,
    missing_alt       INTEGER,
    hreflang          TEXT,
    schema_types      TEXT,
    score             REAL,
    issue_count       INTEGER NOT NULL DEFAULT 0,
    in_sitemap        INTEGER NOT NULL DEFAULT 0,
    error             TEXT,
    audited_at        TEXT,
    result_json       TEXT,
    UNIQUE (session_id, dedupe_key)
);

CREATE TABLE IF NOT EXISTS crawl_link (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES crawl_session(id) ON DELETE CASCADE,
    source_url    TEXT    NOT NULL,
    target_url    TEXT    NOT NULL,
    is_internal   INTEGER NOT NULL DEFAULT 1,
    anchor_text   TEXT,
    rel           TEXT,
    status_code   INTEGER
);

CREATE TABLE IF NOT EXISTS crawl_issue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES crawl_session(id) ON DELETE CASCADE,
    url_id      INTEGER REFERENCES crawl_url(id) ON DELETE CASCADE,
    url         TEXT    NOT NULL,
    rule        TEXT    NOT NULL,
    module      TEXT    NOT NULL,
    severity    TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    detail      TEXT
);

CREATE TABLE IF NOT EXISTS crawl_frontier (
    session_id  INTEGER NOT NULL REFERENCES crawl_session(id) ON DELETE CASCADE,
    payload     TEXT    NOT NULL,
    saved_at    TEXT    NOT NULL,
    PRIMARY KEY (session_id)
);

CREATE INDEX IF NOT EXISTS ix_url_session      ON crawl_url(session_id);
CREATE INDEX IF NOT EXISTS ix_url_status       ON crawl_url(session_id, status_code);
CREATE INDEX IF NOT EXISTS ix_url_title        ON crawl_url(session_id, title);
CREATE INDEX IF NOT EXISTS ix_url_meta         ON crawl_url(session_id, meta_description);
CREATE INDEX IF NOT EXISTS ix_url_h1           ON crawl_url(session_id, h1);
CREATE INDEX IF NOT EXISTS ix_url_depth        ON crawl_url(session_id, depth);
CREATE INDEX IF NOT EXISTS ix_issue_session    ON crawl_issue(session_id, rule);
CREATE INDEX IF NOT EXISTS ix_issue_severity   ON crawl_issue(session_id, severity);
CREATE INDEX IF NOT EXISTS ix_link_source      ON crawl_link(session_id, source_url);
CREATE INDEX IF NOT EXISTS ix_link_target      ON crawl_link(session_id, target_url);
"""

# Columns a results table may sort by. Anything else is rejected, because a sort column has to
# be interpolated into SQL and must never come straight from a query string.
SORTABLE_COLUMNS = frozenset(
    {
        "url", "depth", "status_code", "title", "title_length", "meta_length",
        "h1_count", "word_count", "internal_links", "external_links", "images",
        "missing_alt", "score", "issue_count", "response_ms", "byte_size",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SessionRow:
    id: int
    root_url: str
    started_at: str
    status: str
    urls_crawled: int
    urls_discovered: int
    finished_at: Optional[str] = None
    health_score: Optional[float] = None
    label: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self.status in ("running", "paused")


class CrawlStore:
    """SQLite-backed crawl storage. Safe to use from several worker threads."""

    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        # check_same_thread=False plus an explicit lock: the crawler writes from a pool.
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()

        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "CrawlStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _query(self, sql: str, params: Sequence = ()) -> List[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params))

    def _query_one(self, sql: str, params: Sequence = ()) -> Optional[sqlite3.Row]:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    # --- sessions --------------------------------------------------------------

    def create_session(
        self, root_url: str, settings_json: str = "{}", label: Optional[str] = None
    ) -> int:
        with self._write() as conn:
            cursor = conn.execute(
                "INSERT INTO crawl_session(root_url, label, started_at, status, settings_json) "
                "VALUES (?, ?, ?, 'running', ?)",
                (root_url, label, _now(), settings_json),
            )
            return int(cursor.lastrowid)

    def update_session(self, session_id: int, **fields: Any) -> None:
        allowed = {
            "status", "finished_at", "urls_crawled", "urls_discovered", "health_score",
            "robots_json", "sitemap_json", "error", "label",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{k} = ?" for k in updates)
        with self._write() as conn:
            conn.execute(
                f"UPDATE crawl_session SET {assignments} WHERE id = ?",
                (*updates.values(), session_id),
            )

    def finish_session(self, session_id: int, status: str = "completed") -> None:
        counts = self.status_breakdown(session_id)
        self.update_session(
            session_id,
            status=status,
            finished_at=_now(),
            urls_crawled=sum(counts.values()),
            health_score=self.health_score(session_id),
        )

    def get_session(self, session_id: int) -> Optional[SessionRow]:
        row = self._query_one("SELECT * FROM crawl_session WHERE id = ?", (session_id,))
        return self._to_session(row) if row else None

    def list_sessions(self, limit: int = 50) -> List[SessionRow]:
        rows = self._query(
            "SELECT * FROM crawl_session ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [self._to_session(r) for r in rows]

    @staticmethod
    def _to_session(row: sqlite3.Row) -> SessionRow:
        return SessionRow(
            id=row["id"],
            root_url=row["root_url"],
            started_at=row["started_at"],
            status=row["status"],
            urls_crawled=row["urls_crawled"],
            urls_discovered=row["urls_discovered"],
            finished_at=row["finished_at"],
            health_score=row["health_score"],
            label=row["label"],
            error=row["error"],
        )

    def session_settings_json(self, session_id: int) -> str:
        row = self._query_one("SELECT settings_json FROM crawl_session WHERE id = ?", (session_id,))
        return row["settings_json"] if row else "{}"

    # --- urls ------------------------------------------------------------------

    # Columns declared NOT NULL: passing an explicit None would be rejected, because a
    # column DEFAULT only applies when the column is left out of the statement entirely.
    _NOT_NULL_DEFAULTS = {"depth": 0, "redirect_hops": 0, "issue_count": 0, "in_sitemap": 0}

    def add_url(self, session_id: int, record: Dict[str, Any]) -> int:
        """Write one crawled URL. Re-crawling the same key updates the existing row."""
        columns = [
            "url", "dedupe_key", "depth", "discovered_from", "status_code", "final_url",
            "redirect_hops", "content_type", "response_ms", "byte_size", "title",
            "title_length", "meta_description", "meta_length", "h1", "h1_count",
            "canonical", "indexable", "robots_directives", "word_count", "internal_links",
            "external_links", "images", "missing_alt", "hreflang", "schema_types",
            "score", "issue_count", "in_sitemap", "error", "audited_at", "result_json",
        ]
        values = []
        for name in columns:
            value = record.get(name)
            if value is None and name in self._NOT_NULL_DEFAULTS:
                value = self._NOT_NULL_DEFAULTS[name]
            values.append(value)
        placeholders = ", ".join("?" for _ in columns)
        assignments = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "dedupe_key")

        with self._write() as conn:
            cursor = conn.execute(
                f"INSERT INTO crawl_url(session_id, {', '.join(columns)}) "
                f"VALUES (?, {placeholders}) "
                f"ON CONFLICT(session_id, dedupe_key) DO UPDATE SET {assignments}",
                (session_id, *values),
            )
            if cursor.lastrowid:
                return int(cursor.lastrowid)

        row = self._query_one(
            "SELECT id FROM crawl_url WHERE session_id = ? AND dedupe_key = ?",
            (session_id, record.get("dedupe_key")),
        )
        return int(row["id"]) if row else 0

    def count_urls(self, session_id: int, where: str = "", params: Sequence = ()) -> int:
        clause = f" AND {where}" if where else ""
        row = self._query_one(
            f"SELECT COUNT(*) AS n FROM crawl_url WHERE session_id = ?{clause}",
            (session_id, *params),
        )
        return int(row["n"]) if row else 0

    def urls_page(
        self,
        session_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
        sort: str = "url",
        descending: bool = False,
        where: str = "",
        params: Sequence = (),
        search: str = "",
    ) -> List[sqlite3.Row]:
        """One page of results. Never returns the whole crawl."""
        if sort not in SORTABLE_COLUMNS:
            sort = "url"
        direction = "DESC" if descending else "ASC"

        clauses: List[str] = []
        values: List[Any] = [session_id]
        if where:
            clauses.append(f"({where})")
            values.extend(params)
        if search:
            clauses.append("(url LIKE ? OR title LIKE ? OR meta_description LIKE ?)")
            pattern = f"%{search}%"
            values.extend([pattern, pattern, pattern])

        condition = (" AND " + " AND ".join(clauses)) if clauses else ""
        return self._query(
            f"SELECT * FROM crawl_url WHERE session_id = ?{condition} "
            f"ORDER BY {sort} {direction}, id ASC LIMIT ? OFFSET ?",
            (*values, limit, offset),
        )

    def iter_urls(self, session_id: int, batch: int = 500) -> Iterator[sqlite3.Row]:
        """Stream every row without holding the crawl in memory — used by CSV export."""
        offset = 0
        while True:
            rows = self._query(
                "SELECT * FROM crawl_url WHERE session_id = ? ORDER BY id LIMIT ? OFFSET ?",
                (session_id, batch, offset),
            )
            if not rows:
                return
            yield from rows
            offset += batch

    def get_url(self, session_id: int, url_id: int) -> Optional[sqlite3.Row]:
        return self._query_one(
            "SELECT * FROM crawl_url WHERE session_id = ? AND id = ?", (session_id, url_id)
        )

    def get_url_by_key(self, session_id: int, key: str) -> Optional[sqlite3.Row]:
        return self._query_one(
            "SELECT * FROM crawl_url WHERE session_id = ? AND dedupe_key = ?", (session_id, key)
        )

    def result_for(self, session_id: int, url_id: int) -> Optional[Dict[str, Any]]:
        row = self.get_url(session_id, url_id)
        if not row or not row["result_json"]:
            return None
        try:
            return json.loads(row["result_json"])
        except ValueError:
            return None

    def mark_in_sitemap(self, session_id: int, keys: Iterable[str]) -> int:
        keys = list(keys)
        if not keys:
            return 0
        with self._write() as conn:
            conn.executemany(
                "UPDATE crawl_url SET in_sitemap = 1 WHERE session_id = ? AND dedupe_key = ?",
                [(session_id, key) for key in keys],
            )
        return len(keys)

    # --- links -----------------------------------------------------------------

    def add_links(self, session_id: int, rows: Iterable[Dict[str, Any]]) -> None:
        payload = [
            (
                session_id,
                r.get("source_url"),
                r.get("target_url"),
                1 if r.get("is_internal", True) else 0,
                r.get("anchor_text"),
                r.get("rel"),
                r.get("status_code"),
            )
            for r in rows
        ]
        if not payload:
            return
        with self._write() as conn:
            conn.executemany(
                "INSERT INTO crawl_link(session_id, source_url, target_url, is_internal, "
                "anchor_text, rel, status_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
                payload,
            )

    def links_to(self, session_id: int, target_url: str) -> List[sqlite3.Row]:
        return self._query(
            "SELECT * FROM crawl_link WHERE session_id = ? AND target_url = ?",
            (session_id, target_url),
        )

    def inlink_counts(self, session_id: int) -> Dict[str, int]:
        rows = self._query(
            "SELECT target_url, COUNT(*) AS n FROM crawl_link "
            "WHERE session_id = ? AND is_internal = 1 GROUP BY target_url",
            (session_id,),
        )
        return {row["target_url"]: int(row["n"]) for row in rows}

    # --- issues ----------------------------------------------------------------

    def add_issues(self, session_id: int, url_id: Optional[int], url: str, findings) -> None:
        payload = [
            (
                session_id,
                url_id,
                url,
                f.rule,
                f.module.value if hasattr(f.module, "value") else str(f.module),
                f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                f.title,
                f.detail,
            )
            for f in findings
        ]
        if not payload:
            return
        with self._write() as conn:
            conn.executemany(
                "INSERT INTO crawl_issue(session_id, url_id, url, rule, module, severity, "
                "title, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                payload,
            )

    def issue_summary(self, session_id: int) -> List[sqlite3.Row]:
        """Every distinct issue with how many URLs it affects — the dashboard's issue list."""
        return self._query(
            "SELECT rule, module, severity, MIN(title) AS title, COUNT(DISTINCT url) AS urls "
            "FROM crawl_issue WHERE session_id = ? GROUP BY rule, module, severity "
            "ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
            "WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, urls DESC",
            (session_id,),
        )

    def urls_with_issue(
        self, session_id: int, rule: str, limit: int = 200, offset: int = 0
    ) -> List[sqlite3.Row]:
        return self._query(
            "SELECT DISTINCT i.url, u.status_code, u.title, u.id AS url_id "
            "FROM crawl_issue i LEFT JOIN crawl_url u "
            "  ON u.session_id = i.session_id AND u.url = i.url "
            "WHERE i.session_id = ? AND i.rule = ? ORDER BY i.url LIMIT ? OFFSET ?",
            (session_id, rule, limit, offset),
        )

    def count_urls_with_issue(self, session_id: int, rule: str) -> int:
        row = self._query_one(
            "SELECT COUNT(DISTINCT url) AS n FROM crawl_issue WHERE session_id = ? AND rule = ?",
            (session_id, rule),
        )
        return int(row["n"]) if row else 0

    def severity_counts(self, session_id: int) -> Dict[str, int]:
        rows = self._query(
            "SELECT severity, COUNT(*) AS n FROM crawl_issue WHERE session_id = ? "
            "GROUP BY severity",
            (session_id,),
        )
        return {row["severity"]: int(row["n"]) for row in rows}

    # --- aggregates ------------------------------------------------------------

    def status_breakdown(self, session_id: int) -> Dict[str, int]:
        """Counts by status class — the 2xx/3xx/4xx/5xx dashboard cards."""
        rows = self._query(
            "SELECT status_code, COUNT(*) AS n FROM crawl_url WHERE session_id = ? "
            "GROUP BY status_code",
            (session_id,),
        )
        buckets = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "failed": 0}
        for row in rows:
            code = row["status_code"]
            count = int(row["n"])
            if code is None:
                buckets["failed"] += count
            elif 200 <= code < 300:
                buckets["2xx"] += count
            elif 300 <= code < 400:
                buckets["3xx"] += count
            elif 400 <= code < 500:
                buckets["4xx"] += count
            elif code >= 500:
                buckets["5xx"] += count
        return buckets

    def duplicates(self, session_id: int, column: str, minimum: int = 2) -> List[sqlite3.Row]:
        """Values shared by more than one URL — duplicate titles, descriptions, H1s."""
        if column not in ("title", "meta_description", "h1", "canonical"):
            raise ValueError(f"Not a duplicate-checkable column: {column!r}")
        return self._query(
            f"SELECT {column} AS value, COUNT(*) AS n, GROUP_CONCAT(url, char(10)) AS urls "
            f"FROM crawl_url WHERE session_id = ? AND {column} IS NOT NULL AND {column} != '' "
            f"AND status_code >= 200 AND status_code < 300 "
            f"GROUP BY {column} HAVING COUNT(*) >= ? ORDER BY n DESC",
            (session_id, minimum),
        )

    def health_score(self, session_id: int) -> float:
        """Mean per-page score across pages that returned a document."""
        row = self._query_one(
            "SELECT AVG(score) AS avg FROM crawl_url "
            "WHERE session_id = ? AND score IS NOT NULL",
            (session_id,),
        )
        return round(float(row["avg"]), 1) if row and row["avg"] is not None else 0.0

    def depth_breakdown(self, session_id: int) -> Dict[int, int]:
        rows = self._query(
            "SELECT depth, COUNT(*) AS n FROM crawl_url WHERE session_id = ? "
            "GROUP BY depth ORDER BY depth",
            (session_id,),
        )
        return {int(row["depth"]): int(row["n"]) for row in rows}

    def orphans(self, session_id: int) -> List[sqlite3.Row]:
        """Crawled pages nothing links to, other than the entry point."""
        return self._query(
            "SELECT u.* FROM crawl_url u WHERE u.session_id = ? AND u.depth > 0 AND NOT EXISTS ("
            "  SELECT 1 FROM crawl_link l WHERE l.session_id = u.session_id "
            "  AND l.is_internal = 1 AND l.target_url = u.url) ORDER BY u.url",
            (session_id,),
        )

    # --- frontier persistence --------------------------------------------------

    def save_frontier(self, session_id: int, snapshot: Dict[str, Any]) -> None:
        with self._write() as conn:
            conn.execute(
                "INSERT INTO crawl_frontier(session_id, payload, saved_at) VALUES (?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET payload = excluded.payload, "
                "saved_at = excluded.saved_at",
                (session_id, json.dumps(snapshot), _now()),
            )

    def load_frontier(self, session_id: int) -> Optional[Dict[str, Any]]:
        row = self._query_one(
            "SELECT payload FROM crawl_frontier WHERE session_id = ?", (session_id,)
        )
        if not row:
            return None
        try:
            return json.loads(row["payload"])
        except ValueError:
            return None

    # --- maintenance -----------------------------------------------------------

    def delete_session(self, session_id: int) -> None:
        with self._write() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for table in ("crawl_issue", "crawl_link", "crawl_url", "crawl_frontier"):
                conn.execute(f"DELETE FROM {table} WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM crawl_session WHERE id = ?", (session_id,))

    # --- site-wide queries -----------------------------------------------------

    def url_status_map(self, session_id: int) -> Dict[str, Optional[int]]:
        """Every crawled URL and the status it returned, keyed by both requested and final URL.

        Broken-link detection reads this instead of re-requesting pages the crawl already
        fetched, which is what keeps link checking from doubling the request count.
        """
        statuses: Dict[str, Optional[int]] = {}
        for row in self._query(
            "SELECT url, final_url, status_code FROM crawl_url WHERE session_id = ?",
            (session_id,),
        ):
            statuses[row["url"]] = row["status_code"]
            if row["final_url"]:
                statuses.setdefault(row["final_url"], row["status_code"])
        return statuses

    def distinct_link_targets(self, session_id: int, internal: Optional[bool] = None):
        clause = "" if internal is None else " AND is_internal = ?"
        params = (session_id,) if internal is None else (session_id, 1 if internal else 0)
        return self._query(
            "SELECT target_url, COUNT(*) AS n, MIN(source_url) AS example_source "
            f"FROM crawl_link WHERE session_id = ?{clause} "
            "GROUP BY target_url ORDER BY n DESC",
            params,
        )

    def links_by_target(self, session_id: int, targets: Sequence[str]):
        """Source pages for a set of target URLs, so a broken link names who links to it."""
        if not targets:
            return []
        rows = []
        # Chunked to stay under SQLite's variable limit on large crawls.
        for start in range(0, len(targets), 400):
            chunk = list(targets[start : start + 400])
            placeholders = ",".join("?" for _ in chunk)
            rows.extend(
                self._query(
                    f"SELECT source_url, target_url, anchor_text FROM crawl_link "
                    f"WHERE session_id = ? AND target_url IN ({placeholders})",
                    (session_id, *chunk),
                )
            )
        return rows

    def redirect_rows(self, session_id: int):
        return self._query(
            "SELECT * FROM crawl_url WHERE session_id = ? AND redirect_hops > 0 "
            "ORDER BY redirect_hops DESC, url",
            (session_id,),
        )

    def rows_where(self, session_id: int, where: str, params: Sequence = (), limit: int = 5000):
        return self._query(
            f"SELECT * FROM crawl_url WHERE session_id = ? AND {where} ORDER BY url LIMIT ?",
            (session_id, *params, limit),
        )

    def set_link_status(self, session_id: int, statuses: Dict[str, Optional[int]]) -> None:
        if not statuses:
            return
        with self._write() as conn:
            conn.executemany(
                "UPDATE crawl_link SET status_code = ? WHERE session_id = ? AND target_url = ?",
                [(status, session_id, url) for url, status in statuses.items()],
            )

    def clear_issues_for_module(self, session_id: int, module: str) -> None:
        """Site-wide findings are recomputed wholesale, so the previous run is cleared first."""
        with self._write() as conn:
            conn.execute(
                "DELETE FROM crawl_issue WHERE session_id = ? AND module = ?",
                (session_id, module),
            )
