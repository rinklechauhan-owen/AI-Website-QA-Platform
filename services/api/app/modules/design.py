"""Module 6 — AI design review.

Sends full-page screenshots to a vision model and scores alignment, spacing, consistency,
typography, hierarchy, whitespace, colour palette, brand consistency, and overall aesthetics.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule

REVIEW_DIMENSIONS = (
    "alignment",
    "spacing",
    "consistency",
    "typography",
    "buttons",
    "cards",
    "navigation",
    "footer",
    "visual_hierarchy",
    "whitespace",
    "color_palette",
    "brand_consistency",
    "accessibility",
    "responsive_design",
    "overall_aesthetics",
)


class DesignModule(AuditModule):
    key = ModuleKey.DESIGN

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # TODO: call the vision model per dimension, emit a finding per issue, and return
        # {"score": ..., "strengths": [...], "issues": [...]}.
        raise NotImplementedError("Module 6 (design) is not implemented yet")
