"""Plain-text report for the console."""

from __future__ import annotations

import os
import sys
import unicodedata
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

# Typography that reads well in the HTML report but arrives as mojibake on a Windows console
# using a legacy code page (cp1252 / cp437). Substituted only when stdout cannot encode it.
_ASCII_SUBSTITUTIONS = {
    "·": "-",      # ·
    "—": "--",     # —
    "–": "-",      # –
    "×": "x",      # ×
    "≥": ">=",     # ≥
    "≤": "<=",     # ≤
    "’": "'",      # ’
    "‘": "'",      # ‘
    "“": '"',      # “
    "”": '"',      # ”
    "…": "...",    # …
    "✓": "OK",     # ✓
    " ": " ",      # non-breaking space
}


def _encodable(text: str, encoding: str) -> bool:
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def to_ascii(text: str) -> str:
    """Reduce text to ASCII, keeping as much meaning as possible.

    The explicit table handles our own punctuation. Everything else is page-controlled — a
    title can hold anything at all — so the remainder goes through NFKD decomposition, which
    turns 'é' into 'e' and '™' into 'TM', before unrepresentable characters become '?'.
    """
    for source, replacement in _ASCII_SUBSTITUTIONS.items():
        text = text.replace(source, replacement)

    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return without_marks.encode("ascii", errors="replace").decode("ascii")


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


def render(result: AuditResult, color: bool = None, ascii_only: bool = None) -> str:
    if color is None:
        color = supports_color()

    if ascii_only is None:
        # Downgrade only when the console genuinely cannot render the characters.
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        ascii_only = not _encodable("·—≥✓", encoding)

    def paint(text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if color else text

    def conv(text: str) -> str:
        """Normalise before wrapping, so substitutions cannot push a line over WIDTH."""
        return to_ascii(text) if ascii_only else text

    sep = "-" if ascii_only else "·"

    out: List[str] = []
    out.append("=" * WIDTH)
    out.append(paint("  WEBSITE QA AUDIT", _BOLD))
    out.append("=" * WIDTH)
    out.append(f"  URL        {conv(result.final_url)}")
    if result.was_redirected:
        out.append(f"  Requested  {conv(result.url)}  (redirected)")
    out.append(f"  Title      {conv(result.page_title)}")
    out.append(
        f"  Response   HTTP {result.status} {sep} {result.elapsed_ms} ms {sep} "
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
            stat_line = f" {sep} ".join(
                f"{k.replace('_', ' ')}: {v}" for k, v in pack.stats.items()
            )
            out.extend(_wrap(conv(stat_line), indent=2))
            out.append("")

        if not pack.findings:
            out.append(paint("  No issues found.", _DIM) if color else "  No issues found.")
            out.append("")
            continue

        for finding in pack.findings:
            badge = f"[{SEVERITY_LABEL[finding.severity]}]"
            out.append(f"  {paint(badge, _ANSI[finding.severity])} {conv(finding.title)}")
            out.append(paint(f"      rule: {finding.rule}", _DIM) if color else f"      rule: {finding.rule}")

            if finding.detail:
                out.extend(_wrap(conv(finding.detail), indent=6))
            if finding.recommendation:
                out.extend(_wrap(conv("Fix: " + finding.recommendation), indent=6))
            out.append("")

    if result.inventory is not None:
        out.extend(_inventory_lines(result.inventory, conv, paint, color, sep))

    out.append("=" * WIDTH)
    out.append("  Static HTML analysis only. Performance, rendered-DOM, and visual checks")
    out.append("  require the browser-based modules and are not included in this run.")
    out.append("=" * WIDTH)

    return "\n".join(out)


def _heading(title: str) -> List[str]:
    return ["-" * WIDTH, f"  {title.upper()}", "-" * WIDTH]


def _inventory_lines(inventory, conv, paint, color: bool, sep: str) -> List[str]:
    out: List[str] = []

    # --- content listing ---
    content = inventory.content
    counts = " ".join(f"{tag}:{n}" for tag, n in content.counts.items() if n)
    out.extend(_heading("page content"))
    out.append(f"  {len(content.blocks)} blocks {sep} {content.total_words} words {sep} {counts}")
    out.append("")
    if not content.blocks:
        out.append("  No content blocks found.")
        out.append("")
    else:
        for block in content.blocks:
            label = f"  {block.tag.upper():<3} L{block.line:<5} "
            wrapped = _wrap(conv(block.text), indent=len(label))
            if wrapped:
                # Fold the label into the first wrapped line.
                out.append(label + wrapped[0].lstrip())
                out.extend(wrapped[1:])
        out.append("")

    # --- structure outline ---
    outline = inventory.outline
    out.extend(_heading("page structure"))
    out.append(f"  {outline.total_nodes} elements {sep} max depth {outline.max_depth_seen}")
    if outline.was_truncated:
        dropped = outline.truncated_depth + outline.truncated_count
        out.append(f"  ({dropped} deeper or later element(s) not shown)")
    out.append("")
    for row in outline.rows:
        out.append("  " + "  " * row.depth + conv(row.selector))
    out.append("")

    # --- image alt inventory ---
    images = inventory.images
    out.extend(_heading("image alt text"))
    out.append(f"  {images.total} images {sep} {images.coverage:.0f}% described")
    out.append("")
    if not images.needs_attention:
        out.append("  All images have alt text.")
    else:
        for image in images.needs_attention:
            state = image.alt_state.upper()
            tag = paint(f"[{state}]", _ANSI[Severity.HIGH if state == "MISSING" else Severity.MEDIUM])
            out.append(f"  {tag} L{image.line}")
            out.extend(_wrap(conv(image.src or "(no src)"), indent=6))
    out.append("")

    # --- suggested schema ---
    schema = inventory.schema
    out.extend(_heading("suggested schema.org markup"))
    existing = ", ".join(schema.existing_types) if schema.existing_types else "none"
    out.append(f"  Already on page: {existing}")
    out.append(f"  Suggested:       {', '.join(schema.suggested_types) or 'none'}")
    out.append("")
    for note in schema.notes:
        out.extend(_wrap(conv("note: " + note), indent=2))
    if schema.notes:
        out.append("")
    for line in schema.script_block.splitlines():
        out.append("  " + conv(line))
    out.append("")

    return out
