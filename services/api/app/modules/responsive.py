"""Module 9 — Responsive testing.

Replays each page at every breakpoint in RESPONSIVE_BREAKPOINTS, captures a screenshot, and
detects overflow, misalignment, navigation problems, spacing, broken grids, missing content.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import RESPONSIVE_BREAKPOINTS, ModuleKey
from app.modules.base import AuditModule


class ResponsiveModule(AuditModule):
    key = ModuleKey.RESPONSIVE

    breakpoints: tuple[int, ...] = RESPONSIVE_BREAKPOINTS

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # TODO: for each page × breakpoint, screenshot into Page.screenshot_keys and emit
        # findings tagged with the reproducing width in `meta`.
        raise NotImplementedError("Module 9 (responsive) is not implemented yet")
