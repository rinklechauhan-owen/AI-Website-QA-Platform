"""Self-contained HTML report.

Everything is inlined — no external CSS, fonts, scripts, or images — so the file can be
emailed, committed, or opened straight off disk and still render identically.
"""

from __future__ import annotations

from html import escape
from typing import List

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

_CSS = """
* { box-sizing: border-box; }

:root {
  color-scheme: light dark;
  --bg: #f7f8fa;
  --card: #ffffff;
  --border: #e4e7ec;
  --ink: #101828;
  --ink-muted: #667085;
  --ink-faint: #98a2b3;
  --accent: #2563eb;
  --critical: #b42318;
  --high: #d92d20;
  --medium: #dc6803;
  --low: #0e7490;
  --info: #667085;
  --good: #12b76a;
  --warn: #f79009;
  --bad: #f04438;
  --shadow: 0 1px 2px rgba(16, 24, 40, .06), 0 1px 3px rgba(16, 24, 40, .1);
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0c111d;
    --card: #161b26;
    --border: #262b37;
    --ink: #f5f5f6;
    --ink-muted: #94969c;
    --ink-faint: #6c6f7a;
    --accent: #60a5fa;
    --critical: #fda29b;
    --high: #f97066;
    --medium: #fdb022;
    --low: #67e8f9;
    --info: #94969c;
    --shadow: none;
  }
}

body {
  margin: 0;
  padding: 40px 20px 72px;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}

.wrap { max-width: 940px; margin: 0 auto; }

/* --- header --- */
.head { display: flex; flex-wrap: wrap; gap: 28px; align-items: center;
        background: var(--card); border: 1px solid var(--border); border-radius: 14px;
        padding: 28px; box-shadow: var(--shadow); }
.head-main { flex: 1 1 380px; min-width: 0; }
.eyebrow { font-size: 11px; letter-spacing: .09em; text-transform: uppercase;
           color: var(--ink-faint); font-weight: 600; margin: 0 0 8px; }
h1 { font-size: 21px; line-height: 1.3; margin: 0 0 6px; font-weight: 650; word-break: break-word; }
.url { margin: 0 0 14px; font-size: 13px; word-break: break-all; }
.url a { color: var(--accent); text-decoration: none; }
.url a:hover { text-decoration: underline; }
.facts { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 0; font-size: 12.5px;
         color: var(--ink-muted); list-style: none; padding: 0; }
.facts b { color: var(--ink); font-weight: 600; }

/* --- score ring --- */
.ring { position: relative; width: 128px; height: 128px; flex: 0 0 auto; }
.ring svg { transform: rotate(-90deg); }
.ring-track { stroke: var(--border); }
.ring-val { stroke-linecap: round; }
.ring-text { position: absolute; inset: 0; display: flex; flex-direction: column;
             align-items: center; justify-content: center; }
.ring-num { font-size: 31px; font-weight: 680; letter-spacing: -.02em; line-height: 1; }
.ring-of { font-size: 10.5px; color: var(--ink-faint); text-transform: uppercase;
           letter-spacing: .08em; margin-top: 5px; }

/* --- severity chips --- */
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 22px 0 0; }
.chip { display: inline-flex; align-items: baseline; gap: 7px; padding: 6px 13px;
        border-radius: 999px; border: 1px solid var(--border); background: var(--card);
        font-size: 12.5px; color: var(--ink-muted); }
.chip b { font-size: 14px; font-weight: 660; }
.chip.critical b { color: var(--critical); }
.chip.high b { color: var(--high); }
.chip.medium b { color: var(--medium); }
.chip.low b { color: var(--low); }
.chip.info b { color: var(--info); }

/* --- pack summary cards --- */
.packs { display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
         gap: 12px; margin: 12px 0 0; }
.pack-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
             padding: 16px 18px; box-shadow: var(--shadow); }
.pack-card .name { font-size: 12px; text-transform: uppercase; letter-spacing: .07em;
                   color: var(--ink-faint); font-weight: 600; }
.pack-card .val { font-size: 26px; font-weight: 660; letter-spacing: -.02em; margin: 6px 0 10px; }
.meter { height: 5px; border-radius: 999px; background: var(--border); overflow: hidden; }
.meter span { display: block; height: 100%; border-radius: 999px; }
.pack-card .sub { font-size: 12px; color: var(--ink-muted); margin-top: 9px; }

/* --- sections --- */
section { margin-top: 40px; }
h2 { font-size: 15.5px; font-weight: 650; margin: 0 0 4px;
     display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.count-pill { font-size: 11.5px; font-weight: 600; color: var(--ink-muted);
              background: var(--bg); border: 1px solid var(--border);
              padding: 2px 9px; border-radius: 999px; }
.section-note { margin: 0 0 16px; font-size: 12.5px; color: var(--ink-muted); }

/* --- stats --- */
.stats { display: flex; flex-wrap: wrap; gap: 7px; margin: 0 0 18px; padding: 0; list-style: none; }
.stats li { font-size: 12px; color: var(--ink-muted); background: var(--card);
            border: 1px solid var(--border); border-radius: 7px; padding: 5px 11px; }
.stats b { color: var(--ink); font-weight: 620; }

/* --- findings --- */
.finding { background: var(--card); border: 1px solid var(--border);
           border-left: 3px solid var(--border); border-radius: 10px;
           padding: 16px 18px; margin-bottom: 10px; box-shadow: var(--shadow); }
.finding.critical { border-left-color: var(--critical); }
.finding.high     { border-left-color: var(--high); }
.finding.medium   { border-left-color: var(--medium); }
.finding.low      { border-left-color: var(--low); }
.finding.info     { border-left-color: var(--info); }

.f-top { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.badge { font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
         padding: 3px 8px; border-radius: 5px; flex: 0 0 auto; color: #fff; }
.badge.critical { background: var(--critical); }
.badge.high     { background: var(--high); }
.badge.medium   { background: var(--medium); }
.badge.low      { background: var(--low); }
.badge.info     { background: var(--info); }
@media (prefers-color-scheme: dark) { .badge { color: #0c111d; } }

.f-title { font-weight: 600; font-size: 14.5px; flex: 1 1 260px; min-width: 0;
           word-break: break-word; }
.f-rule { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-size: 11.5px; color: var(--ink-faint); }
.f-detail { margin: 9px 0 0; font-size: 13.5px; color: var(--ink-muted); word-break: break-word; }
.f-el { margin: 10px 0 0; padding: 9px 11px; background: var(--bg); border: 1px solid var(--border);
        border-radius: 7px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 12px; color: var(--ink-muted); overflow-x: auto; white-space: pre-wrap;
        word-break: break-all; }
.f-fix { margin: 11px 0 0; padding-left: 12px; border-left: 2px solid var(--border);
         font-size: 13.5px; }
.f-fix b { font-weight: 620; }

.clean { background: var(--card); border: 1px solid var(--border); border-radius: 10px;
         padding: 18px; font-size: 13.5px; color: var(--ink-muted); }
.clean b { color: var(--good); }

/* --- inventory: content listing --- */
.blocks { display: flex; flex-direction: column; gap: 1px; background: var(--border);
          border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.block { display: flex; gap: 12px; padding: 10px 14px; background: var(--card);
         align-items: baseline; }
.block .tag { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
              font-size: 11px; font-weight: 700; text-transform: uppercase; flex: 0 0 34px;
              color: var(--ink-faint); }
.block.h1 .tag, .block.h2 .tag, .block.h3 .tag { color: var(--accent); }
.block .txt { flex: 1 1 auto; min-width: 0; font-size: 13.5px; word-break: break-word; }
.block.h1 .txt { font-weight: 640; font-size: 15px; }
.block.h2 .txt { font-weight: 620; }
.block.h3 .txt { font-weight: 600; }
.block.p .txt { color: var(--ink-muted); }
.block .ln { flex: 0 0 auto; font-size: 11px; color: var(--ink-faint);
             font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

/* --- inventory: structure outline --- */
.tree { background: var(--card); border: 1px solid var(--border); border-radius: 10px;
        padding: 14px 16px; overflow-x: auto;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 12.5px; line-height: 1.75; }
.tree div { white-space: pre; }
.tree .t { color: var(--accent); }
.tree .q { color: var(--ink-muted); }
.tree .n { color: var(--ink-faint); }

/* --- inventory: tables --- */
table.grid { width: 100%; border-collapse: collapse; background: var(--card);
             border: 1px solid var(--border); border-radius: 10px; overflow: hidden;
             font-size: 13px; }
table.grid th { text-align: left; font-size: 11px; text-transform: uppercase;
                letter-spacing: .06em; color: var(--ink-faint); font-weight: 600;
                padding: 9px 14px; border-bottom: 1px solid var(--border); }
table.grid td { padding: 9px 14px; border-bottom: 1px solid var(--border);
                vertical-align: top; word-break: break-all; }
table.grid tr:last-child td { border-bottom: none; }
table.grid td.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                     font-size: 12px; }
.state { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
         padding: 2px 7px; border-radius: 4px; white-space: nowrap; color: #fff; }
.state.missing { background: var(--high); }
.state.empty { background: var(--medium); }
@media (prefers-color-scheme: dark) { .state { color: #0c111d; } }
.scroll-x { overflow-x: auto; }

/* --- inventory: schema --- */
pre.code { background: var(--card); border: 1px solid var(--border); border-radius: 10px;
           padding: 14px 16px; overflow-x: auto; font-size: 12.5px; line-height: 1.6;
           font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
           color: var(--ink); margin: 0; }
.notes { margin: 0 0 14px; padding-left: 18px; font-size: 13px; color: var(--ink-muted); }
.notes li { margin-bottom: 4px; }
.typerow { display: flex; flex-wrap: wrap; gap: 7px; margin: 0 0 14px; }

footer { margin-top: 44px; padding-top: 20px; border-top: 1px solid var(--border);
         font-size: 12px; color: var(--ink-faint); line-height: 1.7; }
footer code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

@media (max-width: 600px) {
  body { padding: 20px 14px 48px; }
  .head { padding: 20px; gap: 20px; }
  .ring { width: 104px; height: 104px; }
  .ring-num { font-size: 26px; }
}

@media print {
  body { background: #fff; padding: 0; }
  .finding, .pack-card, .head { box-shadow: none; break-inside: avoid; }
}
"""


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


def _content_section(inventory) -> str:
    content = inventory.content
    counts = content.counts
    summary = " · ".join(f"{count} &lt;{tag}&gt;" for tag, count in counts.items() if count)

    parts = ["<section>"]
    parts.append(
        f'  <h2>Page content <span class="count-pill">{len(content.blocks)} blocks</span>'
        f'<span class="count-pill">{content.total_words} words</span></h2>'
    )
    parts.append(
        f'  <p class="section-note">Every heading and paragraph in document order. '
        f"{summary or 'No matching content found.'}</p>"
    )

    if not content.blocks:
        parts.append('  <div class="clean">No content blocks matched the selected tags.</div>')
        parts.append("</section>")
        return "\n".join(parts)

    parts.append('  <div class="blocks">')
    for block in content.blocks:
        parts.append(
            f'    <div class="block {block.tag}"><span class="tag">{block.tag}</span>'
            f'<span class="txt">{escape(block.text)}</span>'
            f'<span class="ln">L{block.line}</span></div>'
        )
    parts.append("  </div>")
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


def render(result: AuditResult) -> str:
    counts = result.counts
    total = sum(counts.values())

    chips: List[str] = []
    for severity in Severity:
        value = counts[severity.value]
        if value:
            chips.append(
                f'<span class="chip {severity.value}"><b>{value}</b> '
                f"{SEVERITY_LABEL[severity]}</span>"
            )
    if not chips:
        chips.append('<span class="chip"><b>0</b> issues</span>')

    facts = [
        f"<li><b>HTTP {result.status}</b></li>",
        f"<li><b>{result.elapsed_ms}</b> ms</li>",
        f"<li><b>{result.byte_size / 1024:.1f}</b> KB</li>",
        f"<li><b>{total}</b> finding{'s' if total != 1 else ''}</li>",
        f"<li>Scanned <b>{escape(result.fetched_at)}</b></li>",
    ]
    if result.was_redirected:
        facts.append(f"<li>Redirected from <b>{escape(result.url)}</b></li>")

    sections = "\n".join(_section(pack) for pack in result.packs)
    pack_cards = "\n".join(_pack_card(pack) for pack in result.packs)

    if result.inventory is not None:
        sections += "\n" + "\n".join(
            (
                _content_section(result.inventory),
                _outline_section(result.inventory),
                _image_alt_section(result.inventory),
                _schema_section(result.inventory),
            )
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QA Audit — {escape(result.page_title)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">

<header class="head">
  <div class="head-main">
    <p class="eyebrow">Website QA Audit</p>
    <h1>{escape(result.page_title)}</h1>
    <p class="url"><a href="{escape(result.final_url)}">{escape(result.final_url)}</a></p>
    <ul class="facts">
{chr(10).join("      " + f for f in facts)}
    </ul>
  </div>
  {_ring(result.overall_score)}
</header>

<div class="chips">
  {" ".join(chips)}
</div>

<div class="packs">
{pack_cards}
</div>

{sections}

<footer>
  Generated by <code>python -m audit</code> from the
  <b>AI Website QA Platform</b> &mdash; a dependency-free static HTML audit engine
  (Python standard library only, no third-party packages).<br>
  Scope of this run: SEO metadata, heading structure, image accessibility and optimisation
  hints, and&mdash;when enabled&mdash;link reachability, plus a content listing, structure
  outline, image alt inventory, and generated schema.org markup. Analysis is of the
  <b>served HTML</b>: Lighthouse performance metrics, axe-core accessibility rules,
  JavaScript-rendered content, and visual/design review require the browser-based modules
  and are <b>not</b> part of this report.
</footer>

</div>
</body>
</html>
"""
