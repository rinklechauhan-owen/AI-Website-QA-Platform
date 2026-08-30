"""Detect pages whose content is assembled by JavaScript in the browser.

This tool reads the HTML a server sends, which is what a crawler sees before any script runs.
On a React, Next, Vue or Angular site that HTML can be almost empty, and the audit would then
report a page with no headings and no content — findings that describe the *tool's* blind spot
rather than the site.

Reporting those as SEO problems would lead an SEO team to fix things that are not broken, so a
page that looks client-rendered is flagged as such and its other findings are qualified.

Detection is deliberately conservative: it takes several corroborating signals to call a page
client-rendered, because a false positive would wave away real problems on a normal page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Root elements frameworks mount into. Empty ones are the strongest single signal.
_MOUNT_POINTS = (
    ("__next", "Next.js"),
    ("root", "React"),
    ("app", "Vue or React"),
    ("__nuxt", "Nuxt"),
    ("q-app", "Quasar"),
    ("svelte", "Svelte"),
)

# Framework fingerprints that appear in the served markup.
_FRAMEWORK_MARKERS = (
    ("__NEXT_DATA__", "Next.js"),
    ("window.__NUXT__", "Nuxt"),
    ("data-reactroot", "React"),
    ("ng-version", "Angular"),
    ("data-server-rendered", "Vue"),
    ("__remixContext", "Remix"),
    ("wp-json/wp/v2", ""),  # neutral; ignored unless other signals agree
)

_SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>(.*?)</script>", re.I | re.S)
_EMPTY_MOUNT = re.compile(
    r"""<(?:div|main|section)\b[^>]*\bid=["']?(%s)["']?[^>]*>\s*</(?:div|main|section)>"""
    % "|".join(name for name, _ in _MOUNT_POINTS),
    re.I,
)

# A page with less visible text than this has very little for a crawler to read.
THIN_TEXT_CHARS = 500
# Script bytes outstripping text by this much suggests the page is an application shell.
SCRIPT_TO_TEXT_RATIO = 8.0


@dataclass
class RenderSignal:
    client_rendered: bool = False
    framework: str = ""
    reasons: List[str] = field(default_factory=list)
    script_bytes: int = 0
    text_chars: int = 0

    @property
    def ratio(self) -> float:
        return round(self.script_bytes / max(self.text_chars, 1), 1)

    @property
    def summary(self) -> str:
        if not self.client_rendered:
            return "Server-rendered"
        name = f"{self.framework} " if self.framework else ""
        return f"{name}content appears to be rendered in the browser".strip().capitalize()


def looks_client_rendered(document) -> RenderSignal:
    """Decide whether a page's content is assembled by script rather than served.

    Requires at least two independent signals. One alone is too weak: plenty of sound pages
    carry a framework marker while still serving their content.
    """
    signal = RenderSignal()
    if document is None:
        return signal

    html = document.html or ""
    signal.text_chars = document.text_length
    signal.script_bytes = sum(len(block) for block in _SCRIPT_BLOCK.findall(html))

    # 1. An empty element that a framework is going to mount into.
    empty_mount = _EMPTY_MOUNT.search(html)
    if empty_mount:
        matched = empty_mount.group(1).lower()
        signal.framework = next(
            (label for name, label in _MOUNT_POINTS if name == matched and label), ""
        )
        signal.reasons.append(f"empty <div id=\"{empty_mount.group(1)}\"> mount point")

    # 2. A framework fingerprint in the markup.
    for marker, label in _FRAMEWORK_MARKERS:
        if label and marker in html:
            signal.framework = signal.framework or label
            signal.reasons.append(f"{label} marker in the page source")
            break

    # 3. Very little visible text.
    if signal.text_chars < THIN_TEXT_CHARS:
        signal.reasons.append(f"only {signal.text_chars} characters of visible text")

    # 4. Script far outweighing content.
    if signal.script_bytes and signal.ratio >= SCRIPT_TO_TEXT_RATIO:
        signal.reasons.append(
            f"{signal.ratio:g}x more script than text ({signal.script_bytes:,} bytes of script)"
        )

    # 5. No headings at all, alongside plenty of script.
    if not document.headings and signal.script_bytes > 5000:
        signal.reasons.append("no headings in the served HTML")

    strong = bool(empty_mount)
    signal.client_rendered = (strong and len(signal.reasons) >= 2) or len(signal.reasons) >= 3
    return signal
