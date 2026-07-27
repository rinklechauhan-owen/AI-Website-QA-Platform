# Audit modules

One module per PRD §5 module. All of them are currently stubs that raise
`NotImplementedError`. The orchestrator in [`app/tasks/scan_tasks.py`](../tasks/scan_tasks.py)
logs and skips that for the audit modules, so partial implementation is safe — implement them
one at a time and scans keep working. The one exception is `crawl`: it runs before the
skip-handler because every other module consumes its output, so an unimplemented crawl fails
the whole scan by design.

## Reuse the existing rule engine

The repository already contains a working, dependency-free rule engine at
[`audit/`](../../../../audit/) covering SEO, image, and link checks. **Wrap it, do not
reimplement it:**

```python
from audit.parse import parse
from audit.rules import seo as seo_rules

findings, stats = seo_rules.run(parse(page.html, page.url))
```

Those rules operate on a single parsed document. What belongs at *this* layer is everything
they cannot see: site-wide context (sitemap, robots.txt, cross-page duplicates, page depth),
anything requiring the rendered DOM (Playwright), and anything requiring the assets themselves
(real image byte sizes, Lighthouse). Rule IDs must stay identical across both layers so
historical comparison keeps working.

## Contract

Subclass [`AuditModule`](base.py):

```python
class SeoModule(AuditModule):
    key = ModuleKey.SEO

    def run(self, db: Session, context: dict) -> dict:
        self.add_finding(
            db, context,
            rule="seo.missing-h1",
            severity=Severity.HIGH,
            title="Page has no H1",
            page_id=page.id,
        )
        return {"score": 82.0}
```

- `context` always carries `scan_id`, `url`, `max_pages`, `max_depth`, `design_upload_key`,
  `content_upload_key`, and — for every module after Module 1 — `crawl` (Module 1's output).
- Persist issues with `add_finding`. Do **not** call `db.commit()`; the task owns the
  transaction boundary.
- Return a `score` key (0–100) to contribute to the scan's overall score. Omit it for
  modules that only report issues.
- Return `{"skipped": "<reason>"}` when a prerequisite is absent (e.g. Module 7 with no
  uploaded document) rather than raising.
- Register the class in [`__init__.py`](__init__.py).

## Rule naming

`<area>.<kebab-case-issue>` — `image.missing-alt`, `seo.duplicate-h1`, `bug.horizontal-scroll`.
Rule IDs are stable identifiers: exports, the checklist, and trend comparison key off them,
so renaming one breaks historical comparison.

## Execution order

| Phase | Modules | Scan status |
| --- | --- | --- |
| Crawl | `crawl` | `crawling` |
| Technical | `seo`, `images`, `performance`, `accessibility`, `responsive`, `forms`, `bugs` | `auditing` |
| AI | `design`, `content`, `screenshots`, `checklist` | `analyzing` |

`checklist` runs in the AI phase because it rolls up everything the earlier phases produced.

## Module index

| Key | File | PRD |
| --- | --- | --- |
| `crawl` | [crawl.py](crawl.py) | Module 1 |
| `images` | [images.py](images.py) | Module 2 |
| `seo` | [seo.py](seo.py) | Module 3 |
| `performance` | [performance.py](performance.py) | Module 4 |
| `accessibility` | [accessibility.py](accessibility.py) | Module 5 |
| `design` | [design.py](design.py) | Module 6 |
| `content` | [content.py](content.py) | Module 7 |
| `bugs` | [bugs.py](bugs.py) | Module 8 |
| `responsive` | [responsive.py](responsive.py) | Module 9 |
| `screenshots` | [screenshots.py](screenshots.py) | Module 10 |
| `forms` | [forms.py](forms.py) | Module 11 |
| `checklist` | [checklist.py](checklist.py) | Module 12 |

Module 13 (AI recommendations) is not a separate module — each module fills the
`recommendation` JSON on its own findings. Module 14 (report generation) is an export
concern, reached through `POST /api/v1/scans/{id}/report`.
