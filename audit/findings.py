"""Finding model shared by every rule pack.

Deliberately dependency-free: this is the same shape as the ``Finding`` row in
services/api/app/models/finding.py, so the API layer can persist what the rules emit
without translating between two vocabularies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# Ordering for display and for the score deduction below.
SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}

# How many points each finding removes from a rule pack's 100-point starting score.
SEVERITY_WEIGHT = {
    Severity.CRITICAL: 25.0,
    Severity.HIGH: 12.0,
    Severity.MEDIUM: 6.0,
    Severity.LOW: 2.0,
    Severity.INFO: 0.0,
}


@dataclass
class Finding:
    """A single issue. ``rule`` is the stable identifier; keep it stable across releases."""

    rule: str
    module: str
    severity: Severity
    title: str
    detail: str = ""
    # The offending markup, trimmed for display.
    element: str = ""
    # Why it matters and how to fix it (PRD Module 13).
    recommendation: str = ""
    line: Optional[int] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


def score_from_findings(findings, floor: float = 0.0) -> float:
    """Deduct weighted points from 100. Info-level findings never reduce the score."""
    score = 100.0
    for finding in findings:
        score -= SEVERITY_WEIGHT[finding.severity]
    return round(max(floor, score), 1)


def sort_findings(findings):
    """Most severe first, then grouped by rule for a stable, readable report."""
    return sorted(findings, key=lambda f: (SEVERITY_ORDER[f.severity], f.rule))


def count_by_severity(findings) -> Dict[str, int]:
    counts = {severity.value: 0 for severity in Severity}
    for finding in findings:
        counts[finding.severity.value] += 1
    return counts
