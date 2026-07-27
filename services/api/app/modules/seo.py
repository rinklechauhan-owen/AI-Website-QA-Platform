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
        # TODO: emit seo.missing-title, seo.title-length, seo.missing-meta-description,
        # seo.missing-canonical, seo.missing-h1, seo.duplicate-h1, seo.heading-order,
        # seo.broken-link, seo.missing-schema, seo.missing-sitemap, seo.robots-blocked.
        raise NotImplementedError("Module 3 (seo) is not implemented yet")
