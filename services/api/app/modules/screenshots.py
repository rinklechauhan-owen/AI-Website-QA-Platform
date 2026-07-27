"""Module 10 — Screenshot analysis.

Reviews uploaded screenshots and, when a design file is attached, diffs design against the
live site: alignment, missing elements, colour, typography, wrong icons, spacing, cropping.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule


class ScreenshotsModule(AuditModule):
    key = ModuleKey.SCREENSHOTS

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        if not context.get("design_upload_key"):
            return {"skipped": "no design upload provided"}

        # TODO: pair each design frame with the matching live screenshot, send both to the
        # vision model, and emit component-level mismatch findings.
        raise NotImplementedError("Module 10 (screenshots) is not implemented yet")
