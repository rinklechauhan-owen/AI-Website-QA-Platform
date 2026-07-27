"""Module 4 — Performance audit.

Runs Lighthouse and records the four category scores plus Core Web Vitals
(LCP, CLS, INP, FCP, TTFB, Speed Index, Total Blocking Time).
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule

CORE_WEB_VITALS = ("lcp", "cls", "inp", "fcp", "ttfb", "speed_index", "total_blocking_time")


class PerformanceModule(AuditModule):
    key = ModuleKey.PERFORMANCE

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # TODO: shell out to the Lighthouse CLI, parse the JSON report, emit findings for
        # metrics outside their "good" threshold, and return {"score": <performance score>}.
        raise NotImplementedError("Module 4 (performance) is not implemented yet")
