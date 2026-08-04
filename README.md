# AI Website QA Platform

AI-powered website QA, design review, content review, and automated bug reporting.

Enter a URL, optionally attach a design file and a content document, and the platform crawls
the site, runs technical audits, applies AI review passes, and produces a client-ready report.

Full product spec: [docs/PRD.md](docs/PRD.md)

---

## Try it in one command

The audit engine in [`audit/`](audit/) is **written against the Python standard library only** —
no `pip install`, no database, no Docker, no API keys. If you have Python 3.9+, it runs.

**Paste URLs into a browser** — starts a local web UI and opens it:

```bash
python -m audit --serve
```

Or straight from the command line:

```bash
python -m audit example.com
```

Produce a self-contained HTML report and open it:

```bash
python -m audit https://example.com --format html --out report.html --open
```

Verify links resolve and measure image weight, then exit non-zero if anything serious turns up
— enough to drop straight into CI:

```bash
python -m audit https://example.com --check-links --check-images --fail-on high
```

**Sample output:** [examples/sample-report.html](examples/sample-report.html) — generated from
the deliberately flawed [examples/sample-page.html](examples/sample-page.html), scoring 45/100
across 21 findings. Regenerate it with `python examples/generate_sample.py`.

<details>
<summary>Full CLI reference</summary>

```
python -m audit <url> [options]
python -m audit --serve [--port N] [--no-browser]

      --serve                    start the local web UI and open a browser
      --port N                   port for --serve (default: 8765; next free port if taken)
      --no-browser               with --serve, do not open a tab automatically
  -f, --format {text,html,json}  output format (default: text)
  -o, --out FILE                 write the report to FILE instead of stdout
      --open                     open the written report in a browser (implies --format html)
      --check-links              verify every link resolves (extra HTTP requests)
      --check-images             measure image transfer sizes (one request per image)
      --image-size-limit MB      flag images heavier than this (default: 2.5)
      --max-links N              cap on links checked (default: 40)
      --content-tags TAGS        tags listed in the content section (default: h1..h6)
      --outline-depth N          nesting depth shown in the structure outline (default: 8)
      --timeout SECONDS          per-request timeout (default: 20)
      --user-agent UA            User-Agent header to send
      --insecure                 skip TLS verification (self-signed staging certs)
      --fail-on SEVERITY         exit 1 if any finding is at least this severe
      --no-color                 disable coloured output
```

Exit codes: `0` clean, `1` findings at or above `--fail-on`, `2` the page could not be audited.

</details>

### The web UI

`--serve` runs a local server built on `http.server` — still no third-party packages. Paste a
URL, choose whether to check links and image sizes, and the same dashboard renders in the
browser.

It also carries a **Schema Generator** page at `/schema`: paste HTML or plain text, pick a
type (or let it auto-detect), and get schema.org JSON-LD back. It reads `Key: value` lines for
specific fields, turns lines ending in `?` into an FAQ, and numbered lines into a how-to.
Supported types: Article, FAQPage, HowTo, Organization, LocalBusiness, Product, Event,
BreadcrumbList, WebPage.

The same rule applies as everywhere else: nothing is invented. Advisory gaps become notes and
the markup is still emitted; a missing **required** property blocks output entirely, because
handing someone invalid structured data with a caveat attached is worse than handing them
nothing.

It binds to `127.0.0.1` only, deliberately: the engine fetches whatever URL it is handed, so
exposing it on a network would be handing out an open request proxy. Non-HTTP schemes
(`file:`, `javascript:`, `data:`, `ftp:`) are rejected before reaching the fetcher, and every
response carries a `Content-Security-Policy` of `default-src 'none'` because reports embed
text taken from the audited page.

---

## Project status

Two layers, at different maturities. Being explicit about which is which:

| Layer | State |
| --- | --- |
| [`audit`](audit/) — static analysis engine, CLI, and web UI | **Working.** SEO, image, link, and image-weight rule packs; dashboard UI; 220 tests |
| [`services/api/`](services/api/) — FastAPI + Celery service | **Scaffold.** Models, schemas, task orchestration, and migrations wired; audit modules are registered stubs |
| [`apps/web/`](apps/web/) — Next.js dashboard | **Scaffold.** Layout, typed API client, and scan form; no report views yet |

The engine is deliberately independent of the service layer. Rule logic that depends on a web
framework, an ORM, or a headless browser can only run in one place; keeping it as plain
functions over a parsed document means the same code serves the CLI, the API worker, and CI.
The service modules in [`services/api/app/modules/`](services/api/app/modules/) are thin
wrappers that persist what the rule packs return.

---

## What the engine checks today

Everything below is derived from the served HTML — no browser required.

**SEO** (`audit/rules/seo.py`) — title presence and length, meta description, `noindex`/`nofollow`
directives, canonical URL, H1 presence and uniqueness, skipped heading levels, empty headings,
`lang` attribute, viewport meta, Open Graph and Twitter Card tags, JSON-LD structured data, thin
content, non-descriptive anchor text.

**Images** (`audit/rules/images.py`) — missing `alt`, explicit `alt=""`, generic alt values
(`image`, `photo`, `logo`, …), overlong alt, unresolvable `src`, absent `width`/`height` (a CLS
cause), legacy PNG/JPEG with no WebP/AVIF alternative, eager loading below the fold, duplicate
sources.

**Links** (`audit/rules/links.py`, opt-in) — broken and unreachable links checked concurrently,
mixed-content images on HTTPS pages, plain-HTTP links.

Each finding carries a stable rule ID, a severity, and a specific fix — not just a label.
Scores start at 100 per pack and deduct by severity; `info` findings never reduce a score.

### Report pages

The report is a dashboard with sidebar navigation. Pages, in order:

| Page | Contents |
| --- | --- |
| **SEO** | Findings from the SEO rule pack |
| **Headings** | Every H1–H6 in document order, indented by level, with line numbers |
| **Meta Tags** | Every `<meta>` element as served — name, property, http-equiv, charset |
| **Canonical URLs** | Declared canonical, whether it is absolute and self-referencing |
| **Alt Tag Missing** | Source URL of every image with no `alt` or an empty one |
| **Image Size** | Images heavier than 2.5 MB (needs `--check-images`) |
| **Index / Follow** | Robots directives from the markup *and* the `X-Robots-Tag` header |
| **Schema** | Generated schema.org JSON-LD, ready to paste |
| **Image Issues** | Remaining image findings — lazy loading, dimensions, formats |
| **Page Structure** | Nested outline of the document's structural elements |
| **Links** | Broken-link findings (only when `--check-links` ran) |

Navigation is **radio inputs plus `:checked` selectors** — no JavaScript, so a saved report
still navigates when opened offline from disk, and the strict Content-Security-Policy holds.
The radios stay keyboard-focusable and exposed to assistive technology, so arrow keys move
between pages; printing reveals every page at once.

A **Dashboard** page leads: overall score ring, four stat cards, per-category meters, a
severity breakdown, and response facts.

Notes on two of them:

- **Image Size** is the only check that fetches subresources, so it is opt-in via
  `--check-images` (the web UI ticks it by default). Sizes come from `Content-Length`; where a
  server omits it, the image is streamed only as far as one byte past the limit — enough to
  answer "is this too big?" without downloading a 40 MB asset to find out. Change the threshold
  with `--image-size-limit 1.5`.
- **Schema** generates Organization, WebPage, BreadcrumbList, and Article or FAQPage when the
  content supports it. Structured data the page already declares is detected so suggestions say
  "merge" rather than duplicating. **No placeholder values are ever emitted** — a field that
  cannot be derived is left out and noted, because markup that describes a page inaccurately is
  worse than none.

### Deliberately not claimed

Lighthouse performance metrics, axe-core accessibility rules, rendered-DOM inspection,
responsive screenshots, AI design review, and content comparison are **specified but not
implemented**. They need a headless browser or a vision model, which is what the service layer
exists for. Both the terminal and HTML reports state this scope in their footer so a report
can't be mistaken for a full audit.

---

## Tests

220 tests, standard library `unittest`, no network access required:

```bash
python -m unittest discover -s tests -t . -v
```

Coverage focuses on the things most likely to break silently: parser edge cases (entities,
headings that wrap links, unclosed `<p>` tags, malformed markup), the boundary between a
missing `alt` attribute and an empty one, score arithmetic, CLI exit codes, URL scheme
validation, and HTML escaping — reports embed page-controlled text, so
[`tests/test_report.py`](tests/test_report.py) audits a hostile fixture and asserts no live
`<script>` or event handler survives into the output.

[`tests/test_server.py`](tests/test_server.py) starts a real server on a free loopback port and
drives it over HTTP, with the audit itself stubbed so the suite stays offline.

---

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  apps/web       │─────▶│  services/api    │─────▶│  Celery workers │
│  Next.js + TS   │ REST │  FastAPI         │ queue│  Playwright     │
│  Tailwind       │◀─────│                  │◀─────│  Lighthouse     │
└─────────────────┘      └──────────────────┘      │  axe-core       │
                                  │                │  AI passes      │
                                  ▼                └────────┬────────┘
                         ┌──────────────────┐               │
                         │ PostgreSQL       │◀──────────────┘
                         │ Redis  ·  S3     │               │
                         └──────────────────┘               ▼
                                                   ┌─────────────────┐
                                                   │  audit/         │
                                                   │  rule engine    │
                                                   │  (stdlib only)  │
                                                   └─────────────────┘
```

Scans are asynchronous: the API accepts a scan request, enqueues it on Redis, and Celery workers
run the crawl and audit modules. The web app polls scan status and renders the report once
results land. The rule engine sits at the bottom with no dependencies pointing outward, so the
CLI reaches it without any of the infrastructure above.

---

## Repository layout

```
audit/                  Dependency-free audit engine, CLI, and web UI
  fetch.py              urllib-based fetching: redirects, gzip, charset detection
  parse.py              html.parser document model and structure tree
  findings.py           Finding dataclass, severity weighting, scoring
  inventory.py          Content listing, structure outline, alt inventory, schema.org
  engine.py             Orchestration and result aggregation
  server.py             http.server web UI for --serve and /schema
  rules/                seo.py · images.py · links.py
  schemagen.py          Standalone content-to-JSON-LD generator
  report/               html.py (dashboard) · pages.py (forms) · theme.py · terminal.py
apps/
  web/                  Next.js 15 + TypeScript + Tailwind front end
services/
  api/                  FastAPI application
    app/
      api/routes/       HTTP endpoints (health, scans, reports)
      models/           SQLAlchemy models
      schemas/          Pydantic request/response schemas
      modules/          Audit modules — one per PRD module
      tasks/            Celery task definitions
    migrations/         Alembic revisions
tests/                  unittest suite for the audit engine
examples/               Sample page, generator script, generated report
docs/PRD.md             Product requirements & technical architecture
docker-compose.yml      PostgreSQL + Redis for local development
```

---

## Running the full service

Only needed to work on the API or the dashboard. The CLI above requires none of it.

### Prerequisites

Node.js 20+, Python 3.11+, Docker.

### 1. Configure environment

```bash
cp .env.example .env
```

Defaults for Postgres and Redis match `docker-compose.yml`. Note that if you run the API
**inside** a container, `localhost` in those URLs must become the Compose service names
(`postgres`, `redis`) — but `NEXT_PUBLIC_API_BASE_URL` must stay host-reachable, since it is
inlined into browser JavaScript at build time.

### 2. Start infrastructure

```bash
docker compose up -d
```

### 3. Install the API and create the schema

```bash
cd services/api && python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

No migrations are committed yet. Generate the initial revision from the models, then apply it:

```bash
cd services/api && .venv/bin/alembic revision --autogenerate -m "initial schema" && .venv/bin/alembic upgrade head
```

On Windows the venv scripts live in `.venv/Scripts/` instead of `.venv/bin/`.

### 4. Run the API

```bash
cd services/api && .venv/bin/uvicorn app.main:app --reload --port 8000
```

API docs at http://localhost:8000/docs.

### 5. Run a Celery worker

```bash
cd services/api && .venv/bin/celery -A app.celery_app worker --loglevel=info
```

On Windows add `--pool=solo`; Celery's default prefork pool does not work there.

### 6. Install browsers for crawling

```bash
cd services/api && .venv/bin/playwright install chromium
```

### 7. Run the web app

```bash
cd apps/web && npm install && npm run dev
```

http://localhost:3000.

---

## Roadmap

Phases follow §22 of the PRD.

- **Phase 1** — Crawl, SEO, accessibility, image audit, Lighthouse performance, PDF export
  *(SEO, image, and link rules done in `audit/`; the rest pending)*
- **Phase 2** — AI design review, AI bug detection, screenshot analysis, QA checklist
- **Phase 3** — Content comparison, document upload, visual regression, team dashboard
- **Phase 4** — Organizations, projects, permissions, history, scheduled scans, notifications
- **Phase 5** — Jira, Slack, GitHub, CI/CD, public API, white label, SSO

A lightweight Chrome extension (PRD §18) ships alongside Phase 2. It only collects the current
page and hands off to the platform — no heavy AI processing in the extension.
