"""Link rule pack — the broken-link and mixed-content half of PRD Module 3.

This is the only pack that makes network requests beyond the initial page fetch, so it is
opt-in behind --check-links.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from audit.fetch import head_status
from audit.findings import Finding, Severity
from audit.parse import Document

MODULE = "links"

DEFAULT_MAX_LINKS = 40
DEFAULT_WORKERS = 8


def _finding(rule: str, severity: Severity, title: str, **kwargs) -> Finding:
    return Finding(rule=rule, module=MODULE, severity=severity, title=title, **kwargs)


def run(
    doc: Document,
    max_links: int = DEFAULT_MAX_LINKS,
    timeout: int = 10,
    verify_tls: bool = True,
    workers: int = DEFAULT_WORKERS,
) -> Tuple[List[Finding], Dict[str, Any]]:
    findings: List[Finding] = []

    page_is_https = urlparse(doc.url).scheme == "https"
    if page_is_https:
        _check_mixed_content(doc, findings)

    # Dedupe while preserving document order, then cap so a large page stays quick.
    seen = set()
    targets: List[str] = []
    for link in doc.links:
        if link.href not in seen and urlparse(link.href).scheme in ("http", "https"):
            seen.add(link.href)
            targets.append(link.href)

    truncated = max(0, len(targets) - max_links)
    targets = targets[:max_links]

    results: Dict[str, Optional[int]] = {}
    if targets:
        with ThreadPoolExecutor(max_workers=min(workers, len(targets))) as pool:
            statuses = pool.map(
                lambda url: head_status(url, timeout=timeout, verify_tls=verify_tls), targets
            )
            results = dict(zip(targets, statuses))

    text_by_href = {link.href: link.text for link in doc.links}

    broken = {url: code for url, code in results.items() if code is not None and code >= 400}
    unreachable = [url for url, code in results.items() if code is None]

    for url, code in sorted(broken.items(), key=lambda item: item[1], reverse=True):
        label = text_by_href.get(url) or url
        findings.append(
            _finding(
                "link.broken",
                Severity.HIGH if code == 404 else Severity.MEDIUM,
                f"HTTP {code} — {url}",
                detail=f"Link text: {label!r}",
                element=url,
                recommendation="Update the URL or remove the link. Broken links waste crawl budget "
                "and are among the most visible quality problems to a visitor.",
                meta={"status": code, "url": url},
            )
        )

    if unreachable:
        findings.append(
            _finding(
                "link.unreachable",
                Severity.MEDIUM,
                f"{len(unreachable)} link(s) could not be reached",
                detail="URLs: " + ", ".join(unreachable[:5]),
                recommendation="Verify these manually. A DNS failure, TLS error, or timeout can "
                "also mean the host simply blocks automated clients.",
                meta={"urls": unreachable[:20]},
            )
        )

    stats = {
        "links_found": len(doc.links),
        "unique_checked": len(targets),
        "not_checked": truncated,
        "broken": len(broken),
        "unreachable": len(unreachable),
        "ok": sum(1 for code in results.values() if code is not None and code < 400),
    }
    return findings, stats


def _check_mixed_content(doc: Document, findings: List[Finding]) -> None:
    """Insecure subresources on an HTTPS page get blocked or downgrade the padlock."""
    insecure_images = [img for img in doc.images if img.src.startswith("http://")]
    if insecure_images:
        findings.append(
            _finding(
                "link.mixed-content-image",
                Severity.MEDIUM,
                f"{len(insecure_images)} image(s) loaded over plain HTTP on an HTTPS page",
                detail="Sources: " + ", ".join(img.src for img in insecure_images[:5]),
                line=insecure_images[0].line,
                recommendation="Serve these over HTTPS. Browsers block or upgrade mixed content, "
                "so the images may not render at all.",
            )
        )

    insecure_links = [link for link in doc.links if link.href.startswith("http://")]
    if insecure_links:
        findings.append(
            _finding(
                "link.insecure-http",
                Severity.LOW,
                f"{len(insecure_links)} link(s) point at plain HTTP",
                detail="URLs: " + ", ".join(link.href for link in insecure_links[:5]),
                line=insecure_links[0].line,
                recommendation="Point these at the HTTPS equivalent to avoid an extra redirect and "
                "a downgrade warning.",
            )
        )
