"""Module 1 — Website crawl.

Walks the site with Playwright and records HTML, CSS, JS, images, fonts, meta tags, and
internal/external links per page. Every other module consumes this output.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule


class CrawlModule(AuditModule):
    key = ModuleKey.CRAWL

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # TODO: launch Playwright, honour robots.txt and CRAWL_* settings, persist Page rows,
        # and return {"pages": [...], "assets": {...}, "console_errors": [...]}.
        raise NotImplementedError("Module 1 (crawl) is not implemented yet")
