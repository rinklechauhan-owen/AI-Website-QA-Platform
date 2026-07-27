"""Module 2 — Image audit.

Missing, empty, and generic alt text; WebP/AVIF conversion opportunities; oversized assets;
lazy loading; responsive srcset; duplicates. AI suggests replacement alt text.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule

# Alt values that are present but carry no information (PRD Module 2).
GENERIC_ALT_VALUES = frozenset({"image", "photo", "img", "logo", "banner", "picture", "graphic"})


class ImagesModule(AuditModule):
    key = ModuleKey.IMAGES

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # TODO: emit image.missing-alt, image.empty-alt, image.generic-alt,
        # image.unoptimized-format, image.oversized, image.no-lazy-load, image.duplicate.
        raise NotImplementedError("Module 2 (images) is not implemented yet")
