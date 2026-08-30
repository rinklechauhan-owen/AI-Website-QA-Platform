# Upgrade Plan — Single-Page Audit → Full Website Crawler

Analysis of the existing project and the plan to extend it to a 2,000-URL website crawler
**without changing how the current single-page audit behaves**.

Written before any code was changed.

---

## 1. Current architecture

The audit engine is a layered pipeline with dependencies pointing in one direction. Nothing in
it knows about a web framework, an ORM, or a browser.

```
audit_url(url, ...)                    ← the public entry point today
   │
   ├── fetch(url) ─────────────► Response(url, status, body, headers, elapsed_ms, byte_size)
   │
   └── audit_response(response, requested_url, ...)   ← ★ the reuse seam
          │
          ├── parse(body, url) ──► Document
          │                        title, lang, metas, canonical, headings, blocks,
          │                        images, links, jsonld, structure tree, text_length
          │
          ├── rules/seo.run(doc)      ─┐
          ├── rules/images.run(doc)    ├─► [Finding]  +  stats  ──► PackResult(score)
          ├── rules/links.run(doc)     │   (opt-in, network)
          ├── assets.run(doc)         ─┘   (opt-in, network)
          │
          ├── inventory.build(doc, headers) ──► PageInventory
          │       content · outline · images · schema · metas · canonical · index_follow
          │
          └──────────────────────────► AuditResult
                                          packs · document · inventory · image_sizes · headers
                                          .findings .overall_score .counts .page_title
```

`AuditResult` is then rendered by `report/html.py` (dashboard), `report/terminal.py`, or
serialised with `.to_dict()` for JSON.

### The single most important finding

```python
def audit_url(url, ...):
    response = fetch(url, ...)          # ← fetching is already separated
    return audit_response(response, url, ...)
```

**`audit_response()` takes an already-fetched `Response`.** It was split out originally so
tests could supply fixtures without network access. That same seam is exactly what a crawler
needs: the crawler must fetch each page anyway in order to extract its links, so it can pass
the `Response` it already holds straight into `audit_response()`.

**Consequence: no refactor of the audit engine is required, and `audit_url()` is not touched
at all.** Mode A cannot regress, because none of its code changes.

```
Mode A   audit_url()  ──► fetch ──┐
                                  ├──► audit_response() ──► AuditResult
Mode B   crawler      ──► fetch ──┘         (identical analysis for 1 URL or 2,000)
```

### Storage today

There is **none**. The engine is stateless: audit, render, discard. `services/api/` contains
SQLAlchemy models (`Scan`, `Page`, `Finding`) but that layer is scaffold and its audit modules
are stubs. Nothing persists.

---

## 2. Existing functionality (must all keep working)

| # | Feature | Where |
| --- | --- | --- |
| 1 | Single-page audit, `audit_url()` | `engine.py` |
| 2 | 38 detection rules — 21 SEO, 11 image, 4 link, 2 HTTP | `rules/`, `assets.py` |
| 3 | HTTP fetching: redirects, gzip/deflate, charset detection | `fetch.py` |
| 4 | Tolerant HTML parsing into a `Document` | `parse.py` |
| 5 | Severity weighting and 0–100 scoring; info never deducts | `findings.py` |
| 6 | Heading listing (H1–H6) | `inventory.py` |
| 7 | Structure outline with depth and node caps | `inventory.py` |
| 8 | Meta tag listing | `inventory.py` |
| 9 | Canonical analysis (absolute, self-referencing) | `inventory.py` |
| 10 | Index/follow from markup **and** `X-Robots-Tag` | `inventory.py` |
| 11 | Image alt inventory with coverage % | `inventory.py` |
| 12 | schema.org suggestion from the page | `inventory.py` |
| 13 | Image weight measurement, 2.5 MB threshold | `assets.py` |
| 14 | Link checking (broken, mixed content) | `rules/links.py` |
| 15 | Schema Generator, 9 types, blocking-warning rule | `schemagen.py` |
| 16 | HTML dashboard, 11 pages, sidebar nav, no JavaScript | `report/html.py` |
| 17 | Terminal report with ASCII transliteration | `report/terminal.py` |
| 18 | JSON output | `AuditResult.to_dict()` |
| 19 | CLI: 18 flags, exit codes 0/1/2 | `cli.py` |
| 20 | Web UI: `/`, `/audit`, `/schema`, `/health` | `server.py` |
| 21 | Design system: Montserrat, brand palette, logo, type scale | `report/theme.py` |
| 22 | Security posture: loopback bind, scheme allow-list, CSP, zero scripts | `server.py` |
| 23 | 241 tests | `tests/` |

**Reusable by the crawler with no modification:** 1–14, 16–18, 21, 22. That is nearly
everything. The crawler is a *scheduler around* the existing engine, not a second engine.

---

## 3. What needs to be added

| Area | Requirement |
| --- | --- |
| Crawl loop | Frontier queue, visited set, depth tracking, concurrency, stop conditions |
| URL normalisation | Scheme, trailing slash, fragments, query params, case, encoding, duplicates |
| robots.txt | Fetch, parse, obey `Disallow`/`Allow`, read `Sitemap:` directives, `Crawl-delay` |
| Sitemaps | Discover, parse (incl. sitemap indexes), compare against crawled URLs |
| Site-wide rules | Duplicate titles/descriptions/H1s, orphan pages, redirect chains, broken-link sources |
| Redirect analysis | Chains, loops, hop counts, final destination |
| Persistence | Crawl sessions, per-URL rows, incremental writes, pagination, resume |
| Site dashboard | Summary cards, severity roll-up, health score |
| Data tables | Sort, filter, search, paginate, column visibility, export |
| Issue filtering | Click an issue → the affected URLs only |
| URL detail view | Per-page report reusing the existing single-page rendering |
| Export | CSV (Excel-compatible), per-issue and full |
| Crawl controls | Settings panel, live progress, pause/resume/stop |

---

## 4. Files to modify (deliberately few)

| File | Change | Risk |
| --- | --- | --- |
| `cli.py` | Add `--crawl` and crawl flags. Existing flags untouched. | Low |
| `server.py` | Add crawl routes. Existing routes untouched. | Low |
| `report/pages.py` | Add mode chooser to the form; add crawl screens. | Low |
| `report/theme.py` | Add CSS for tables, progress bar, filter chips. Tokens unchanged. | Low |
| `rules/seo.py` | **No change.** Site-wide duplicate rules go in a new pack. | — |
| `engine.py` | **No change.** | — |
| `fetch.py` | **No change.** | — |
| `parse.py` | **No change.** | — |
| `inventory.py` | **No change.** | — |
| `report/html.py` | **No change** to `render()`. | — |

The four files that change are all additive. Nothing existing is rewritten.

---

## 5. New files

```
audit/crawl/
  __init__.py
  urlnorm.py      URL normalisation, internal/external classification, canonical resolution
  robots.py       robots.txt fetch, parse, allow/deny, sitemap discovery
  sitemap.py      sitemap.xml and sitemap-index parsing, URL extraction
  frontier.py     the queue: dedupe, depth, include/exclude patterns, ordering
  settings.py     CrawlSettings dataclass, defaults, validation
  store.py        SQLite persistence: sessions, pages, links, issues; paginated reads
  crawler.py      the crawl loop: concurrency, retries, rate limiting, pause/stop
  siterules.py    site-wide rule pack: duplicates, orphans, redirect chains, broken links
  export.py       CSV writers for full crawl and per-issue subsets

audit/report/
  crawl_pages.py  crawl screens: settings, live progress, dashboard, tables, URL detail

tests/
  test_urlnorm.py · test_robots.py · test_sitemap.py · test_frontier.py
  test_store.py · test_crawler.py · test_siterules.py · test_export.py
```

---

## 6. Storage

**Decision: `sqlite3` from the standard library, in memory only.**

> **Revised after stage 1.** You asked for no database and no login. Nothing is written to
> disk and no file is created: the store opens with `:memory:`, so a crawl is a working set
> that lives as long as the tool is open and then disappears. CSV export is how results
> leave. There are no accounts, no sessions and no authentication anywhere in the tool.
>
> A crawl still needs *somewhere* to put 2,000 pages while it runs — they cannot sit in a
> browser, and the brief requires paginated, memory-conscious reads. SQLite's in-memory mode
> provides that with no dependency and no file. Measured on a real 2,000-page crawl: **19.7 MB
> total, 10.1 KB per page**, with Python-level allocation peaking at 1.8 MB.

The project's defining property is zero third-party dependencies. `sqlite3` ships with Python,
so persistence can be added without breaking that. It also happens to be the right tool:

| Requirement (from the brief) | How SQLite satisfies it |
| --- | --- |
| 2,000 pages without loading all into memory | Rows written incrementally, read by page |
| Don't freeze the UI | Query `LIMIT/OFFSET` per table page |
| Several crawls open at once in one process | One row per session |
| Pause/resume without restarting | The frontier lives in the DB, not in RAM |
| Prepare for crawl comparison | Two sessions in one file, joinable by URL |
| Sorting, filtering, searching | `ORDER BY`, `WHERE`, indexes |

### Schema

```sql
crawl_session(id, root_url, started_at, finished_at, status, settings_json,
              urls_crawled, urls_discovered, health_score)

crawl_url(id, session_id, url, normalised_url, depth, status_code, final_url,
          redirect_hops, content_type, response_ms, byte_size,
          title, title_length, meta_description, meta_length,
          h1, h1_count, canonical, indexable, robots_directives,
          word_count, internal_links, external_links, images, missing_alt,
          hreflang, schema_types, error, audited_at, result_json)

crawl_link(id, session_id, source_url_id, target_url, is_internal,
           status_code, anchor_text, rel)

crawl_issue(id, session_id, url_id, rule, module, severity, title, detail)

crawl_frontier(id, session_id, url, depth, state)      -- queued | active | done
```

`result_json` holds the full `AuditResult.to_dict()` so the URL detail view can re-render a
page exactly as a single-page audit would, with no re-fetch. The flat columns exist so tables
can sort and filter without deserialising 2,000 JSON blobs.

Indexes on `(session_id, status_code)`, `(session_id, title)`, `(session_id, meta_description)`,
`(session_id, h1)` — the last three make duplicate detection a `GROUP BY` rather than an
in-memory scan.

**No change to the `services/api/` SQLAlchemy models.** They stay as they are; the crawl store
is a separate, self-contained concern that a future service layer can read.

---

## 7. Implementation plan — six stages

Each stage ends with tests, and with the existing 241 tests re-run to prove Mode A is intact.

| Stage | Delivers | Verification |
| --- | --- | --- |
| **1. Foundation** | `urlnorm`, `robots`, `sitemap`, `frontier`, `settings`, `store` | Unit tests; no engine files touched |
| **2. Crawl loop** | `crawler.py` — concurrency, retries, rate limit, depth, stop/pause, incremental writes | Crawl a local fixture site; 500-URL synthetic run |
| **3. Site-wide analysis** | `siterules.py` — duplicates, orphans, redirect chains, broken-link sources, sitemap comparison | Fixture sites with each defect |
| **4. Reporting** | `crawl_pages.py` — dashboard, tables, issue filtering, URL detail | Rendered output asserted; no scripts |
| **5. Interfaces** | CLI `--crawl`; server crawl routes, settings, live progress, pause/stop | Real crawl driven through a browser |
| **6. Export & sessions** | CSV export, session list, prior-crawl viewing | Round-trip export tests |

### Reuse map

```
                    ┌──────────────────┐
Mode A: audit_url ──┤                  │
                    │  audit_response  │──► AuditResult ──► existing renderers
Mode B: crawler ────┤                  │         │
                    └──────────────────┘         └──► store.write() ──► site dashboard
```

Site-wide rules are a **new pack** (`siterules.py`) emitting the same `Finding` objects with
the same severities. They cannot live in `rules/seo.py` because that pack sees one document at
a time by design, and changing its signature would risk Mode A.

---

## 8. Risks

| # | Risk | Mitigation |
| --- | --- | --- |
| 1 | **Breaking the single-page audit** | `engine.py`, `fetch.py`, `parse.py`, `inventory.py`, `rules/` are not modified. The 241 existing tests are the regression gate and are re-run at every stage. |
| 2 | **Live progress needs JavaScript** — but the report is script-free by design, CSP-enforced and test-asserted | Progress page uses `<meta http-equiv="refresh">` polling; pause/stop are form POSTs. Zero scripts, no CSP change. Trade-off: a full repaint every ~2s rather than a smooth counter. Noted as a deliberate choice; relaxing it later means allowing script on that one page only, never in the downloadable report. |
| 3 | **JavaScript rendering needs a headless browser** — a large third-party dependency that breaks the project's core property | Build the extension point (a renderer interface, HTML-only by default) and document how to plug Playwright in. **Do not add the dependency.** Flagged explicitly rather than silently skipped — see below. |
| 4 | Crawling hammers a live site | Concurrency cap (default 5), per-request delay, `Crawl-delay` honoured, robots.txt respected by default, timeouts, retry with backoff. |
| 5 | Memory growth over 2,000 pages | Nothing accumulates in RAM: each page is written to SQLite and released. Tables read by page. |
| 6 | Crawler traps — infinite calendars, faceted params, session IDs | Normalisation strips known tracking params; depth cap; max-URL cap; repeated-path-segment detection. |
| 7 | One bad page killing the crawl | Every fetch and parse is wrapped; failures are recorded as rows and the loop continues. Explicit acceptance criterion, explicitly tested. |
| 8 | A 2,000-row HTML table freezing the browser | Server-side pagination, default 100 rows per page. The full set is only ever materialised in CSV export, streamed. |
| 9 | Report file size at scale | The crawl dashboard is a *served* view backed by SQLite, not one giant self-contained file. Single-page reports stay self-contained as now. |
| 10 | Scope: this is a large build | Six stages, each independently testable, each leaving the tool working. |

### Two items that need a decision from you

**JavaScript rendering (brief §22).** Every other requirement can be met with the standard
library. This one cannot — it needs Chromium via Playwright (~300 MB), which ends "no install,
no dependencies, runs anywhere Python does". I plan to build the seam and leave it unpopulated,
so enabling it later is a config change rather than a rewrite. Say if you would rather I take
the dependency now.

**Live progress smoothness.** Meta-refresh polling keeps the zero-script guarantee but repaints
the page every couple of seconds. A smooth counter needs ~30 lines of JavaScript on the progress
page only. I default to zero-script; tell me if you prefer the smoother version.

Neither blocks Stage 1, which is why implementation starts now.
