"""Audit orchestration: fetch a URL, parse it, run each rule pack, aggregate scores."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from audit import assets, inventory as inventory_module
from audit.assets import ImageSizeReport
from audit.fetch import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT, FetchError, Response, fetch
from audit.findings import (
    Finding,
    Severity,
    count_by_severity,
    score_from_findings,
    sort_findings,
)
from audit.inventory import PageInventory
from audit.parse import Document, parse
from audit.rules import images, links, seo

PACK_LABELS = {
    "seo": "SEO",
    "images": "Images",
    "links": "Links",
    "assets": "Image weight",
}


@dataclass
class PackResult:
    module: str
    label: str
    score: float
    findings: List[Finding] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "label": self.label,
            "score": self.score,
            "stats": self.stats,
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass
class AuditResult:
    url: str
    final_url: str
    status: int
    fetched_at: str
    elapsed_ms: int
    byte_size: int
    packs: List[PackResult] = field(default_factory=list)
    document: Optional[Document] = None
    # Extracts rather than findings — heading list, structure outline, meta tags, canonical,
    # robots directives, image alt inventory, schema.org. None if the page did not parse.
    inventory: Optional[PageInventory] = None
    # Populated only when image weight checking is enabled; it costs a request per image.
    image_sizes: Optional[ImageSizeReport] = None
    headers: Dict[str, str] = field(default_factory=dict)

    @property
    def findings(self) -> List[Finding]:
        collected: List[Finding] = []
        for pack in self.packs:
            collected.extend(pack.findings)
        return sort_findings(collected)

    @property
    def overall_score(self) -> float:
        if not self.packs:
            return 0.0
        return round(sum(pack.score for pack in self.packs) / len(self.packs), 1)

    @property
    def counts(self) -> Dict[str, int]:
        return count_by_severity(self.findings)

    @property
    def page_title(self) -> str:
        if self.document and self.document.title:
            return self.document.title
        return "(no title)"

    @property
    def was_redirected(self) -> bool:
        return self.final_url.rstrip("/") != self.url.rstrip("/")

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "fetched_at": self.fetched_at,
            "elapsed_ms": self.elapsed_ms,
            "byte_size": self.byte_size,
            "page_title": self.page_title,
            "overall_score": self.overall_score,
            "counts": self.counts,
            "packs": [pack.to_dict() for pack in self.packs],
        }
        if self.inventory is not None:
            payload["inventory"] = self.inventory.to_dict()
        if self.image_sizes is not None:
            payload["image_sizes"] = self.image_sizes.to_dict()
        return payload


def _normalise_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def audit_url(
    url: str,
    check_links: bool = False,
    max_links: int = links.DEFAULT_MAX_LINKS,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
    verify_tls: bool = True,
    content_tags: Sequence[str] = inventory_module.DEFAULT_CONTENT_TAGS,
    outline_depth: int = inventory_module.DEFAULT_MAX_OUTLINE_DEPTH,
    check_images: bool = False,
    image_size_limit: int = assets.DEFAULT_SIZE_LIMIT,
) -> AuditResult:
    """Fetch and audit a single URL.

    Raises FetchError if the page could not be retrieved at all; an HTTP error status or a
    non-HTML response comes back as a result carrying a critical finding instead.
    """
    url = _normalise_url(url)
    response = fetch(url, timeout=timeout, user_agent=user_agent, verify_tls=verify_tls)
    return audit_response(
        response,
        url,
        check_links,
        max_links,
        timeout,
        verify_tls,
        content_tags=content_tags,
        outline_depth=outline_depth,
        check_images=check_images,
        image_size_limit=image_size_limit,
    )


def audit_response(
    response: Response,
    requested_url: str,
    check_links: bool = False,
    max_links: int = links.DEFAULT_MAX_LINKS,
    timeout: int = DEFAULT_TIMEOUT,
    verify_tls: bool = True,
    content_tags: Sequence[str] = inventory_module.DEFAULT_CONTENT_TAGS,
    outline_depth: int = inventory_module.DEFAULT_MAX_OUTLINE_DEPTH,
    check_images: bool = False,
    image_size_limit: int = assets.DEFAULT_SIZE_LIMIT,
) -> AuditResult:
    """Audit an already-fetched response. Split out so tests can supply fixtures."""
    result = AuditResult(
        url=requested_url,
        final_url=response.url,
        status=response.status,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        elapsed_ms=response.elapsed_ms,
        byte_size=response.byte_size,
        headers=dict(response.headers),
    )

    if response.status >= 400:
        result.packs.append(
            PackResult(
                module="http",
                label="HTTP",
                score=0.0,
                findings=[
                    Finding(
                        rule="http.error-status",
                        module="http",
                        severity=Severity.CRITICAL,
                        title=f"Page returned HTTP {response.status}",
                        detail=f"Requested {requested_url}, final URL {response.url}.",
                        recommendation="The page must return 200 before the remaining audits mean "
                        "anything.",
                        meta={"status": response.status},
                    )
                ],
            )
        )
        return result

    if not response.is_html:
        result.packs.append(
            PackResult(
                module="http",
                label="HTTP",
                score=0.0,
                findings=[
                    Finding(
                        rule="http.not-html",
                        module="http",
                        severity=Severity.CRITICAL,
                        title=f"Response is not HTML ({response.content_type or 'unknown type'})",
                        recommendation="Point the audit at an HTML page.",
                    )
                ],
            )
        )
        return result

    document = parse(response.body, response.url)
    result.document = document
    result.inventory = inventory_module.build(
        document,
        content_tags=content_tags,
        max_outline_depth=outline_depth,
        headers=response.headers,
    )

    for module in (seo, images):
        pack_findings, stats = module.run(document)
        result.packs.append(
            PackResult(
                module=module.MODULE,
                label=PACK_LABELS[module.MODULE],
                score=score_from_findings(pack_findings),
                findings=sort_findings(pack_findings),
                stats=stats,
            )
        )

    if check_images:
        pack_findings, stats, report = assets.run(
            document, limit=image_size_limit, timeout=timeout, verify_tls=verify_tls
        )
        result.image_sizes = report
        result.packs.append(
            PackResult(
                module=assets.MODULE,
                label=PACK_LABELS[assets.MODULE],
                score=score_from_findings(pack_findings),
                findings=sort_findings(pack_findings),
                stats=stats,
            )
        )
    else:
        result.image_sizes = ImageSizeReport(limit_bytes=image_size_limit, checked=False)

    if check_links:
        pack_findings, stats = links.run(
            document, max_links=max_links, timeout=timeout, verify_tls=verify_tls
        )
        result.packs.append(
            PackResult(
                module=links.MODULE,
                label=PACK_LABELS[links.MODULE],
                score=score_from_findings(pack_findings),
                findings=sort_findings(pack_findings),
                stats=stats,
            )
        )

    return result


__all__ = ["AuditResult", "PackResult", "FetchError", "audit_url", "audit_response"]
