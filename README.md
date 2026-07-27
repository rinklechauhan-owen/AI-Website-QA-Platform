# AI Website QA Platform

AI-powered website QA, design review, content review, and automated bug reporting.

Enter a URL, optionally attach a design file and a content document, and the platform crawls
the site, runs technical audits, applies AI review passes, and produces a client-ready report.

Full product spec: [docs/PRD.md](docs/PRD.md)

> **Status: scaffold.** Repository structure, tooling, and configuration are in place.
> The audit modules are stubbed — see [Roadmap](#roadmap) and
> [services/api/app/modules/README.md](services/api/app/modules/README.md).

---

## What it reports on

| Area | Coverage |
| --- | --- |
| SEO | Titles, meta, canonical, OG/Twitter, robots, sitemap, heading hierarchy, schema, links |
| Accessibility | axe-core rules, labels, ARIA, contrast, focus states, keyboard nav, landmarks |
| Performance | Lighthouse scores, Core Web Vitals (LCP, CLS, INP, FCP, TTFB, SI, TBT) |
| Images | Missing/empty/generic alt, WebP + AVIF opportunities, oversized assets, lazy loading |
| Design | AI review of full-page screenshots — alignment, spacing, typography, hierarchy |
| Content | Live site vs. uploaded document — missing sections, changed CTAs, grammar, tone |
| Bugs | Overflow, horizontal scroll, 404 assets, console errors, API failures, overlap |
| Responsive | 11 breakpoints from 320px to 1920px, screenshot + layout diff per width |
| Forms | Required fields, validation rules, submit path, success and error states |
| QA Checklist | Auto-generated per-page pass/fail checklist |

---

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  apps/web       │─────▶│  services/api    │─────▶│  Celery workers │
│  Next.js + TS   │ REST │  FastAPI         │ queue│  Playwright     │
│  Tailwind       │◀─────│                  │◀─────│  Lighthouse     │
└─────────────────┘      └──────────────────┘      │  axe-core       │
                                  │                │  AI passes      │
                                  ▼                └─────────────────┘
                         ┌──────────────────┐               │
                         │ PostgreSQL       │◀──────────────┘
                         │ Redis  ·  S3     │
                         └──────────────────┘
```

Scans are asynchronous: the API accepts a scan request, enqueues it on Redis, and Celery
workers run the crawl and audit modules. The web app polls scan status and renders the
report once results land.

---

## Repository layout

```
apps/
  web/                  Next.js 15 + TypeScript + Tailwind front end
    app/                App Router pages and layouts
    components/         UI components
    lib/                API client, shared helpers
services/
  api/                  FastAPI application
    app/
      api/routes/       HTTP endpoints (health, scans, reports)
      models/           SQLAlchemy models
      schemas/          Pydantic request/response schemas
      modules/          Audit modules — one per PRD module
      tasks/            Celery task definitions
    migrations/         Alembic revisions
docs/
  PRD.md                Product requirements & technical architecture
docker-compose.yml      PostgreSQL + Redis for local development
```

---

## Getting started

### Prerequisites

- Node.js 20+
- Python 3.11+
- Docker (for PostgreSQL and Redis)

### 1. Configure environment

```bash
cp .env.example .env
```

Fill in `OPENAI_API_KEY` and, if you are using screenshot storage, the `S3_*` values.
The defaults for Postgres and Redis match `docker-compose.yml`.

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

API docs are served at http://localhost:8000/docs.

### 5. Run a Celery worker

```bash
cd services/api && .venv/bin/celery -A app.celery_app worker --loglevel=info
```

### 6. Install browsers for crawling

```bash
cd services/api && .venv/bin/playwright install chromium
```

### 7. Run the web app

```bash
cd apps/web && npm install && npm run dev
```

The app is served at http://localhost:3000.

---

## Roadmap

Phases follow §22 of the PRD.

- **Phase 1** — Crawl, SEO, accessibility, image audit, Lighthouse performance, PDF export
- **Phase 2** — AI design review, AI bug detection, screenshot analysis, QA checklist
- **Phase 3** — Content comparison, document upload, visual regression, team dashboard
- **Phase 4** — Organizations, projects, permissions, history, scheduled scans, notifications
- **Phase 5** — Jira, Slack, GitHub, CI/CD, public API, white label, SSO

A lightweight Chrome extension (PRD §18) ships alongside Phase 2. It only collects the
current page and hands off to the platform — no heavy AI processing in the extension.
