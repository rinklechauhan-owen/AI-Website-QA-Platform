"""Contract every audit module implements."""

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey, Priority, Severity
from app.models import Finding


class AuditModule(ABC):
    """Base class for audit modules.

    A module reads the shared ``context`` (which always carries ``scan_id``, ``url``, and —
    for everything after Module 1 — the ``crawl`` output), persists ``Finding`` rows via
    ``add_finding``, and returns a dict. Include a ``score`` key (0–100) in the return value
    to contribute to the scan's overall score.

    Modules must not commit; the orchestrating task owns the transaction boundary.
    """

    key: ModuleKey

    @abstractmethod
    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        """Execute the audit and return a result summary."""

    def add_finding(
        self,
        db: Session,
        context: dict[str, Any],
        *,
        rule: str,
        severity: Severity,
        title: str,
        detail: str | None = None,
        page_id: Any | None = None,
        selector: str | None = None,
        snippet: str | None = None,
        priority: Priority | None = None,
        recommendation: dict | None = None,
        meta: dict | None = None,
    ) -> Finding:
        finding = Finding(
            scan_id=context["scan_id"],
            page_id=page_id,
            module=self.key,
            rule=rule,
            severity=severity,
            priority=priority,
            title=title,
            detail=detail,
            selector=selector,
            snippet=snippet,
            recommendation=recommendation or {},
            meta=meta or {},
        )
        db.add(finding)
        return finding
