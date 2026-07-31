"""Measure the transfer weight of a page's images.

The only part of the engine that fetches subresources, so it is opt-in: a page with fifty
images means fifty extra requests against someone else's server.

Sizes come from a HEAD request's Content-Length where possible. When a server omits it —
common with chunked or dynamically generated responses — the image is streamed only as far
as one byte past the limit, which is enough to answer "is this too big?" without downloading
a 40 MB asset to find out.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from audit.fetch import DEFAULT_USER_AGENT, build_opener
from audit.findings import Finding, Severity
from audit.parse import Document

MODULE = "assets"

# 2.5 MB, the threshold above which an image is treated as a problem.
DEFAULT_SIZE_LIMIT = int(2.5 * 1024 * 1024)

DEFAULT_MAX_IMAGES = 60
DEFAULT_WORKERS = 8
DEFAULT_TIMEOUT = 15

_KB = 1024
_MB = 1024 * 1024


def human_size(num_bytes: Optional[int]) -> str:
    if num_bytes is None:
        return "unknown"
    if num_bytes >= _MB:
        return f"{num_bytes / _MB:.2f} MB"
    if num_bytes >= _KB:
        return f"{num_bytes / _KB:.0f} KB"
    return f"{num_bytes} B"


@dataclass
class ImageMeasurement:
    src: str
    byte_size: Optional[int] = None
    content_type: str = ""
    line: int = 0
    error: Optional[str] = None
    # True when the size is a floor rather than exact: streaming stopped at the cap.
    at_least: bool = False

    @property
    def known(self) -> bool:
        return self.byte_size is not None

    @property
    def display_size(self) -> str:
        if not self.known:
            return "unknown"
        prefix = ">" if self.at_least else ""
        return prefix + human_size(self.byte_size)

    def exceeds(self, limit: int) -> bool:
        return self.byte_size is not None and self.byte_size > limit


@dataclass
class ImageSizeReport:
    limit_bytes: int = DEFAULT_SIZE_LIMIT
    checked: bool = False
    measurements: List[ImageMeasurement] = field(default_factory=list)
    not_checked: int = 0

    @property
    def oversized(self) -> List[ImageMeasurement]:
        return sorted(
            (m for m in self.measurements if m.exceeds(self.limit_bytes)),
            key=lambda m: m.byte_size or 0,
            reverse=True,
        )

    @property
    def measured(self) -> List[ImageMeasurement]:
        return [m for m in self.measurements if m.known]

    @property
    def unknown(self) -> List[ImageMeasurement]:
        return [m for m in self.measurements if not m.known]

    @property
    def total_bytes(self) -> int:
        return sum(m.byte_size or 0 for m in self.measurements)

    @property
    def heaviest(self) -> Optional[ImageMeasurement]:
        measured = self.measured
        return max(measured, key=lambda m: m.byte_size or 0) if measured else None

    @property
    def limit_label(self) -> str:
        return human_size(self.limit_bytes)

    def stats(self) -> Dict[str, Any]:
        return {
            "images_measured": len(self.measured),
            "size_unknown": len(self.unknown),
            "not_checked": self.not_checked,
            "over_limit": len(self.oversized),
            "total_weight": human_size(self.total_bytes),
            "limit": self.limit_label,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checked": self.checked,
            "limit_bytes": self.limit_bytes,
            "limit": self.limit_label,
            "total_bytes": self.total_bytes,
            "not_checked": self.not_checked,
            "images": [
                {
                    "src": m.src,
                    "bytes": m.byte_size,
                    "size": m.display_size,
                    "content_type": m.content_type,
                    "line": m.line,
                    "error": m.error,
                    "over_limit": m.exceeds(self.limit_bytes),
                }
                for m in sorted(
                    self.measurements, key=lambda m: m.byte_size or -1, reverse=True
                )
            ],
        }


def _measure_one(
    src: str,
    line: int,
    limit: int,
    timeout: int,
    verify_tls: bool,
    user_agent: str,
) -> ImageMeasurement:
    measurement = ImageMeasurement(src=src, line=line)
    opener = build_opener(verify_tls)
    headers = {"User-Agent": user_agent, "Accept": "image/*,*/*;q=0.8"}

    # HEAD first: a Content-Length answers the question without transferring the file.
    try:
        request = urllib.request.Request(src, method="HEAD", headers=headers)
        with opener.open(request, timeout=timeout) as response:
            measurement.content_type = response.headers.get("Content-Type", "")
            length = response.headers.get("Content-Length")
            if length and length.isdigit():
                measurement.byte_size = int(length)
                return measurement
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        # Plenty of servers reject HEAD outright; fall through to the ranged read.
        pass

    try:
        request = urllib.request.Request(src, method="GET", headers=headers)
        with opener.open(request, timeout=timeout) as response:
            measurement.content_type = response.headers.get("Content-Type", "")
            length = response.headers.get("Content-Length")
            if length and length.isdigit():
                measurement.byte_size = int(length)
                return measurement

            # No Content-Length: read just past the limit, enough to decide.
            cap = limit + 1
            body = response.read(cap)
            measurement.byte_size = len(body)
            measurement.at_least = len(body) >= cap
    except urllib.error.HTTPError as exc:
        measurement.error = f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        measurement.error = str(getattr(exc, "reason", exc))[:120]

    return measurement


def measure(
    doc: Document,
    limit: int = DEFAULT_SIZE_LIMIT,
    timeout: int = DEFAULT_TIMEOUT,
    verify_tls: bool = True,
    max_images: int = DEFAULT_MAX_IMAGES,
    workers: int = DEFAULT_WORKERS,
    user_agent: str = DEFAULT_USER_AGENT,
) -> ImageSizeReport:
    """Fetch the size of each distinct image on the page."""
    report = ImageSizeReport(limit_bytes=limit, checked=True)

    # Deduplicate by source: the same file used five times is one request.
    seen: Dict[str, int] = {}
    for image in doc.images:
        if image.src.startswith(("http://", "https://")) and image.src not in seen:
            seen[image.src] = image.line

    targets = list(seen.items())
    report.not_checked = max(0, len(targets) - max_images)
    targets = targets[:max_images]

    if not targets:
        return report

    with ThreadPoolExecutor(max_workers=min(workers, len(targets))) as pool:
        report.measurements = list(
            pool.map(
                lambda item: _measure_one(
                    item[0], item[1], limit, timeout, verify_tls, user_agent
                ),
                targets,
            )
        )

    return report


def findings_from(report: ImageSizeReport) -> List[Finding]:
    """Turn oversized images into findings. One per image — each needs its own fix."""
    findings: List[Finding] = []

    for measurement in report.oversized:
        excess = (measurement.byte_size or 0) - report.limit_bytes
        findings.append(
            Finding(
                rule="image.oversized",
                module=MODULE,
                severity=Severity.HIGH,
                title=f"{measurement.display_size} — {measurement.src.rsplit('/', 1)[-1]}",
                detail=f"Source: {measurement.src}",
                line=measurement.line,
                recommendation=(
                    f"Over the {report.limit_label} limit by {human_size(excess)}. Re-export at "
                    "the largest size actually displayed, convert to WebP or AVIF, and serve "
                    "responsive variants with srcset. Images of this weight dominate Largest "
                    "Contentful Paint on slower connections."
                ),
                meta={
                    "src": measurement.src,
                    "bytes": measurement.byte_size,
                    "limit_bytes": report.limit_bytes,
                    "content_type": measurement.content_type,
                },
            )
        )

    unreachable = [m for m in report.measurements if m.error]
    if unreachable:
        findings.append(
            Finding(
                rule="image.unreachable",
                module=MODULE,
                severity=Severity.MEDIUM,
                title=f"{len(unreachable)} image(s) could not be fetched",
                detail="; ".join(f"{m.src} ({m.error})" for m in unreachable[:5]),
                recommendation="Confirm these load for a real visitor. A broken image source is "
                "usually a deploy or path problem rather than a slow server.",
                meta={"sources": [m.src for m in unreachable[:20]]},
            )
        )

    return findings


def run(
    doc: Document,
    limit: int = DEFAULT_SIZE_LIMIT,
    timeout: int = DEFAULT_TIMEOUT,
    verify_tls: bool = True,
    max_images: int = DEFAULT_MAX_IMAGES,
) -> Tuple[List[Finding], Dict[str, Any], ImageSizeReport]:
    report = measure(
        doc, limit=limit, timeout=timeout, verify_tls=verify_tls, max_images=max_images
    )
    return findings_from(report), report.stats(), report
