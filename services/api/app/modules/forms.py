"""Module 11 — Forms testing.

Discovers forms and exercises required fields, email and phone validation, dropdowns,
checkboxes, radios, the submit path, and success/error messaging.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule


class FormsModule(AuditModule):
    key = ModuleKey.FORMS

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # TODO: probe validation with deliberately invalid input only — never submit a real
        # payload to a live endpoint without an explicit opt-in on the scan request.
        raise NotImplementedError("Module 11 (forms) is not implemented yet")
