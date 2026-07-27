"""Module 5 — Accessibility audit.

Injects axe-core into each crawled page and maps violations onto findings: labels, ARIA,
contrast, focus states, heading order, landmarks, keyboard navigation, forms, buttons.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule

# axe impact levels map onto our Severity scale.
AXE_IMPACT_TO_SEVERITY = {
    "critical": "critical",
    "serious": "high",
    "moderate": "medium",
    "minor": "low",
}


class AccessibilityModule(AuditModule):
    key = ModuleKey.ACCESSIBILITY

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # TODO: run axe-core per page, dedupe violations across pages, and return
        # {"score": <derived from violation count and impact>}.
        raise NotImplementedError("Module 5 (accessibility) is not implemented yet")
