"""Module 2 — Image audit.

Missing, empty, and generic alt text; WebP/AVIF conversion opportunities; oversized assets;
lazy loading; responsive srcset; duplicates. AI suggests replacement alt text.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule

# Alt values that are present but carry no information live with the rule that uses them,
# in audit/rules/images.py (GENERIC_ALT_VALUES) — not duplicated here.


class ImagesModule(AuditModule):
    key = ModuleKey.IMAGES

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # The markup-level checks already exist, dependency-free, in audit/rules/images.py —
        # this wrapper should delegate rather than reimplement:
        #
        #     from audit.parse import parse
        #     from audit.rules import images as image_rules
        #     findings, stats = image_rules.run(parse(page.html, page.url))
        #
        # Still to add at this layer, because they require fetching each asset: real byte size,
        # actual vs. displayed dimensions, WebP/AVIF saving estimates, and perceptual hashing
        # for duplicate detection across differently-named files.
        raise NotImplementedError("Module 2 (images) is not implemented yet")
