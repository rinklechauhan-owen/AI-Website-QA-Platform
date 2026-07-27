"""SEO rule pack — PRD Module 3, the checks that need only the parsed document."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from audit.findings import Finding, Severity
from audit.parse import Document

MODULE = "seo"

TITLE_MIN = 15
TITLE_MAX = 60
DESCRIPTION_MIN = 50
DESCRIPTION_MAX = 160
THIN_CONTENT_CHARS = 300

# Link text that tells neither a user nor a crawler where the link goes.
NON_DESCRIPTIVE_LINK_TEXT = frozenset(
    {"click here", "here", "read more", "more", "link", "this", "learn more", "details"}
)

REQUIRED_OG_TAGS = ("og:title", "og:description", "og:image")


def _finding(rule: str, severity: Severity, title: str, **kwargs) -> Finding:
    return Finding(rule=rule, module=MODULE, severity=severity, title=title, **kwargs)


def run(doc: Document) -> Tuple[List[Finding], Dict[str, Any]]:
    findings: List[Finding] = []

    _check_title(doc, findings)
    _check_description(doc, findings)
    _check_robots(doc, findings)
    _check_canonical(doc, findings)
    _check_headings(doc, findings)
    _check_lang_and_viewport(doc, findings)
    _check_social(doc, findings)
    _check_structured_data(doc, findings)
    _check_content(doc, findings)
    _check_link_text(doc, findings)

    stats = {
        "title_length": len(doc.title or ""),
        "description_length": len(doc.meta("description") or ""),
        "h1_count": len(doc.headings_at(1)),
        "heading_count": len(doc.headings),
        "internal_links": len(doc.internal_links()),
        "external_links": len(doc.external_links()),
        "structured_data_blocks": len(doc.jsonld_blocks),
        "text_length": doc.text_length,
    }
    return findings, stats


def _check_title(doc: Document, findings: List[Finding]) -> None:
    if not doc.title:
        findings.append(
            _finding(
                "seo.missing-title",
                Severity.HIGH,
                "Page has no <title>",
                detail="The title is the strongest on-page ranking signal and the clickable "
                "headline in search results.",
                recommendation=f"Add a unique <title> of {TITLE_MIN}–{TITLE_MAX} characters "
                "that leads with the page's primary keyword.",
            )
        )
        return

    length = len(doc.title)
    if length < TITLE_MIN:
        findings.append(
            _finding(
                "seo.title-too-short",
                Severity.MEDIUM,
                f"Title is only {length} characters",
                detail=f"Current title: {doc.title!r}",
                element=doc.title,
                recommendation=f"Expand to at least {TITLE_MIN} characters to describe the page "
                "and include the brand name.",
            )
        )
    elif length > TITLE_MAX:
        findings.append(
            _finding(
                "seo.title-too-long",
                Severity.LOW,
                f"Title is {length} characters and will be truncated",
                detail=f"Current title: {doc.title!r}",
                element=doc.title,
                recommendation=f"Trim to {TITLE_MAX} characters or fewer so Google shows it in "
                "full. Put the important words first.",
            )
        )


def _check_description(doc: Document, findings: List[Finding]) -> None:
    description = doc.meta("description")

    if description is None:
        findings.append(
            _finding(
                "seo.missing-meta-description",
                Severity.HIGH,
                "Page has no meta description",
                detail="Without one, search engines synthesise a snippet from page copy, which "
                "usually reads poorly and lowers click-through rate.",
                recommendation=f"Add a meta description of {DESCRIPTION_MIN}–{DESCRIPTION_MAX} "
                "characters that summarises the page and contains a call to action.",
            )
        )
        return

    length = len(description)
    if length == 0:
        findings.append(
            _finding(
                "seo.empty-meta-description",
                Severity.HIGH,
                "Meta description is empty",
                recommendation="Populate the description or remove the empty tag.",
            )
        )
    elif length < DESCRIPTION_MIN:
        findings.append(
            _finding(
                "seo.meta-description-too-short",
                Severity.LOW,
                f"Meta description is only {length} characters",
                element=description,
                recommendation=f"Expand toward {DESCRIPTION_MIN}–{DESCRIPTION_MAX} characters to "
                "use the full snippet width.",
            )
        )
    elif length > DESCRIPTION_MAX:
        findings.append(
            _finding(
                "seo.meta-description-too-long",
                Severity.LOW,
                f"Meta description is {length} characters and will be truncated",
                element=description,
                recommendation=f"Trim to {DESCRIPTION_MAX} characters or fewer.",
            )
        )


def _check_robots(doc: Document, findings: List[Finding]) -> None:
    robots = (doc.meta("robots") or "").lower()

    if "noindex" in robots:
        findings.append(
            _finding(
                "seo.noindex",
                Severity.CRITICAL,
                "Page is marked noindex and cannot rank",
                detail=f'<meta name="robots" content="{robots}">',
                element=robots,
                recommendation="Remove noindex if this page is meant to be indexable. This is "
                "frequently a staging directive left in place after go-live.",
            )
        )

    if "nofollow" in robots:
        findings.append(
            _finding(
                "seo.nofollow-page",
                Severity.MEDIUM,
                "Page-level nofollow stops link equity flowing onward",
                element=robots,
                recommendation="Remove the page-level nofollow unless this is deliberate.",
            )
        )


def _check_canonical(doc: Document, findings: List[Finding]) -> None:
    if not doc.canonical:
        findings.append(
            _finding(
                "seo.missing-canonical",
                Severity.MEDIUM,
                "No canonical URL declared",
                detail="Without a canonical, query strings and alternate paths can be indexed as "
                "separate duplicate pages.",
                recommendation='Add <link rel="canonical" href="..."> pointing at the preferred '
                "absolute URL for this page.",
            )
        )


def _check_headings(doc: Document, findings: List[Finding]) -> None:
    h1s = doc.headings_at(1)

    if not h1s:
        findings.append(
            _finding(
                "seo.missing-h1",
                Severity.HIGH,
                "Page has no H1",
                detail="The H1 states the page topic for both users and crawlers.",
                recommendation="Add exactly one H1 describing the page's subject.",
            )
        )
    elif len(h1s) > 1:
        findings.append(
            _finding(
                "seo.multiple-h1",
                Severity.MEDIUM,
                f"Page has {len(h1s)} H1 elements",
                detail="Found: " + "; ".join(repr(h.text) for h in h1s[:5]),
                line=h1s[1].line,
                recommendation="Keep one H1 and demote the rest to H2 so the outline has a single "
                "top-level topic.",
            )
        )

    # Flag jumps like H2 -> H4, which break the document outline for screen readers.
    previous = 0
    for heading in doc.headings:
        if previous and heading.level > previous + 1:
            findings.append(
                _finding(
                    "seo.heading-level-skip",
                    Severity.LOW,
                    f"Heading jumps from H{previous} to H{heading.level}",
                    detail=f"Heading text: {heading.text!r}",
                    element=heading.text,
                    line=heading.line,
                    recommendation=f"Use H{previous + 1} here, or restructure the section so "
                    "heading levels descend one at a time.",
                )
            )
        previous = heading.level

    empty = [h for h in doc.headings if not h.text.strip()]
    if empty:
        findings.append(
            _finding(
                "seo.empty-heading",
                Severity.LOW,
                f"{len(empty)} heading element(s) contain no text",
                line=empty[0].line,
                recommendation="Remove the empty heading or give it text. Headings are often left "
                "empty when used purely for spacing.",
            )
        )


def _check_lang_and_viewport(doc: Document, findings: List[Finding]) -> None:
    if not doc.lang:
        findings.append(
            _finding(
                "seo.missing-lang",
                Severity.MEDIUM,
                "<html> has no lang attribute",
                detail="Screen readers use it to pick a pronunciation model, and search engines "
                "use it for language targeting.",
                recommendation='Add a language code, e.g. <html lang="en">.',
            )
        )

    if not doc.meta("viewport"):
        findings.append(
            _finding(
                "seo.missing-viewport",
                Severity.HIGH,
                "No viewport meta tag",
                detail="Mobile browsers fall back to a desktop-width viewport and zoom out, so the "
                "page fails mobile usability checks.",
                recommendation='Add <meta name="viewport" content="width=device-width, '
                'initial-scale=1">.',
            )
        )


def _check_social(doc: Document, findings: List[Finding]) -> None:
    missing_og = [tag for tag in REQUIRED_OG_TAGS if not doc.meta_property(tag)]
    if missing_og:
        findings.append(
            _finding(
                "seo.missing-open-graph",
                Severity.LOW,
                f"Missing Open Graph tag(s): {', '.join(missing_og)}",
                detail="Open Graph controls the preview card when the page is shared on social "
                "platforms and in messaging apps.",
                recommendation="Add the missing og: properties. og:image should be at least "
                "1200×630 for a large preview card.",
            )
        )

    if not (doc.meta("twitter:card") or doc.meta_property("twitter:card")):
        findings.append(
            _finding(
                "seo.missing-twitter-card",
                Severity.INFO,
                "No Twitter/X card metadata",
                recommendation='Add <meta name="twitter:card" content="summary_large_image"> to '
                "control the shared preview.",
            )
        )


def _check_structured_data(doc: Document, findings: List[Finding]) -> None:
    if not doc.jsonld_blocks:
        findings.append(
            _finding(
                "seo.no-structured-data",
                Severity.LOW,
                "No JSON-LD structured data found",
                detail="Structured data is what makes rich results (breadcrumbs, FAQs, ratings) "
                "eligible to appear.",
                recommendation="Add schema.org JSON-LD appropriate to the page type — "
                "Organization and BreadcrumbList are the usual baseline.",
            )
        )


def _check_content(doc: Document, findings: List[Finding]) -> None:
    if doc.text_length < THIN_CONTENT_CHARS:
        findings.append(
            _finding(
                "seo.thin-content",
                Severity.MEDIUM,
                f"Only {doc.text_length} characters of visible text",
                detail="Pages this short rarely rank competitively, and the figure can also "
                "indicate copy that is rendered client-side and therefore invisible to crawlers.",
                recommendation=f"Aim for more than {THIN_CONTENT_CHARS} characters of substantive "
                "server-rendered copy.",
                meta={"text_length": doc.text_length},
            )
        )


def _check_link_text(doc: Document, findings: List[Finding]) -> None:
    offenders = [
        link
        for link in doc.links
        if link.text.strip().lower().rstrip(".!:") in NON_DESCRIPTIVE_LINK_TEXT
    ]
    if offenders:
        findings.append(
            _finding(
                "seo.non-descriptive-link-text",
                Severity.LOW,
                f"{len(offenders)} link(s) use non-descriptive anchor text",
                detail="Examples: "
                + "; ".join(f"{link.text!r} -> {link.href}" for link in offenders[:5]),
                line=offenders[0].line,
                recommendation="Describe the destination in the link text. Anchor text is a "
                "ranking signal and the primary way screen-reader users scan links.",
            )
        )
