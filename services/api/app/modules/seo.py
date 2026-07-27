"""Module 3 — SEO audit.

Titles, meta descriptions, canonical, Open Graph, Twitter Cards, robots, sitemap, heading
hierarchy, structured data (breadcrumb / FAQ / organization / article), links, page depth.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule


class SeoModule(AuditModule):
    key = ModuleKey.SEO

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # The rule logic already exists, dependency-free, in audit/rules/seo.py — this wrapper
        # should parse each crawled page and persist what audit.rules.seo.run() returns rather
        # than reimplementing the checks:
        #
        #     from audit.parse import parse
        #     from audit.rules import seo as seo_rules
        #     findings, stats = seo_rules.run(parse(page.html, page.url))
        #
        # Still to add at this layer, because they need site-wide context the CLI lacks:
        # sitemap.xml discovery, robots.txt directives, cross-page duplicate titles and H1s,
        # and page depth.
        raise NotImplementedError("Module 3 (seo) is not implemented yet")
