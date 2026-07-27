"""Module 8 — Bug detection.

Detects broken layouts, overflow, horizontal scroll, missing images, 404 assets, JS and
console errors, API failures, overlapping controls, hidden content, broken sliders, and
missing fonts. Emits a full bug report per issue (steps, expected, actual, screenshot).
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule


class BugsModule(AuditModule):
    key = ModuleKey.BUGS

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # TODO: emit bug.horizontal-scroll, bug.overflow, bug.asset-404, bug.console-error,
        # bug.api-failure, bug.overlap, bug.hidden-content, bug.missing-font — each with a
        # reproduction screenshot and steps/expected/actual in `recommendation`.
        raise NotImplementedError("Module 8 (bugs) is not implemented yet")
