"""Self-contained HTML report.

Everything is inlined — no external CSS, fonts, scripts, or images — so the file can be
emailed, committed, or opened straight off disk and still render identically.
"""

from __future__ import annotations

from html import escape
from dataclasses import dataclass
from typing import Dict, List

from audit.assets import human_size
from audit.report.theme import BASE_CSS, BRAND_MARK, icon
from audit.engine import AuditResult, PackResult
from audit.findings import Finding, Severity

# Circumference of the r=42 score ring, used for the stroke-dash animation offset.
_RING_CIRCUMFERENCE = 263.894

SEVERITY_LABEL = {
    Severity.CRITICAL: "Critical",
    Severity.HIGH: "High",
    Severity.MEDIUM: "Medium",
    Severity.LOW: "Low",
    Severity.INFO: "Info",
}

_CSS = BASE_CSS


def _score_color(score: float) -> str:
    if score >= 90:
        return "var(--good)"
    if score >= 70:
        return "var(--warn)"
    return "var(--bad)"


def _ring(score: float) -> str:
    offset = _RING_CIRCUMFERENCE * (1 - max(0.0, min(100.0, score)) / 100)
    return f"""<div class="ring">
  <svg width="128" height="128" viewBox="0 0 100 100" aria-hidden="true">
    <circle class="ring-track" cx="50" cy="50" r="42" fill="none" stroke-width="8"/>
    <circle class="ring-val" cx="50" cy="50" r="42" fill="none" stroke-width="8"
            stroke="{_score_color(score)}"
            stroke-dasharray="{_RING_CIRCUMFERENCE:.3f}"
            stroke-dashoffset="{offset:.3f}"/>
  </svg>
  <div class="ring-text">
    <div class="ring-num">{score:.0f}</div>
    <div class="ring-of">of 100</div>
  </div>
</div>"""


def _humanise(key: str) -> str:
    return key.replace("_", " ")


def _pack_card(pack: PackResult) -> str:
    issues = len(pack.findings)
    label = "no issues" if issues == 0 else f"{issues} issue{'s' if issues != 1 else ''}"
    return f"""<div class="pack-card">
  <div class="name">{escape(pack.label)}</div>
  <div class="val" style="color:{_score_color(pack.score)}">{pack.score:.0f}</div>
  <div class="meter"><span style="width:{max(0.0, min(100.0, pack.score)):.1f}%;
       background:{_score_color(pack.score)}"></span></div>
  <div class="sub">{label}</div>
</div>"""


def _finding_block(finding: Finding) -> str:
    severity = finding.severity.value
    parts = [f'<article class="finding {severity}">']
    parts.append('  <div class="f-top">')
    parts.append(f'    <span class="badge {severity}">{SEVERITY_LABEL[finding.severity]}</span>')
    parts.append(f'    <span class="f-title">{escape(finding.title)}</span>')
    parts.append(f'    <span class="f-rule">{escape(finding.rule)}</span>')
    parts.append("  </div>")

    if finding.detail:
        line = f" (line {finding.line})" if finding.line else ""
        parts.append(f'  <p class="f-detail">{escape(finding.detail)}{line}</p>')

    if finding.element:
        parts.append(f'  <div class="f-el">{escape(finding.element)}</div>')

    if finding.recommendation:
        parts.append(f'  <p class="f-fix"><b>Fix:</b> {escape(finding.recommendation)}</p>')

    parts.append("</article>")
    return "\n".join(parts)


def _section(pack: PackResult) -> str:
    parts = ["<section>"]
    count = len(pack.findings)
    pill = "clean" if count == 0 else f"{count} finding{'s' if count != 1 else ''}"
    parts.append(
        f'  <h2>{escape(pack.label)} <span class="count-pill">{pill}</span>'
        f'<span class="count-pill">{pack.score:.0f}/100</span></h2>'
    )

    if pack.stats:
        parts.append('  <ul class="stats">')
        for key, value in pack.stats.items():
            parts.append(f"    <li>{escape(_humanise(key))} <b>{escape(str(value))}</b></li>")
        parts.append("  </ul>")

    if not pack.findings:
        parts.append(f'  <div class="clean"><b>&#10003; Clean.</b> No {escape(pack.label.lower())} issues detected.</div>')
    else:
        parts.extend(_finding_block(f) for f in pack.findings)

    parts.append("</section>")
    return "\n".join(parts)


def _headings_section(document) -> str:
    """H1-H6 only, indented by level so the outline reads as a hierarchy."""
    headings = list(document.headings) if document else []
    counts: Dict[str, int] = {}
    for heading in headings:
        key = f"h{heading.level}"
        counts[key] = counts.get(key, 0) + 1
    summary = " · ".join(f"{counts[f'h{n}']} &lt;h{n}&gt;" for n in range(1, 7) if counts.get(f"h{n}"))

    parts = ["<section>"]
    parts.append(
        f'  <h2>Headings <span class="count-pill">{len(headings)} total</span></h2>'
    )
    parts.append(
        f'  <p class="section-note">Every H1&ndash;H6 in document order, indented by level. '
        f"{summary or 'No headings found.'}</p>"
    )

    if not headings:
        parts.append(
            '  <div class="clean">No headings on this page. Every page needs at least an H1.</div>'
        )
        parts.append("</section>")
        return "\n".join(parts)

    parts.append('  <div class="blocks">')
    for heading in headings:
        text = escape(heading.text) if heading.text.strip() else "<em>(empty heading)</em>"
        indent = (heading.level - 1) * 18
        parts.append(
            f'    <div class="block h{heading.level}">'
            f'<span class="tag">h{heading.level}</span>'
            f'<span class="txt" style="padding-left:{indent}px">{text}</span>'
            f'<span class="ln">L{heading.line}</span></div>'
        )
    parts.append("  </div>")
    parts.append("</section>")
    return "\n".join(parts)


def _meta_section(inventory) -> str:
    metas = inventory.metas
    parts = ["<section>"]
    parts.append(f'  <h2>Meta tags <span class="count-pill">{len(metas)} tags</span></h2>')
    parts.append(
        '  <p class="section-note">Every <code>&lt;meta&gt;</code> element as served, in '
        "document order.</p>"
    )

    if not metas:
        parts.append('  <div class="clean">No meta tags found.</div>')
        parts.append("</section>")
        return "\n".join(parts)

    parts.append('  <div class="scroll-x"><table class="grid">')
    parts.append("    <tr><th>Attribute</th><th>Key</th><th>Content</th></tr>")
    for tag in metas:
        content = (
            escape(tag.content)
            if not tag.is_empty
            else '<span class="state empty">empty</span>'
        )
        parts.append(
            f"    <tr><td>{escape(tag.kind)}</td>"
            f'<td class="mono">{escape(tag.key)}</td><td>{content}</td></tr>'
        )
    parts.append("    </table></div>")
    parts.append("</section>")
    return "\n".join(parts)


def _canonical_section(inventory, findings) -> str:
    canonical = inventory.canonical
    parts = ["<section>"]
    state = "declared" if canonical.present else "missing"
    parts.append(f'  <h2>Canonical URL <span class="count-pill">{state}</span></h2>')
    parts.append(
        '  <p class="section-note">The canonical tells search engines which URL to index when '
        "the same content is reachable by more than one address.</p>"
    )

    if not canonical.present:
        parts.append(
            '  <div class="f-el">No &lt;link rel="canonical"&gt; on this page.</div>'
        )
    else:
        parts.append('  <div class="scroll-x"><table class="grid">')
        parts.append("    <tr><th>Property</th><th>Value</th></tr>")
        rows = [
            ("Declared canonical", escape(canonical.declared or "")),
            ("Page URL", escape(canonical.page_url)),
            ("Self-referencing", "yes" if canonical.is_self_referencing else "<b>no</b>"),
            ("Absolute URL", "yes" if canonical.is_absolute else "<b>no — should be absolute</b>"),
        ]
        for label, value in rows:
            parts.append(f'    <tr><td>{label}</td><td class="mono">{value}</td></tr>')
        parts.append("    </table></div>")

        if not canonical.is_self_referencing:
            parts.append(
                '  <p class="f-fix"><b>Note:</b> the canonical points at a different URL, so '
                "this page is asking not to be indexed in its own right. Intentional for "
                "duplicates and paginated views; a mistake everywhere else.</p>"
            )
        elif canonical.differs_only_by_trailing_slash:
            parts.append(
                '  <p class="f-fix"><b>Note:</b> the canonical matches this page apart from a '
                "trailing slash. Harmless, but make it byte-identical to avoid ambiguity.</p>"
            )

    related = [f for f in findings if "canonical" in f.rule]
    if related:
        parts.append('  <div style="margin-top:18px">')
        parts.extend(_finding_block(f) for f in related)
        parts.append("  </div>")

    parts.append("</section>")
    return "\n".join(parts)


def _index_follow_section(inventory) -> str:
    info = inventory.index_follow
    parts = ["<section>"]
    pill = escape(info.summary)
    parts.append(f'  <h2>Index / Follow <span class="count-pill">{pill}</span></h2>')
    parts.append(
        '  <p class="section-note">Crawler directives from both the markup and the HTTP '
        "response. A header-level <code>X-Robots-Tag</code> is invisible in the HTML and is a "
        'classic cause of "the page looks fine but will not rank".</p>'
    )

    parts.append('  <div class="scroll-x"><table class="grid">')
    parts.append("    <tr><th>Source</th><th>Value</th></tr>")
    for label, value in (
        ('&lt;meta name="robots"&gt;', info.robots_meta),
        ('&lt;meta name="googlebot"&gt;', info.googlebot_meta),
        ("X-Robots-Tag header", info.x_robots_tag),
    ):
        shown = (
            f'<span class="mono">{escape(value)}</span>'
            if value
            else '<span style="opacity:.6">not set</span>'
        )
        parts.append(f"    <tr><td>{label}</td><td>{shown}</td></tr>")
    parts.append(
        f'    <tr><td><b>Effective</b></td><td><b>{escape(info.summary)}</b></td></tr>'
    )
    parts.append("    </table></div>")

    if info.is_default:
        parts.append(
            '  <p class="f-fix"><b>Default:</b> nothing on the page restricts crawling, so it '
            "is treated as index, follow. No robots meta tag is needed to achieve that.</p>"
        )
    elif not info.indexable:
        parts.append(
            '  <p class="f-fix"><b>This page cannot rank.</b> A noindex directive is active. '
            "That is correct for thank-you pages and internal search results, and a serious "
            "problem anywhere else — it is frequently a staging directive left in after "
            "go-live.</p>"
        )
    elif not info.followable:
        parts.append(
            '  <p class="f-fix"><b>Links are not followed</b> from this page, so it passes no '
            "authority onward. Rarely intentional outside paid or user-generated pages.</p>"
        )

    parts.append("</section>")
    return "\n".join(parts)


def _image_size_section(report) -> str:
    parts = ["<section>"]

    if report is None or not report.checked:
        limit = report.limit_label if report is not None else "2.50 MB"
        parts.append(f'  <h2>Image size <span class="count-pill">not checked</span></h2>')
        parts.append(
            '  <p class="section-note">Measuring image weight needs one request per image, so '
            "it is off by default.</p>"
        )
        parts.append(
            '  <div class="f-el">Enable it with <b>--check-images</b> on the command line, or '
            'tick <b>"Check image sizes"</b> in the web UI. '
            f"Images over {escape(limit)} will be listed here.</div>"
        )
        parts.append("</section>")
        return "\n".join(parts)

    oversized = report.oversized
    parts.append(
        f'  <h2>Image size <span class="count-pill">over {escape(report.limit_label)}: '
        f'{len(oversized)}</span>'
        f'<span class="count-pill">{human_size(report.total_bytes)} total</span></h2>'
    )
    parts.append(
        f'  <p class="section-note">{len(report.measured)} image(s) measured'
        + (f", {len(report.unknown)} unavailable" if report.unknown else "")
        + (f", {report.not_checked} beyond the cap" if report.not_checked else "")
        + ". Sizes come from Content-Length, or a capped read where the server omits it.</p>"
    )

    if not oversized:
        parts.append(
            f'  <div class="clean"><b>&#10003; Clean.</b> No image exceeds '
            f"{escape(report.limit_label)}.</div>"
        )
    else:
        parts.append('  <div class="scroll-x"><table class="grid">')
        parts.append("    <tr><th>Size</th><th>Image source</th><th>Type</th><th>Line</th></tr>")
        for measurement in oversized:
            parts.append(
                f'    <tr><td><span class="state missing">{escape(measurement.display_size)}'
                f'</span></td><td class="mono">{escape(measurement.src)}</td>'
                f"<td>{escape(measurement.content_type or '—')}</td>"
                f"<td>{measurement.line}</td></tr>"
            )
        parts.append("    </table></div>")

    # Always show the full measured list; the heavy ones are only meaningful in context.
    others = [m for m in report.measurements if not m.exceeds(report.limit_bytes)]
    if others:
        ranked = sorted(others, key=lambda m: m.byte_size or -1, reverse=True)
        parts.append(
            f'  <p class="section-note" style="margin-top:22px">Remaining images, heaviest '
            f"first.</p>"
        )
        parts.append('  <div class="scroll-x"><table class="grid">')
        parts.append("    <tr><th>Size</th><th>Image source</th><th>Line</th></tr>")
        for measurement in ranked:
            label = escape(measurement.display_size)
            if measurement.error:
                label = f'<span style="opacity:.7">{escape(measurement.error)}</span>'
            parts.append(
                f'    <tr><td class="mono">{label}</td>'
                f'<td class="mono">{escape(measurement.src)}</td>'
                f"<td>{measurement.line}</td></tr>"
            )
        parts.append("    </table></div>")

    parts.append("</section>")
    return "\n".join(parts)


def _outline_section(inventory) -> str:
    outline = inventory.outline
    parts = ["<section>"]
    parts.append(
        f'  <h2>Page structure <span class="count-pill">{outline.total_nodes} elements</span>'
        f'<span class="count-pill">depth {outline.max_depth_seen}</span></h2>'
    )

    note = "Structural elements only — inline formatting is omitted so the page shape stays legible."
    if outline.was_truncated:
        dropped = outline.truncated_depth + outline.truncated_count
        note += f" {dropped} deeper or later element(s) not shown."
    parts.append(f'  <p class="section-note">{note}</p>')

    if not outline.rows:
        parts.append('  <div class="clean">No structural elements found.</div>')
        parts.append("</section>")
        return "\n".join(parts)

    parts.append('  <div class="tree">')
    for row in outline.rows:
        indent = "  " * row.depth
        children = (
            f'<span class="n">  ({row.child_count})</span>' if row.child_count else ""
        )
        # Split the selector so the tag and its id/classes can be coloured separately.
        tag_part = escape(row.tag)
        rest = escape(row.selector[len(row.tag) :])
        parts.append(
            f'    <div>{indent}<span class="t">{tag_part}</span>'
            f'<span class="q">{rest}</span>{children}</div>'
        )
    parts.append("  </div>")
    parts.append("</section>")
    return "\n".join(parts)


def _image_alt_section(inventory) -> str:
    images = inventory.images
    flagged = images.needs_attention

    parts = ["<section>"]
    parts.append(
        f'  <h2>Image alt text <span class="count-pill">{images.total} images</span>'
        f'<span class="count-pill">{images.coverage:.0f}% described</span></h2>'
    )
    parts.append(
        '  <p class="section-note">Source URLs for every image with no alt attribute or an '
        'explicitly empty one. <code>alt=""</code> is correct for purely decorative images — '
        "confirm each one genuinely carries no meaning.</p>"
    )

    if not flagged:
        parts.append(
            '  <div class="clean"><b>&#10003; Clean.</b> Every image has alt text.</div>'
        )
        parts.append("</section>")
        return "\n".join(parts)

    parts.append('  <div class="scroll-x"><table class="grid">')
    parts.append(
        "    <tr><th>State</th><th>Image source</th><th>Line</th><th>Dimensions</th></tr>"
    )
    for image in flagged:
        state = image.alt_state
        dimensions = (
            f"{image.width}&times;{image.height}" if image.width and image.height else "—"
        )
        parts.append(
            f'    <tr><td><span class="state {state}">{state}</span></td>'
            f'<td class="mono">{escape(image.src or "(no src)")}</td>'
            f"<td>{image.line}</td><td>{dimensions}</td></tr>"
        )
    parts.append("    </table></div>")
    parts.append("</section>")
    return "\n".join(parts)


def _schema_section(inventory) -> str:
    schema = inventory.schema
    parts = ["<section>"]
    parts.append(
        f'  <h2>Suggested schema.org markup '
        f'<span class="count-pill">{len(schema.suggested_types)} types</span></h2>'
    )
    parts.append(
        '  <p class="section-note">Generated from what is actually on the page — no '
        "placeholder values. Review before publishing; inaccurate structured data is worse "
        "than none.</p>"
    )

    parts.append('  <div class="typerow">')
    if schema.existing_types:
        for name in schema.existing_types:
            parts.append(f'    <span class="chip">already on page <b>{escape(name)}</b></span>')
    else:
        parts.append('    <span class="chip">no structured data <b>currently</b></span>')
    for name in schema.suggested_types:
        parts.append(f'    <span class="chip">suggested <b>{escape(name)}</b></span>')
    parts.append("  </div>")

    if schema.notes:
        parts.append('  <ul class="notes">')
        for note in schema.notes:
            parts.append(f"    <li>{escape(note)}</li>")
        parts.append("  </ul>")

    # Escaped, never a live <script> — the report must not execute anything.
    parts.append(f'  <pre class="code">{escape(schema.script_block)}</pre>')
    parts.append("</section>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------------------


@dataclass
class Page:
    """One sidebar entry and the panel it reveals."""

    key: str
    label: str
    icon: str
    group: str
    body: str
    badge: str = ""
    hot: bool = False


def _nav_css(keys: List[str]) -> str:
    """Per-page :checked rules. Generated because the page set varies by run."""
    rules = []
    for key in keys:
        rules.append(
            f"#tab-{key}:checked ~ .main .panels > #panel-{key} {{ display: block; }}\n"
            f'#tab-{key}:checked ~ .sidebar label[for="tab-{key}"] '
            "{ background: var(--accent-soft); color: var(--accent); font-weight: 620; }\n"
            f'#tab-{key}:checked ~ .main .topbar div[data-title="{key}"] {{ display: block; }}\n'
            f'#tab-{key}:focus-visible ~ .sidebar label[for="tab-{key}"] '
            "{ outline: 2px solid var(--accent); outline-offset: -2px; }"
        )
    return "\n".join(rules)


def _stat_card(label: str, value: str, note: str, icon_name: str, accent: bool = False) -> str:
    cls = " accent" if accent else ""
    return (
        f'<div class="stat{cls}">'
        f'<span class="corner">{icon(icon_name, 14)}</span>'
        f'<p class="k">{escape(label)}</p>'
        f'<p class="v">{escape(value)}</p>'
        f'<p class="d">{note}</p>'
        "</div>"
    )


def _overview_page(result: AuditResult) -> str:
    counts = result.counts
    total = sum(counts.values())
    inventory = result.inventory
    serious = counts["critical"] + counts["high"]
    report = result.image_sizes
    measured = report is not None and report.checked and bool(report.measurements)

    images = inventory.images if inventory else None
    weight = human_size(report.total_bytes) if measured else f"{result.byte_size / 1024:.0f} KB"
    weight_note = (
        f"{len(report.measured)} images measured" if measured else "HTML document only"
    )

    cards = [
        _stat_card(
            "Overall score",
            f"{result.overall_score:.0f}",
            f'<span class="tone">{len(result.packs)} categories</span>',
            "gauge",
            accent=True,
        ),
        _stat_card(
            "Findings",
            str(total),
            f'<span class="tone">{serious} need attention</span>'
            if serious
            else '<span class="tone">nothing serious</span>',
            "alert",
        ),
        _stat_card(
            "Images",
            str(images.total) if images else "0",
            f'<span class="tone">{len(images.needs_attention)} missing alt</span>'
            if images
            else "&nbsp;",
            "image",
        ),
        _stat_card("Page weight", weight, weight_note, "weight"),
    ]

    meters = []
    for pack in result.packs:
        width = max(0.0, min(100.0, pack.score))
        issues = len(pack.findings)
        plural = "s" if issues != 1 else ""
        meters.append(
            '<div class="meter-row">'
            f'<div class="mt"><span>{escape(pack.label)}</span>'
            f'<b style="color:{_score_color(pack.score)}">{pack.score:.0f}'
            f'<span style="color:var(--ink-3);font-weight:500"> &middot; {issues} issue{plural}'
            "</span></b></div>"
            f'<div class="meter"><i style="width:{width:.1f}%;'
            f'background:{_score_color(pack.score)}"></i></div>'
            "</div>"
        )

    legend = [
        f'<div class="legend-row">'
        f'<span class="legend-dot" style="background:var(--{severity.value})"></span>'
        f'<span class="lbl">{SEVERITY_LABEL[severity]}</span>'
        f'<span class="num">{counts[severity.value]}</span></div>'
        for severity in Severity
    ]

    facts = [
        ("Status", f"HTTP {result.status}"),
        ("Response time", f"{result.elapsed_ms} ms"),
        ("Document size", f"{result.byte_size / 1024:.1f} KB"),
        ("Scanned", result.fetched_at.replace("T", " ").replace("+00:00", " UTC")),
    ]
    if inventory is not None:
        facts.append(("Indexable", inventory.index_follow.summary))
        facts.append(("Canonical", "declared" if inventory.canonical.present else "missing"))
    if result.was_redirected:
        facts.append(("Redirected from", result.url))

    fact_rows = "".join(
        f'<li><span class="fk">{escape(k)}</span><span class="fv">{escape(str(v))}</span></li>'
        for k, v in facts
    )

    return (
        "<section>"
        f'<div class="grid-4">{"".join(cards)}</div>'
        '<div class="grid-2">'
        '<div class="card card-pad">'
        '<div class="card-head"><h3 class="card-title">Category scores</h3>'
        '<p class="card-note">100 minus weighted deductions</p></div>'
        f'<div class="meters">{"".join(meters)}</div>'
        "</div>"
        '<div class="card card-pad">'
        '<div class="card-head"><h3 class="card-title">Overall</h3></div>'
        f"{_ring(result.overall_score)}"
        f'<div class="legend" style="margin-top:20px">{"".join(legend)}</div>'
        "</div></div>"
        '<div class="grid-2">'
        '<div class="card card-pad">'
        '<div class="card-head"><h3 class="card-title">Response</h3></div>'
        f'<ul class="factlist">{fact_rows}</ul></div>'
        '<div class="card card-pad">'
        '<div class="card-head"><h3 class="card-title">Scope of this run</h3></div>'
        '<p class="card-note">Analysis is of the <b>served HTML</b>. Lighthouse performance '
        "metrics, axe-core accessibility rules, JavaScript-rendered content, and visual review "
        "require the browser-based modules and are not included.</p>"
        "</div></div>"
        "</section>"
    )


def _build_pages(result: AuditResult) -> List[Page]:
    """Sidebar pages.

    The eight requested sections keep the exact order they were asked for; grouping headings
    are cosmetic and must not reshuffle them. Anything else the audit produced follows, so no
    result becomes unreachable.
    """
    packs = {pack.module: pack for pack in result.packs}
    inventory = result.inventory
    document = result.document

    pages: List[Page] = [
        Page("overview", "Dashboard", "dashboard", "Overview", _overview_page(result))
    ]

    if "http" in packs:
        pages.append(
            Page("http", "HTTP Error", "alert", "Overview", _section(packs["http"]), "!", True)
        )

    audit_group = "Audit"

    if "seo" in packs:
        count = len(packs["seo"].findings)
        pages.append(
            Page("seo", "SEO", "search", audit_group, _section(packs["seo"]),
                 str(count) if count else "", bool(count))
        )

    if inventory is not None:
        headings = document.headings if document else []
        pages.append(
            Page("headings", "Headings", "heading", audit_group,
                 _headings_section(document), str(len(headings)))
        )
        pages.append(
            Page("meta", "Meta Tags", "tag", audit_group, _meta_section(inventory),
                 str(len(inventory.metas)))
        )
        canonical_ok = inventory.canonical.present and inventory.canonical.is_self_referencing
        pages.append(
            Page("canonical", "Canonical URLs", "link", audit_group,
                 _canonical_section(inventory, result.findings),
                 "ok" if canonical_ok else "check", not canonical_ok)
        )
        flagged = len(inventory.images.needs_attention)
        pages.append(
            Page("alt", "Alt Tag Missing", "image", audit_group, _image_alt_section(inventory),
                 str(flagged), bool(inventory.images.missing))
        )

    report = result.image_sizes
    if report is not None and report.checked:
        over = len(report.oversized)
        badge, hot = (str(over), True) if over else ("0", False)
    else:
        badge, hot = "off", False
    pages.append(
        Page("imgsize", "Image Size", "weight", audit_group, _image_size_section(report),
             badge, hot)
    )

    if inventory is not None:
        info = inventory.index_follow
        restricted = not (info.indexable and info.followable)
        pages.append(
            Page("robots", "Index / Follow", "eye", audit_group,
                 _index_follow_section(inventory),
                 "blocked" if restricted else "ok", restricted)
        )
        pages.append(
            Page("schema", "Schema", "code", audit_group, _schema_section(inventory),
                 str(len(inventory.schema.suggested_types)))
        )

    more = "More detail"

    if "images" in packs:
        count = len(packs["images"].findings)
        pages.append(
            Page("images", "Image Issues", "alert", more, _section(packs["images"]),
                 str(count) if count else "", bool(count))
        )

    if "assets" in packs and packs["assets"].findings:
        pages.append(
            Page("weightissues", "Weight Issues", "weight", more,
                 _section(packs["assets"]), str(len(packs["assets"].findings)), True)
        )

    if inventory is not None:
        pages.append(
            Page("structure", "Page Structure", "layers", more,
                 _outline_section(inventory), str(inventory.outline.total_nodes))
        )

    if "links" in packs:
        count = len(packs["links"].findings)
        pages.append(
            Page("links", "Links", "link", more, _section(packs["links"]),
                 str(count) if count else "", bool(count))
        )

    return pages


def render(result: AuditResult, serving: bool = False) -> str:
    """Render the full report.

    ``serving`` adds links only a running server can honour — the schema generator and a
    route back to the URL form. A saved file omits them rather than shipping dead links.
    """
    pages = _build_pages(result)

    radios = "\n".join(
        f'  <input type="radio" name="qa-nav" id="tab-{page.key}"'
        f'{" checked" if index == 0 else ""}>'
        for index, page in enumerate(pages)
    )

    nav_parts: List[str] = []
    current_group = None
    for page in pages:
        if page.group != current_group:
            current_group = page.group
            nav_parts.append(f'    <p class="navgroup">{escape(page.group)}</p>')
        pill = (
            f'<span class="pill{" hot" if page.hot else ""}">{escape(page.badge)}</span>'
            if page.badge
            else ""
        )
        nav_parts.append(
            f'    <label class="navitem" for="tab-{page.key}">{icon(page.icon)}'
            f'<span class="navlabel">{escape(page.label)}</span>{pill}</label>'
        )

    if serving:
        nav_parts.append('    <p class="navgroup">Tools</p>')
        nav_parts.append(
            f'    <a class="navitem" href="/schema">{icon("wand")}'
            '<span class="navlabel">Schema Generator</span></a>'
        )
        nav_parts.append(
            f'    <a class="navitem" href="/">{icon("back")}'
            '<span class="navlabel">Audit another page</span></a>'
        )

    titles = "\n".join(
        f'        <div data-title="{page.key}" class="pagetitle">'
        f"<h1>{escape(page.label)}</h1></div>"
        for page in pages
    )

    panels = "\n".join(
        f'        <div class="panel" id="panel-{page.key}">\n{page.body}\n        </div>'
        for page in pages
    )

    if serving:
        side_card = (
            '<div class="sidecard"><h4>Schema Generator</h4>'
            "<p>Paste content and get schema.org JSON-LD back.</p></div>"
        )
        actions = (
            '<a class="btn primary" href="/schema">Schema Generator</a>'
            '<a class="btn" href="/">New audit</a>'
        )
    else:
        side_card = (
            '<div class="sidecard"><h4>Run it yourself</h4>'
            "<p>Dependency-free. No install, no database.</p>"
            "<code>python -m audit --serve</code></div>"
        )
        actions = ""

    nav_rules = _nav_css([page.key for page in pages])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QA Audit — {escape(result.page_title)}</title>
<style>{_CSS}
.pagetitle {{ display: none; }}
{nav_rules}</style>
</head>
<body>
<div class="app" role="radiogroup" aria-label="Report sections">
{radios}

  <aside class="sidebar">
    <div class="brand">
      <span class="brand-mark">{BRAND_MARK}</span>
      <span><span class="brand-name">Website QA</span><br>
      <span class="brand-sub">Audit report</span></span>
    </div>
{chr(10).join(nav_parts)}
    <div class="sidefoot">{side_card}</div>
  </aside>

  <div class="main">
    <header class="topbar">
      <div class="topbar-main">
        <p class="crumb">Website QA Audit</p>
{titles}
        <p class="sub"><a href="{escape(result.final_url)}">{escape(result.final_url)}</a>
        &nbsp;&middot;&nbsp; {escape(result.page_title)}</p>
      </div>
      <div class="topbar-side">{actions}</div>
    </header>

    <div class="content">
      <div class="panels">
{panels}
      </div>

      <footer class="foot">
        Generated by <code>python -m audit</code> from the <b>AI Website QA Platform</b>
        &mdash; a dependency-free static HTML audit engine (Python standard library only,
        no third-party packages).<br>
        Analysis is of the <b>served HTML</b>. Lighthouse performance metrics, axe-core
        accessibility rules, JavaScript-rendered content, and visual review require the
        browser-based modules and are <b>not</b> part of this report.
      </footer>
    </div>
  </div>
</div>
</body>
</html>
"""
