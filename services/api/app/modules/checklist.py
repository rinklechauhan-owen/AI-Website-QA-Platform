"""Module 12 — QA checklist.

Derives a per-page pass/fail checklist from the findings the other modules produced, so this
module runs last and adds no new detection of its own.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule

CHECKLIST_ITEMS = (
    "meta_title",
    "meta_description",
    "canonical",
    "h1",
    "h2",
    "sitemap",
    "robots",
    "responsive",
    "accessibility",
    "images_optimized",
    "image_alt",
    "no_broken_links",
)


class ChecklistModule(AuditModule):
    key = ModuleKey.CHECKLIST

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # TODO: roll findings up per page into {item: bool} and return
        # {"score": <percentage passing>, "pages": {...}}.
        raise NotImplementedError("Module 12 (checklist) is not implemented yet")
