"""Plain-text report for the console."""

from __future__ import annotations

import os
import sys
from typing import List

from audit.engine import AuditResult
from audit.findings import Severity

WIDTH = 78

SEVERITY_LABEL = {
    Severity.CRITICAL: "CRITICAL",
    Severity.HIGH: "HIGH",
    Severity.MEDIUM: "MEDIUM",
    Severity.LOW: "LOW",
    Severity.INFO: "INFO",
}

_ANSI = {
    Severity.CRITICAL: "\033[1;31m",
    Severity.HIGH: "\033[31m",
    Severity.MEDIUM: "\033[33m",
    Severity.LOW: "\033[36m",
    Severity.INFO: "\033[90m",
}
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[90m"


def supports_color(stream=None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if sys.platform == "win32":
        # Windows Terminal and PowerShell 7 set this; legacy conhost does not.
        return bool(os.environ.get("WT_SESSION") or os.environ.get("TERM"))
    return True


def _bar(score: float, width: int = 24) -> str:
    filled = int(round(score / 100 * width))
    return "#" * filled + "." * (width - filled)


def _wrap(text: str, indent: int, width: int = WIDTH) -> List[str]:
    """Minimal greedy wrap — avoids pulling in textwrap's paragraph handling."""
    limit = max(20, width - indent)
    words = text.split()
    lines: List[str] = []
    current = ""

    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= limit:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return [" " * indent + line for line in lines]


def render(result: AuditResult, color: bool = None) -> str:
    if color is None:
        color = supports_color()

    def paint(text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if color else text

    out: List[str] = []
    out.append("=" * WIDTH)
    out.append(paint("  WEBSITE QA AUDIT", _BOLD))
    out.append("=" * WIDTH)
    out.append(f"  URL        {result.final_url}")
    if result.was_redirected:
        out.append(f"  Requested  {result.url}  (redirected)")
    out.append(f"  Title      {result.page_title}")
    out.append(
        f"  Response   HTTP {result.status} · {result.elapsed_ms} ms · "
        f"{result.byte_size / 1024:.1f} KB"
    )
    out.append(f"  Scanned    {result.fetched_at}")
    out.append("")

    out.append(
        f"  OVERALL {result.overall_score:5.1f}/100   [{_bar(result.overall_score)}]"
    )
    out.append("")

    counts = result.counts
    summary = "  ".join(
        f"{SEVERITY_LABEL[sev]} {counts[sev.value]}"
        for sev in Severity
        if counts[sev.value]
    )
    out.append("  " + (summary or "No issues found."))
    out.append("")

    for pack in result.packs:
        out.append("-" * WIDTH)
        out.append(
            f"  {pack.label.upper():12} {pack.score:5.1f}/100   [{_bar(pack.score, 18)}]"
        )
        out.append("-" * WIDTH)

        if pack.stats:
            stat_line = " · ".join(f"{k.replace('_', ' ')}: {v}" for k, v in pack.stats.items())
            out.extend(_wrap(stat_line, indent=2))
            out.append("")

        if not pack.findings:
            out.append(paint("  No issues found.", _DIM) if color else "  No issues found.")
            out.append("")
            continue

        for finding in pack.findings:
            badge = f"[{SEVERITY_LABEL[finding.severity]}]"
            out.append(f"  {paint(badge, _ANSI[finding.severity])} {finding.title}")
            out.append(paint(f"      rule: {finding.rule}", _DIM) if color else f"      rule: {finding.rule}")

            if finding.detail:
                out.extend(_wrap(finding.detail, indent=6))
            if finding.recommendation:
                out.extend(_wrap("Fix: " + finding.recommendation, indent=6))
            out.append("")

    out.append("=" * WIDTH)
    out.append("  Static HTML analysis only. Performance, rendered-DOM, and visual checks")
    out.append("  require the browser-based modules and are not included in this run.")
    out.append("=" * WIDTH)

    return "\n".join(out)
