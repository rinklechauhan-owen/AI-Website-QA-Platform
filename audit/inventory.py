"""Page inventory: what is on the page, as opposed to what is wrong with it.

Rules in audit/rules/ produce findings. This module produces extracts — content listings,
a structure outline, an image alt-text inventory, and suggested schema.org markup — which
are reference material rather than pass/fail judgements.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from audit.parse import Document, ImageRef, Node, TextBlock

# Content tags listed by default. Overridable per call.
DEFAULT_CONTENT_TAGS = ("h1", "h2", "h3", "p")

DEFAULT_MAX_OUTLINE_NODES = 400
DEFAULT_MAX_OUTLINE_DEPTH = 8

# Splitters used to guess a site name out of a page title, e.g. "About | Acme Ltd".
_TITLE_SEPARATORS = re.compile(r"\s+[|–—·-]\s+")


# ---------------------------------------------------------------------------------------
# Content listing
# ---------------------------------------------------------------------------------------


@dataclass
class ContentInventory:
    blocks: List[TextBlock] = field(default_factory=list)
    tags: Sequence[str] = ()

    @property
    def counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {tag: 0 for tag in self.tags}
        for block in self.blocks:
            counts[block.tag] = counts.get(block.tag, 0) + 1
        return counts

    @property
    def total_words(self) -> int:
        return sum(block.word_count for block in self.blocks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tags": list(self.tags),
            "counts": self.counts,
            "total_words": self.total_words,
            "blocks": [
                {
                    "tag": block.tag,
                    "text": block.text,
                    "line": block.line,
                    "words": block.word_count,
                }
                for block in self.blocks
            ],
        }


def content_inventory(doc: Document, tags: Sequence[str] = DEFAULT_CONTENT_TAGS) -> ContentInventory:
    """Every heading and paragraph of the requested types, in document order."""
    return ContentInventory(blocks=doc.blocks_for(*tags), tags=tuple(tags))


# ---------------------------------------------------------------------------------------
# Structure outline
# ---------------------------------------------------------------------------------------


@dataclass
class OutlineRow:
    depth: int
    tag: str
    selector: str
    line: int
    child_count: int = 0


@dataclass
class StructureOutline:
    rows: List[OutlineRow] = field(default_factory=list)
    total_nodes: int = 0
    max_depth_seen: int = 0
    truncated_depth: int = 0
    truncated_count: int = 0

    @property
    def was_truncated(self) -> bool:
        return bool(self.truncated_depth or self.truncated_count)

    @property
    def tag_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row in self.rows:
            counts[row.tag] = counts.get(row.tag, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_nodes": self.total_nodes,
            "max_depth": self.max_depth_seen,
            "truncated_by_depth": self.truncated_depth,
            "truncated_by_count": self.truncated_count,
            "tag_counts": self.tag_counts,
            "rows": [
                {
                    "depth": row.depth,
                    "tag": row.tag,
                    "selector": row.selector,
                    "line": row.line,
                    "children": row.child_count,
                }
                for row in self.rows
            ],
        }


def structure_outline(
    doc: Document,
    max_nodes: int = DEFAULT_MAX_OUTLINE_NODES,
    max_depth: int = DEFAULT_MAX_OUTLINE_DEPTH,
) -> StructureOutline:
    """Flatten the parsed tree into displayable rows, capped so a deep page stays readable."""
    outline = StructureOutline()
    if doc.root is None:
        return outline

    outline.total_nodes = max(0, doc.root.count() - 1)  # exclude the synthetic root

    def visit(node: Node) -> None:
        for child in node.children:
            outline.max_depth_seen = max(outline.max_depth_seen, child.depth)

            if child.depth > max_depth:
                outline.truncated_depth += child.count()
                continue
            if len(outline.rows) >= max_nodes:
                outline.truncated_count += child.count()
                continue

            outline.rows.append(
                OutlineRow(
                    depth=child.depth,
                    tag=child.tag,
                    selector=child.selector,
                    line=child.line,
                    child_count=len(child.children),
                )
            )
            visit(child)

    visit(doc.root)
    return outline


# ---------------------------------------------------------------------------------------
# Image alt inventory
# ---------------------------------------------------------------------------------------


@dataclass
class ImageAltInventory:
    missing: List[ImageRef] = field(default_factory=list)
    empty: List[ImageRef] = field(default_factory=list)
    present: List[ImageRef] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.missing) + len(self.empty) + len(self.present)

    @property
    def needs_attention(self) -> List[ImageRef]:
        """Images a human has to look at: no alt attribute, or an explicitly empty one."""
        return self.missing + self.empty

    @property
    def coverage(self) -> float:
        """Share of images carrying meaningful alt text, 0-100."""
        if not self.total:
            return 100.0
        return round(len(self.present) / self.total * 100, 1)

    def to_dict(self) -> Dict[str, Any]:
        def describe(image: ImageRef) -> Dict[str, Any]:
            return {
                "src": image.src,
                "alt": image.alt,
                "alt_state": image.alt_state,
                "line": image.line,
                "index": image.index,
                "width": image.width,
                "height": image.height,
                "loading": image.loading,
            }

        return {
            "total": self.total,
            "coverage": self.coverage,
            "missing_alt": [describe(i) for i in self.missing],
            "empty_alt": [describe(i) for i in self.empty],
            "has_alt": [describe(i) for i in self.present],
        }


def image_alt_inventory(doc: Document) -> ImageAltInventory:
    """Split every <img> by the state of its alt attribute."""
    inventory = ImageAltInventory()
    for image in doc.images:
        state = image.alt_state
        if state == "missing":
            inventory.missing.append(image)
        elif state == "empty":
            inventory.empty.append(image)
        else:
            inventory.present.append(image)
    return inventory


# ---------------------------------------------------------------------------------------
# schema.org JSON-LD suggestion
# ---------------------------------------------------------------------------------------


@dataclass
class SchemaSuggestion:
    existing_types: List[str] = field(default_factory=list)
    generated: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def suggested_types(self) -> List[str]:
        return [str(item.get("@type", "?")) for item in self.generated.get("@graph", [])]

    @property
    def json_ld(self) -> str:
        if not self.generated:
            return ""
        return json.dumps(self.generated, indent=2, ensure_ascii=False)

    @property
    def script_block(self) -> str:
        """Ready to paste into <head>."""
        if not self.json_ld:
            return ""
        return f'<script type="application/ld+json">\n{self.json_ld}\n</script>'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "existing_types": self.existing_types,
            "suggested_types": self.suggested_types,
            "notes": self.notes,
            "json_ld": self.generated,
        }


def _existing_types(doc: Document) -> List[str]:
    """@type values already declared on the page."""
    found: List[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            declared = value.get("@type")
            if isinstance(declared, str):
                found.append(declared)
            elif isinstance(declared, list):
                found.extend(str(item) for item in declared)
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    for block in doc.jsonld_blocks:
        try:
            collect(json.loads(block))
        except (ValueError, TypeError):
            # Malformed JSON-LD is itself worth knowing about.
            found.append("(unparseable)")

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(found))


def _site_name(doc: Document) -> str:
    site = doc.meta_property("og:site_name")
    if site:
        return site

    if doc.title:
        parts = [part.strip() for part in _TITLE_SEPARATORS.split(doc.title) if part.strip()]
        if len(parts) > 1:
            # "About Us | Acme Ltd" -> the brand is conventionally last.
            return parts[-1]

    host = urlparse(doc.url).netloc
    return host[4:] if host.startswith("www.") else host


def _find_logo(doc: Document) -> Optional[str]:
    for image in doc.images:
        haystack = f"{image.src} {image.alt or ''}".lower()
        if "logo" in haystack:
            return image.src
    return None


def _breadcrumbs(doc: Document) -> Optional[Dict[str, Any]]:
    parsed = urlparse(doc.canonical or doc.url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return None

    origin = f"{parsed.scheme}://{parsed.netloc}"
    items = [
        {
            "@type": "ListItem",
            "position": 1,
            "name": "Home",
            "item": origin + "/",
        }
    ]

    path = ""
    for position, segment in enumerate(segments, start=2):
        path += "/" + segment
        label = re.sub(r"[-_]+", " ", re.sub(r"\.\w+$", "", segment)).strip().title()
        items.append(
            {
                "@type": "ListItem",
                "position": position,
                "name": label,
                "item": origin + path,
            }
        )

    return {"@type": "BreadcrumbList", "itemListElement": items}


def _faq(doc: Document) -> Optional[Dict[str, Any]]:
    """Pair question-shaped headings with the paragraph that follows them."""
    pairs = []
    blocks = doc.blocks
    for index, block in enumerate(blocks):
        if block.level is None or not block.text.rstrip().endswith("?"):
            continue
        answer = next(
            (later.text for later in blocks[index + 1 :] if later.tag == "p" and later.text),
            None,
        )
        if answer:
            pairs.append(
                {
                    "@type": "Question",
                    "name": block.text,
                    "acceptedAnswer": {"@type": "Answer", "text": answer},
                }
            )

    if len(pairs) < 2:
        return None
    return {"@type": "FAQPage", "mainEntity": pairs}


def suggest_schema(doc: Document) -> SchemaSuggestion:
    """Generate schema.org JSON-LD from what is demonstrably on the page.

    Only fields backed by real page content are emitted — no placeholders, because markup
    that describes a page inaccurately is worse than none at all.
    """
    suggestion = SchemaSuggestion(existing_types=_existing_types(doc))

    page_url = doc.canonical or doc.url
    origin = doc.origin
    site_name = _site_name(doc)
    description = doc.meta("description") or doc.meta_property("og:description")
    h1s = doc.headings_at(1)
    graph: List[Dict[str, Any]] = []

    organization: Dict[str, Any] = {
        "@type": "Organization",
        "@id": f"{origin}/#organization",
        "name": site_name,
        "url": origin + "/",
    }
    logo = _find_logo(doc)
    if logo:
        organization["logo"] = {"@type": "ImageObject", "url": logo}
    else:
        suggestion.notes.append(
            "No logo image detected — add an Organization.logo URL before publishing."
        )
    graph.append(organization)

    web_page: Dict[str, Any] = {
        "@type": "WebPage",
        "@id": f"{page_url}#webpage",
        "url": page_url,
        "name": doc.title or site_name,
        "isPartOf": {"@id": f"{origin}/#organization"},
    }
    if description:
        web_page["description"] = description
    else:
        suggestion.notes.append(
            "Page has no meta description, so WebPage.description was left out."
        )
    if doc.lang:
        web_page["inLanguage"] = doc.lang
    og_image = doc.meta_property("og:image")
    if og_image:
        web_page["primaryImageOfPage"] = {"@type": "ImageObject", "url": og_image}
    graph.append(web_page)

    breadcrumbs = _breadcrumbs(doc)
    if breadcrumbs:
        breadcrumbs["@id"] = f"{page_url}#breadcrumb"
        graph.append(breadcrumbs)
        suggestion.notes.append(
            "Breadcrumb names were derived from the URL path — rename them to match your "
            "on-page breadcrumb labels."
        )

    # Only claim Article when the page really looks like one.
    has_article_element = bool(doc.root and any(n.tag == "article" for n in doc.root.walk()))
    if h1s and (has_article_element or doc.text_length > 1500):
        article: Dict[str, Any] = {
            "@type": "Article",
            "headline": h1s[0].text,
            "mainEntityOfPage": {"@id": f"{page_url}#webpage"},
            "publisher": {"@id": f"{origin}/#organization"},
        }
        if description:
            article["description"] = description
        if og_image:
            article["image"] = og_image
        graph.append(article)
        suggestion.notes.append(
            "Article was suggested from page structure — add datePublished and author, which "
            "cannot be read reliably from the markup."
        )

    faq = _faq(doc)
    if faq:
        graph.append(faq)

    suggestion.generated = {"@context": "https://schema.org", "@graph": graph}

    overlap = sorted(set(suggestion.existing_types) & set(suggestion.suggested_types))
    if overlap:
        suggestion.notes.append(
            "Page already declares " + ", ".join(overlap) + " — merge rather than duplicate."
        )

    return suggestion


# ---------------------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------------------


@dataclass
class PageInventory:
    content: ContentInventory
    outline: StructureOutline
    images: ImageAltInventory
    schema: SchemaSuggestion

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content.to_dict(),
            "outline": self.outline.to_dict(),
            "images": self.images.to_dict(),
            "schema": self.schema.to_dict(),
        }


def build(
    doc: Document,
    content_tags: Sequence[str] = DEFAULT_CONTENT_TAGS,
    max_outline_nodes: int = DEFAULT_MAX_OUTLINE_NODES,
    max_outline_depth: int = DEFAULT_MAX_OUTLINE_DEPTH,
) -> PageInventory:
    return PageInventory(
        content=content_inventory(doc, content_tags),
        outline=structure_outline(doc, max_outline_nodes, max_outline_depth),
        images=image_alt_inventory(doc),
        schema=suggest_schema(doc),
    )
