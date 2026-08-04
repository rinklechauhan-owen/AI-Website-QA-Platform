# AI Website QA Platform — Summary

A one-page overview. Full detail is in [DEVELOPMENT.md](DEVELOPMENT.md).

---

## What it is

A tool that audits any website URL and produces a client-ready report covering SEO, headings,
meta tags, canonical URLs, image accessibility, image weight, crawler directives and structured
data. It also generates schema.org markup from pasted content.

**Key point: it uses only the Python standard library.** No install, no database, no API keys,
no running costs. If Python is present, it runs.

---

## By the numbers

| | |
| --- | --- |
| Detection rules | **38** |
| Tests | **241** |
| Report pages | 11 plus a dashboard |
| Schema types generated | 9 |
| Third-party dependencies | **0** |
| Built over | 10 commits, 27 Jul – 4 Aug 2026 |

---

## What it checks

- **SEO** — titles, meta descriptions, canonical, accidental `noindex`, heading structure,
  social tags, structured data, thin content
- **Headings** — every H1–H6 in document order
- **Meta tags** — every `<meta>` as served
- **Images** — missing or weak alt text, layout-shift causes, modern format opportunities,
  lazy loading, files over 2.5 MB
- **Index / Follow** — robots directives from the markup *and* response headers
- **Links** — broken links, insecure HTTP, mixed content
- **Page structure** — nested outline of the document

Every finding carries a severity and a **specific fix**, not just a label.

---

## How it is used

| | |
| --- | --- |
| Command line | `python -m audit <url>` |
| Browser | `python -m audit --serve` — paste a URL into a form |
| Pipeline | `--fail-on high` exits non-zero, so it can block a release |

Output as terminal text, a self-contained HTML dashboard, or JSON.

The HTML report contains **no JavaScript and makes no external requests** — everything is
inlined, so a saved file renders identically offline, forever.

---

## Schema Generator

A separate tool page. Paste HTML or plain text, get schema.org JSON-LD ready to paste into a
page head. Nine types including Article, FAQPage, HowTo, Product, LocalBusiness and Event.

**Nothing is invented.** If a required field cannot be derived, no markup is produced — invalid
structured data is worse for a site than none.

---

## Design

Dashboard layout with sidebar navigation. Montserrat (embedded, so it renders anywhere), brand
colours `#3264f5` and `#5b95d2` solid and as a gradient, Owen Media logo, and one type scale
across every screen.

Contrast was measured, not eyeballed: `#3264f5` passes WCAG AA on white so it carries text;
`#5b95d2` does not, so it stays decorative in light mode and becomes the accent in dark mode.

---

## Status

| Layer | State |
| --- | --- |
| Audit engine, CLI, browser UI | **Working** |
| API service (FastAPI, Celery) | Scaffold — structure wired, audit modules are stubs |
| Next.js dashboard | Scaffold — layout and API client, no report views |

**Not yet built**, though specified: Lighthouse performance scores, full axe-core accessibility
ruleset, responsive screenshots, AI design review, content-versus-brief comparison, PDF export,
team history, and Jira/Slack integrations. These need a headless browser or a vision model.

**One limitation worth stating:** analysis is of the served HTML, so on a JavaScript-rendered
site the tool sees what a crawler sees before scripts run — often less than a visitor sees.

---

## Try it

```bash
python -m audit --serve
```

Sample output is committed at [`examples/sample-report.html`](../examples/sample-report.html).
