# AI Website QA Platform — Development Record

What has been built, how it works, why it was built that way, and what remains unbuilt.

**Repository:** https://github.com/rinklechauhan-owen/AI-Website-QA-Platform
**Period:** 27 July – 4 August 2026 · 9 commits
**Status:** working audit engine and interface; service and dashboard layers scaffolded

---

## 1. Summary

The project began as a product specification for a 16-module website QA platform. It now
contains a **working, dependency-free website auditing tool** plus the scaffolding for the
larger platform described in that specification.

The working part audits any URL and reports on SEO, headings, meta tags, canonical URLs, image
accessibility, image weight, crawler directives, structured data, page structure and links. It
runs from a command line, from a browser interface, or in a deployment pipeline. It also
generates schema.org markup from arbitrary content.

The single most important property: **it uses only the Python standard library.** No
`pip install`, no database, no API keys, no build step. If Python 3.9+ is present, it runs.
That constraint was chosen deliberately and is discussed in §4.

### At a glance

| | |
| --- | --- |
| Audit engine | 23 files, ~5,500 lines of Python |
| Tests | 11 files, ~1,850 lines, **241 tests**, no network required |
| Detection rules | **38** stable rule IDs across 4 packs |
| Schema types generated | 9 |
| Report pages | 11, plus a dashboard |
| Third-party runtime dependencies | **0** |
| Service layer (scaffold) | 45 files, ~1,300 lines |
| Front-end layer (scaffold) | 13 files |

---

## 2. Timeline

Nine commits, in order.

| Commit | Date | What it added |
| --- | --- | --- |
| `ff895bf` | 27 Jul | Initial commit (README stub only) |
| `11732ba` | 28 Jul | Product spec and repository scaffold |
| `ecf0d03` | 28 Jul | **Working audit engine, CLI, HTML report** |
| `c3afe43` | 28 Jul | Fix: mojibake in terminal output on legacy code pages |
| `86a34ea` | 28 Jul | Fix: transliterate text taken from audited pages |
| `cf0cd92` | 31 Jul | **Browser UI, content listing, structure outline, schema suggestion** |
| `4832eaa` | 31 Jul | **Tabbed report and image weight measurement** |
| `6a18564` |  4 Aug | **Dashboard redesign, sidebar navigation, Schema Generator** |
| `d2e779e` |  4 Aug | **Owen Media brand: Montserrat, brand blues, logo, type scale** |

### Phase 1 — Specification and scaffold (`11732ba`)

The product requirements were committed as [`docs/PRD.md`](PRD.md): vision, five user roles,
16 feature modules, tech stack, permissions model and a five-phase roadmap.

Alongside it, a repository structure was laid down for the eventual platform — a FastAPI
service with SQLAlchemy models, Pydantic schemas, Celery task orchestration and Alembic
migrations, plus a Next.js front end with a typed API client. **All audit logic in that layer
was left as registered stubs.** The README said so explicitly.

At this point the repository described a platform but did not audit anything.

### Phase 2 — A working engine (`ecf0d03`)

The gap between "specified" and "working" was closed by building the rule engine as a
standalone, dependency-free package:

- `fetch.py` — HTTP via `urllib`, adding redirect handling, gzip/deflate decompression and
  charset detection, none of which `urllib` provides.
- `parse.py` — a document model built on `html.parser`. Deliberately tolerant, because audited
  markup is frequently broken.
- `findings.py` — a `Finding` dataclass matching the shape of the service layer's database row,
  plus severity weighting and scoring.
- `rules/seo.py`, `rules/images.py`, `rules/links.py` — the detection logic.
- `report/html.py`, `report/terminal.py` — output renderers.
- `cli.py` — `python -m audit <url>`, with text/HTML/JSON output and CI exit codes.

### Phase 3 — Browser input and page inventory (`cf0cd92`)

Four capabilities were added:

1. A **local web server** (`server.py`) built on `http.server`, so a URL can be pasted into a
   browser rather than typed on a command line.
2. A **content listing** — every heading and paragraph in document order.
3. A **structure outline** — a nested tree of the document's structural elements.
4. An **image alt inventory** — the source URL of every image lacking usable alt text.

Plus **generated schema.org markup** derived from the audited page.

### Phase 4 — Tabs and image weight (`4832eaa`)

The report was reorganised from one long scroll into tabs. A genuinely new capability arrived
with it: `assets.py` measures the transfer size of every image and flags anything over 2.5 MB.
This is the only check that fetches subresources, so it is opt-in.

### Phase 5 — Dashboard and Schema Generator (`6a18564`)

Tabs became sidebar navigation with each section as a page, fronted by a dashboard showing an
overall score ring, stat cards, per-category meters and a severity breakdown.

A **Schema Generator** was added as a separate tool page: paste content, get JSON-LD. Unlike
the page-derived suggestion, this works from content the user supplies.

### Phase 6 — Brand (`d2e779e`)

Montserrat embedded as a variable font, the Owen Media logo inlined, brand blues applied, and
every ad-hoc font size replaced with a single type scale.

---

## 3. Architecture

```
                    ┌─────────────────────────────────────┐
   Command line ───▶│                                     │
                    │            audit/                   │
   Browser UI ─────▶│      dependency-free engine         │──▶ text / HTML / JSON
                    │                                     │
   CI pipeline ────▶│  fetch → parse → rules → report     │──▶ exit code
                    └─────────────────────────────────────┘
                                    ▲
                                    │ (intended)
                    ┌───────────────┴─────────────────────┐
                    │   services/api  (scaffold)          │
                    │   FastAPI · Celery · PostgreSQL     │
                    └─────────────────────────────────────┘
                                    ▲
                    ┌───────────────┴─────────────────────┐
                    │   apps/web  (scaffold)              │
                    │   Next.js dashboard                 │
                    └─────────────────────────────────────┘
```

**Dependencies point in one direction only.** The engine knows nothing about FastAPI,
SQLAlchemy or a browser. This is the central architectural decision and everything else follows
from it:

- The same rule code serves the CLI, the web UI, a background worker and CI.
- Rules can be tested without a database, a network or a server.
- The service layer becomes a thin persistence wrapper rather than a reimplementation.

The service-layer stubs in `services/api/app/modules/` are documented to **wrap** the engine
rather than duplicate it, with the division of labour stated: markup-level checks belong in the
engine; anything needing site-wide context, a rendered DOM or the assets themselves belongs in
the service layer.

### Pipeline

```
URL
 │
 ├─ fetch.py ........ HTTP GET, follow redirects, decompress, decode charset
 │
 ├─ parse.py ........ build Document: title, meta, headings, paragraphs,
 │                    images, links, JSON-LD, structure tree
 │
 ├─ rules/ .......... seo · images · links · assets  →  Finding objects
 │
 ├─ inventory.py ..... extracts: headings, structure, meta, canonical,
 │                    robots directives, alt inventory, schema suggestion
 │
 └─ report/ ......... html.py (dashboard) · terminal.py · JSON
```

Findings are judgements (something is wrong). Inventory items are extracts (this is what is
there). Keeping them separate matters: a heading list is reference material, not a defect.

---

## 4. The zero-dependency constraint

The engine imports nothing outside the Python standard library. This was a deliberate choice
with real consequences, positive and negative.

**What it bought:**

- Runs on any machine with Python — no install step, no environment to break.
- Anyone can be handed a command and get a result in seconds.
- No supply-chain surface, no version conflicts, no lock file to maintain.
- The test suite runs in under a second with no fixtures or services.

**What it cost:**

- `urllib` needed redirect, gzip and charset handling written by hand (`fetch.py`).
- `html.parser` is a tag-stream parser, not a tree builder, so the document model and structure
  tree were built manually (`parse.py`). This turned out to be an advantage — a lenient parser
  is what you want when auditing broken markup — but it took real work.
- The web UI is `http.server` rather than a framework, so routing, form parsing and error
  handling are explicit.
- No Lighthouse, no axe-core, no headless browser. Those need the service layer.

**How it constrains the output:** the HTML report contains **zero `<script>` tags** and makes
**zero external requests**. Everything — CSS, font, logo, icons — is inlined. This is enforced
by tests, not convention. Consequences:

- A saved report renders identically offline, forever, with no CDN dependency.
- Navigation had to be built from radio inputs and `:checked` selectors rather than JavaScript.
- Reports embed text taken from audited pages, so a scripted report would be an injection
  vector. Having no script capability removes the risk category entirely.

---

## 5. The engine, module by module

### `fetch.py` (166 lines)

HTTP on `urllib`, with the gaps filled in:

- Redirects followed; the final URL is reported so redirect chains are visible.
- gzip and deflate decompression, including servers that omit the zlib wrapper.
- Charset detection from the `Content-Type` header, falling back to a `<meta charset>` sniff,
  then UTF-8, then cp1252, then a lossy decode. A page never fails to audit over encoding.
- HTTP error statuses return a normal response so the rules can report on them; only a genuine
  connection failure raises.
- `head_status()` for link checking — tries `HEAD`, falls back to `GET`, because many servers
  reject `HEAD`.

### `parse.py` (409 lines)

Builds a `Document` from HTML. Extracts title, `lang`, meta tags, canonical, headings,
paragraphs, images, links, JSON-LD blocks, `<picture>` sources, visible text length, and a
nested structure tree.

Three details worth noting, each of which was a bug before it was a feature:

- **Nested capture.** `<h2><a>Title</a></h2>` must give the heading its text *and* the anchor
  its text. Text is appended to every open capture frame, not just the innermost.
- **Implicit paragraph close.** `<p>one<p>two` is valid HTML and must yield two blocks, not one
  merged block. Any block-level element closes an open `<p>`.
- **Alt state is three-valued.** A missing `alt` attribute, `alt=""`, and `alt="text"` are
  distinct cases with different meanings. `None` versus `""` versus content, never conflated.

Malformed input degrades to partial results rather than raising.

### `findings.py` (81 lines)

The `Finding` dataclass: `rule`, `module`, `severity`, `title`, `detail`, `element`,
`recommendation`, `line`, `meta`. Its shape matches the service layer's `Finding` database row,
so persistence needs no translation.

Scoring: each pack starts at 100 and deducts by severity — critical 25, high 12, medium 6,
low 2, **info 0**. Informational findings never reduce a score, because `alt=""` on a decorative
image is correct and should not be punished.

### `rules/seo.py` (353 lines) — 21 rules

Title presence and length · meta description presence and length · `noindex` and `nofollow`
directives · canonical URL · H1 presence and uniqueness · skipped heading levels · empty
headings · `lang` attribute · viewport meta · Open Graph tags · Twitter Card · JSON-LD
structured data · thin content · non-descriptive anchor text.

`seo.noindex` is the only **critical** severity in the pack — a live page carrying a staging
`noindex` cannot rank at all, and it is a common post-launch mistake.

### `rules/images.py` (217 lines) — 11 rules

Missing `alt` · explicit `alt=""` · generic alt values (`image`, `photo`, `logo`, …) · overlong
alt · unresolvable `src` · absent `width`/`height` (a layout-shift cause) · legacy PNG/JPEG with
no WebP/AVIF alternative · eager loading below the fold · duplicate sources · oversized files ·
unreachable files.

`image.missing-alt` is reported **per image**, because each needs its own alt text written.
Grouped findings are used only where one fix addresses all instances.

### `rules/links.py` (131 lines) — 4 rules

Broken links · unreachable links · mixed-content images on HTTPS pages · plain-HTTP links.
Checked concurrently via `ThreadPoolExecutor`, deduplicated, and capped — with the number
skipped reported rather than silently dropped.

### `assets.py` (284 lines)

Measures image transfer weight. Size comes from a `HEAD` request's `Content-Length`. Where a
server omits it, the image is streamed **only as far as one byte past the limit** — enough to
answer "is this too big?" without downloading a 40 MB file to find out. Sources are
deduplicated first, so an image used five times costs one request.

Default threshold 2.5 MB, configurable.

### `inventory.py` (650 lines)

Extracts rather than judgements:

- **Content listing** — headings and paragraphs in document order with line numbers and word
  counts.
- **Structure outline** — nested structural elements with ids and classes. Inline formatting is
  excluded so the page shape stays legible; depth and node count are capped, and anything
  omitted is counted and reported.
- **Meta tags** — every `<meta>` normalised into name / property / http-equiv / charset.
- **Canonical** — declared value, whether absolute, whether self-referencing.
- **Index/follow** — directives from the markup **and** the `X-Robots-Tag` response header. A
  header-level `noindex` is invisible in the HTML and is a classic reason a healthy-looking page
  will not rank.
- **Schema suggestion** — JSON-LD derived from the page: Organization, WebPage, BreadcrumbList,
  and Article or FAQPage where the content supports it. Structured data the page already
  declares is detected so suggestions say "merge" rather than duplicating.

### `schemagen.py` (534 lines)

A standalone generator: content in, JSON-LD out. Distinct from the inventory's suggestion,
which derives from a fetched page; this works from content a user types or pastes.

Nine types: **Article, FAQPage, HowTo, Organization, LocalBusiness, Product, Event,
BreadcrumbList, WebPage**, plus auto-detection.

Input conventions:

| Input | Result |
| --- | --- |
| `Key: value` lines | Specific fields (`Name:`, `Price:`, `Author:`, `Street:` …) |
| Lines ending in `?` followed by an answer | FAQPage question pairs |
| Numbered or bulleted lines | HowTo steps |
| `Home > Services > Branding` | BreadcrumbList |
| Pasted HTML | Parsed with the audit engine's own parser |

**The governing rule: nothing is invented.** A field that cannot be derived is omitted. Beyond
that there is a distinction that matters:

- **Notes** are advisory — the markup is valid but could be richer (no author on an Article).
  Output is still produced.
- **Warnings** are blocking — a *required* property is missing (an Event with no start date).
  **No markup is produced at all.**

That second rule exists because emitting an Event without `startDate` while warning that one is
required would hand someone invalid structured data with a caveat attached. Structured data that
misstates a page is worse for a site than having none.

---

## 6. Interfaces

### Command line

```bash
python -m audit <url> [options]
python -m audit --serve [--port N]
```

| Option | Purpose |
| --- | --- |
| `--serve` | Start the local web UI and open a browser |
| `-f, --format {text,html,json}` | Output format |
| `-o, --out FILE` | Write to a file |
| `--open` | Open the written report |
| `--check-links` | Verify every link resolves |
| `--check-images` | Measure image transfer sizes |
| `--image-size-limit MB` | Weight threshold (default 2.5) |
| `--content-tags TAGS` | Tags in the content listing |
| `--outline-depth N` | Structure outline depth |
| `--fail-on SEVERITY` | Exit non-zero at or above this severity |
| `--insecure` | Skip TLS verification, for staging certificates |

Exit codes: `0` clean · `1` findings at or above `--fail-on` · `2` page could not be audited.
The `--fail-on` flag is what makes this usable as a pipeline gate.

### Web UI

`python -m audit --serve` starts a local server. Three routes:

| Route | Purpose |
| --- | --- |
| `/` | URL form, with checkboxes for link and image checking |
| `/audit` | Runs the audit, renders the dashboard |
| `/schema` | Schema Generator |

Security decisions, all deliberate:

- **Binds `127.0.0.1` only.** The engine fetches whatever URL it is handed; exposed on a
  network it would be an open request proxy.
- **Non-HTTP schemes refused** before reaching the fetcher — `file:`, `javascript:`, `data:`,
  `ftp:` and others.
- **`Content-Security-Policy: default-src 'none'`**, with `data:` permitted for the inlined font
  and logo. `script-src` is absent entirely, so nothing can execute.
- **One bad page cannot take the server down** — unexpected errors return 500 and the server
  keeps serving.

### Report pages

| Page | Contents |
| --- | --- |
| **Dashboard** | Score ring, stat cards, category meters, severity breakdown, response facts |
| **SEO** | SEO rule pack findings |
| **Headings** | Every H1–H6 in document order, indented by level |
| **Meta Tags** | Every `<meta>` as served |
| **Canonical URLs** | Declared canonical, absolute and self-referencing checks |
| **Alt Tag Missing** | Source URL of every image with no or empty alt |
| **Image Size** | Images over the weight threshold |
| **Index / Follow** | Robots directives from markup and headers |
| **Schema** | Generated JSON-LD from the audited page |
| **Image Issues** | Remaining image findings |
| **Page Structure** | Nested structural outline |
| **Links** | Broken-link findings, when link checking ran |

Navigation is radio inputs plus `:checked` selectors. The radios stay keyboard-focusable and
exposed to assistive technology; printing reveals every page at once.

---

## 7. Design system

`audit/report/theme.py` holds the entire visual language, shared by the report and the web UI so
a saved file and a served page cannot drift apart.

### Type

**Montserrat**, embedded as a variable WOFF2 data URI — 38 KB covering weights 400–700, smaller
than three static weights. Embedding rather than linking was necessary: Montserrat was not
installed on the target machine, so a plain `font-family` declaration would have silently fallen
back, and linking a web font would break both the offline guarantee and the CSP. Redistributed
under the SIL Open Font License, which ships alongside it.

One scale governs every size:

| Token | Size | Used for |
| --- | --- | --- |
| `--fs-xs` | 12px | Eyebrows, pills, line numbers, table headers |
| `--fs-sm` | 13px | Secondary text, table cells, notes |
| `--fs-base` | 14px | Body default |
| `--fs-md` | 16px | Section and card headings |
| `--fs-lg` | 20px | Page titles |
| `--fs-xl` | 30px | Stat values |
| `--fs-2xl` | 34px | Score ring |

Weights are limited to 400/500/600/700 — the range the variable font actually carries, so
nothing is synthesised. A test fails on any hardcoded pixel font-size, so the scale cannot
quietly erode.

### Colour

`#3264f5` and `#5b95d2`, solid and as a 135° gradient. Which does what is decided by contrast,
not preference:

| Colour | On white | On dark surface | Role |
| --- | --- | --- | --- |
| `#3264f5` | **4.91:1** ✓ AA | 3.91:1 ✗ | Text, links, solid fills (light mode) |
| `#5b95d2` | 3.15:1 ✗ | **6.11:1** ✓ AA | Gradient and decoration; text accent in dark mode |

Because `#5b95d2` falls below the 4.5:1 AA threshold on white, it never carries body text in
light mode. The accent stat card uses solid `#3264f5` rather than the gradient, since white text
over the gradient's lighter end would fail. These ratios are asserted by tests — a tool that
audits accessibility should not ship failing contrast in its own interface.

### Logo

The Owen Media wordmark, inlined as a data URI. It is white on a transparent background, so it
sits on the brand gradient panel; on the white sidebar it would have been invisible.

### Cost

A generated report is roughly 116 KB, of which about 59 KB is the embedded font and logo. That
is the price of a file that renders identically offline with no external requests. Dropping the
embed and accepting a system-font fallback is a one-line change.

---

## 8. Testing

**241 tests**, standard-library `unittest`, no network access required:

```bash
python -m unittest discover -s tests -t . -v
```

| File | Covers |
| --- | --- |
| `test_parse.py` | Parser edge cases: entities, nested markup, malformed input |
| `test_rules.py` | Rule packs against clean and deliberately broken fixtures |
| `test_inventory.py` | Content listing, outline, alt states, schema suggestion |
| `test_report.py` | Renderer output, HTML validity, escaping |
| `test_pages.py` | Page layout, ordering, extracts behind each page |
| `test_schemagen.py` | All nine schema types, detection, blocking rules |
| `test_server.py` | Real server on a loopback port, driven over HTTP |
| `test_cli.py` | Argument handling and exit codes |
| `test_theme.py` | Embedded assets, type scale, contrast ratios |

Coverage targets the things most likely to break silently rather than chasing a percentage:

- The boundary between a missing `alt` attribute and an empty one.
- Unclosed `<p>` tags and headings that wrap links.
- Score arithmetic, including that info findings never deduct.
- CLI exit codes, since a wrong one breaks a pipeline quietly.
- URL scheme validation.
- **HTML escaping** — `test_report.py` renders a hostile fixture that attempts script injection
  and asserts no live `<script>` or event handler survives into the output. Reports embed text
  from audited pages, so this is a real attack surface.
- **Contrast ratios**, computed from the actual WCAG formula.
- **Type scale integrity** — the suite fails if any component hardcodes a font size.

`test_server.py` starts a real `ThreadingHTTPServer` on a free loopback port and drives it over
HTTP, with the audit itself stubbed so the suite stays offline and fast.

---

## 9. Bugs found and fixed

Kept as a record because most were found by testing rather than by reading, which is the
argument for the test suite.

| Bug | Consequence | Found by |
| --- | --- | --- |
| Headings wrapping a link returned empty text | Card titles under-reported across most real sites | Fixture test |
| `sys.stdout.reconfigure()` on a redirected stream | Crash whenever stdout was not a terminal | CLI test |
| `file:///…` slipped past scheme validation | Confusing 502 instead of a refusal; the guard was dead code | Server test |
| `SO_REUSEADDR` on the port probe | Every port looked free on Windows; two servers could bind one port | Port test |
| Nav radios hidden with `width/height: 0` | Removed from the accessibility tree, tabs keyboard-unreachable | Browser check |
| Schema generator ignored HTML input | Every pasted page returned "no title found" | Generator test |
| Generator emitted an `Event` with no `startDate` | Invalid structured data shipped with a warning attached | Generator test |
| CSP blocked `data:` URIs | Embedded font and logo failed to load on served pages | Browser check |
| `·` and `™` rendered as `�` | Unreadable terminal output on legacy Windows code pages | Live run |
| Tailwind `@theme` nested inside `@media` | Unsupported; dark mode would not have applied | Code review |
| Dead `_pack_card` emitting unstyled classes | Silent dead code after the dashboard redesign | Class audit |
| `.stats` emitted with no CSS rule | Unstyled element in the findings view | Class audit |

Two documentation inaccuracies were also corrected: the module README claimed unimplemented
modules are always skipped (true for audit modules, but not for the crawl module, which fails
the scan by design), and a rule count was misstated as 27 when it was 36.

---

## 10. Honest status

### Working

- The audit engine, all four rule packs, all 38 rules.
- The page inventory: headings, structure, meta, canonical, robots, alt inventory.
- Image weight measurement.
- The Schema Generator, all nine types.
- Three output formats and CI exit codes.
- The command line and the browser UI.
- 241 tests.

### Scaffolded, not functional

- **`services/api/`** — FastAPI application with SQLAlchemy models (`Scan`, `Page`, `Finding`),
  Pydantic schemas, Celery task orchestration and an Alembic environment. Endpoints exist and
  the task pipeline is wired, but the audit modules are registered stubs that raise
  `NotImplementedError`. The orchestrator logs and skips them, so modules can be implemented
  one at a time without breaking scans. No migrations are committed.
- **`apps/web/`** — Next.js 15 with TypeScript, Tailwind, a TanStack Query provider, a typed API
  client mirroring the backend enums, and a scan submission form. No report views.

### Specified but not implemented

From the PRD: Lighthouse performance metrics and Core Web Vitals · axe-core accessibility
ruleset · rendered-DOM inspection · responsive screenshots across 11 breakpoints · AI design
review · content-versus-document comparison · forms testing · PDF, Excel and Word export ·
team dashboard, history and trends · Jira, Slack and GitHub integrations.

These need a headless browser or a vision model, which is what the service layer exists for.
Both report footers state the scope of every run, so a report cannot be mistaken for a full
audit.

### Known limitation worth stating plainly

Analysis is of the **served HTML**. On a JavaScript-rendered site, the tool sees what a crawler
sees before script execution — which is often far less than a visitor sees. That gap is itself
useful information (and the `seo.thin-content` rule surfaces it), but confirming it requires
comparing rendered against served markup, which needs the browser-based modules.

---

## 11. Running it

Python 3.9+ is the only requirement.

Audit a page:

```bash
python -m audit https://example.com
```

Browser interface:

```bash
python -m audit --serve
```

Shareable HTML report:

```bash
python -m audit https://example.com --check-images --format html --out report.html --open
```

Pipeline gate:

```bash
python -m audit https://example.com --check-links --check-images --fail-on high
```

Tests:

```bash
python -m unittest discover -s tests -t . -v
```

Sample output is committed at [`examples/sample-report.html`](../examples/sample-report.html),
generated from the deliberately flawed [`examples/sample-page.html`](../examples/sample-page.html)
so the result is reproducible and does not comment on any real site. Regenerate with
`python examples/generate_sample.py`.

---

## 12. Recurring principles

Four ideas shaped most of the decisions above.

**Dependencies point one way.** Rule logic that depends on a framework, an ORM or a browser can
only run in one place. Keeping it as plain functions over a parsed document means the same code
serves the CLI, a worker and CI.

**Never invent a value.** Applies to generated schema most visibly, but also to scores, counts
and caps. Where a limit truncates output, the amount dropped is reported rather than silently
omitted.

**State scope on the artefact.** Every report says in its own footer what was and was not
checked. A document that travels without its caveats will eventually be read without them.

**Do not ship the flaw you detect.** The tool reports missing alt text, so its own logo has it.
It reports contrast failures, so its own palette is measured against WCAG. It reports
keyboard-inaccessible controls, so its navigation was fixed when a browser check found the
radios missing from the accessibility tree.
