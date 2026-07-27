"""Image rule pack — PRD Module 2, the checks that need only the parsed document.

Byte-level checks (actual file size, real dimensions) require fetching each asset and are
handled by the service-layer module rather than here.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from audit.findings import Finding, Severity
from audit.parse import Document

MODULE = "images"

# Alt text that is present but conveys nothing (PRD Module 2).
GENERIC_ALT_VALUES = frozenset(
    {
        "image",
        "photo",
        "img",
        "logo",
        "banner",
        "picture",
        "graphic",
        "icon",
        "untitled",
        "placeholder",
        "thumbnail",
    }
)

ALT_MAX_LENGTH = 125
MODERN_FORMATS = (".webp", ".avif")
LEGACY_FORMATS = (".png", ".jpg", ".jpeg")

# Images this far down the document are assumed below the fold and should lazy-load.
ABOVE_FOLD_IMAGE_COUNT = 2


def _finding(rule: str, severity: Severity, title: str, **kwargs) -> Finding:
    return Finding(rule=rule, module=MODULE, severity=severity, title=title, **kwargs)


def _extension(src: str) -> str:
    path = urlparse(src).path
    return os.path.splitext(path)[1].lower()


def _short(src: str, limit: int = 80) -> str:
    """Filename-ish label for report display."""
    name = urlparse(src).path.rsplit("/", 1)[-1] or src
    return name if len(name) <= limit else name[: limit - 1] + "…"


def run(doc: Document) -> Tuple[List[Finding], Dict[str, Any]]:
    findings: List[Finding] = []
    images = doc.images

    missing_alt = [img for img in images if img.alt is None]
    empty_alt = [img for img in images if img.alt == ""]
    generic_alt = [
        img
        for img in images
        if img.alt and img.alt.strip().lower() in GENERIC_ALT_VALUES
    ]
    long_alt = [img for img in images if img.alt and len(img.alt) > ALT_MAX_LENGTH]
    no_dimensions = [img for img in images if not (img.width and img.height)]
    legacy_format = [
        img
        for img in images
        if _extension(img.src) in LEGACY_FORMATS and not img.srcset and not doc.picture_sources
    ]
    no_lazy = [
        img
        for img in images
        if img.index > ABOVE_FOLD_IMAGE_COUNT and (img.loading or "").lower() != "lazy"
    ]
    missing_src = [img for img in images if not img.src]

    for img in missing_alt:
        findings.append(
            _finding(
                "image.missing-alt",
                Severity.HIGH,
                f"Image has no alt attribute: {_short(img.src)}",
                detail=f"Source: {img.src}",
                element=f'<img src="{_short(img.src)}">',
                line=img.line,
                recommendation="Add alt text describing the image's purpose. Screen readers "
                "announce the filename instead when alt is absent, which is close to useless. If "
                'the image is purely decorative, use alt="" so it is skipped deliberately.',
                meta={"src": img.src},
            )
        )

    if empty_alt:
        findings.append(
            _finding(
                "image.empty-alt",
                Severity.INFO,
                f'{len(empty_alt)} image(s) use alt="" (decorative)',
                detail="Files: " + ", ".join(_short(img.src) for img in empty_alt[:8]),
                line=empty_alt[0].line,
                recommendation='alt="" is correct for decorative images and screen readers will '
                "skip them. Confirm none of these actually carry meaning.",
            )
        )

    for img in generic_alt:
        findings.append(
            _finding(
                "image.generic-alt",
                Severity.MEDIUM,
                f"Alt text is generic: {img.alt!r} on {_short(img.src)}",
                detail=f"Source: {img.src}",
                element=f'alt="{img.alt}"',
                line=img.line,
                recommendation="Describe what the image shows and why it is on the page. "
                f"{img.alt!r} conveys no more than an empty alt would.",
                meta={"src": img.src, "alt": img.alt},
            )
        )

    if long_alt:
        findings.append(
            _finding(
                "image.alt-too-long",
                Severity.LOW,
                f"{len(long_alt)} image(s) have alt text over {ALT_MAX_LENGTH} characters",
                detail="Files: " + ", ".join(_short(img.src) for img in long_alt[:8]),
                line=long_alt[0].line,
                recommendation=f"Trim to roughly {ALT_MAX_LENGTH} characters. Some screen readers "
                "truncate beyond this; move longer explanations into surrounding copy or a caption.",
            )
        )

    if missing_src:
        findings.append(
            _finding(
                "image.missing-src",
                Severity.HIGH,
                f"{len(missing_src)} <img> element(s) have no resolvable src",
                line=missing_src[0].line,
                recommendation="Give each image a src, or remove the element. This commonly "
                "indicates a lazy-loader whose data attribute this audit did not recognise.",
            )
        )

    if no_dimensions:
        findings.append(
            _finding(
                "image.no-dimensions",
                Severity.LOW,
                f"{len(no_dimensions)} image(s) declare no width/height",
                detail="Files: " + ", ".join(_short(img.src) for img in no_dimensions[:8]),
                line=no_dimensions[0].line,
                recommendation="Set width and height attributes so the browser can reserve space "
                "before the image loads. Missing dimensions are a leading cause of Cumulative "
                "Layout Shift.",
            )
        )

    if legacy_format:
        findings.append(
            _finding(
                "image.legacy-format",
                Severity.LOW,
                f"{len(legacy_format)} image(s) served as PNG/JPEG with no modern alternative",
                detail="Files: " + ", ".join(_short(img.src) for img in legacy_format[:8]),
                line=legacy_format[0].line,
                recommendation="Serve WebP or AVIF via <picture> or a srcset, keeping the original "
                "as fallback. Typical saving is 25–50% of transfer size at equal quality.",
                meta={"candidates": [img.src for img in legacy_format[:20]]},
            )
        )

    if no_lazy:
        findings.append(
            _finding(
                "image.no-lazy-loading",
                Severity.LOW,
                f"{len(no_lazy)} below-the-fold image(s) load eagerly",
                detail="Files: " + ", ".join(_short(img.src) for img in no_lazy[:8]),
                line=no_lazy[0].line,
                recommendation='Add loading="lazy" to images below the fold so they do not compete '
                "with the initial render. Leave the hero image eager — lazy-loading it delays LCP.",
            )
        )

    duplicates = [src for src, count in Counter(img.src for img in images if img.src).items() if count > 1]
    if duplicates:
        findings.append(
            _finding(
                "image.duplicate-src",
                Severity.INFO,
                f"{len(duplicates)} image source(s) appear more than once",
                detail="Files: " + ", ".join(_short(src) for src in duplicates[:8]),
                recommendation="Usually harmless once cached, but repeated sources can indicate a "
                "component rendering more times than intended.",
            )
        )

    modern_count = sum(1 for img in images if _extension(img.src) in MODERN_FORMATS)
    stats = {
        "total_images": len(images),
        "missing_alt": len(missing_alt),
        "empty_alt": len(empty_alt),
        "generic_alt": len(generic_alt),
        "modern_format": modern_count,
        "lazy_loaded": sum(1 for img in images if (img.loading or "").lower() == "lazy"),
        "with_dimensions": len(images) - len(no_dimensions),
    }
    return findings, stats
