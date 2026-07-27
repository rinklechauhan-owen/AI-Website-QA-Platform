"""Document model built with html.parser.

HTMLParser is a tolerant tag-stream parser rather than a spec-compliant tree builder, which
suits us: every rule here works off flat collections of elements, and a lenient parser is an
advantage when auditing markup that may well be broken.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

# Tags whose text content should never be treated as page copy.
_IGNORED_TEXT_TAGS = frozenset({"script", "style", "noscript", "template"})
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


@dataclass
class ImageRef:
    src: str
    # None means the attribute was absent; "" means alt="" was explicitly set.
    alt: Optional[str] = None
    width: Optional[str] = None
    height: Optional[str] = None
    loading: Optional[str] = None
    srcset: Optional[str] = None
    line: int = 0
    # Position in document order, used as a rough above/below-the-fold heuristic.
    index: int = 0


@dataclass
class LinkRef:
    href: str
    text: str = ""
    rel: str = ""
    target: str = ""
    line: int = 0


@dataclass
class Heading:
    level: int
    text: str
    line: int = 0


@dataclass
class Document:
    url: str
    html: str = ""
    title: Optional[str] = None
    lang: Optional[str] = None
    metas: List[Dict[str, str]] = field(default_factory=list)
    canonical: Optional[str] = None
    headings: List[Heading] = field(default_factory=list)
    images: List[ImageRef] = field(default_factory=list)
    links: List[LinkRef] = field(default_factory=list)
    jsonld_blocks: List[str] = field(default_factory=list)
    text_length: int = 0
    picture_sources: List[str] = field(default_factory=list)

    # -- meta helpers ----------------------------------------------------------------

    def meta(self, name: str) -> Optional[str]:
        """Content of <meta name="..."> (case-insensitive)."""
        target = name.lower()
        for tag in self.metas:
            if tag.get("name", "").lower() == target:
                return tag.get("content")
        return None

    def meta_property(self, prop: str) -> Optional[str]:
        """Content of <meta property="..."> — Open Graph and friends."""
        target = prop.lower()
        for tag in self.metas:
            if tag.get("property", "").lower() == target:
                return tag.get("content")
        return None

    def headings_at(self, level: int) -> List[Heading]:
        return [h for h in self.headings if h.level == level]

    @property
    def origin(self) -> str:
        parsed = urlparse(self.url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def internal_links(self) -> List[LinkRef]:
        host = urlparse(self.url).netloc
        return [link for link in self.links if urlparse(link.href).netloc == host]

    def external_links(self) -> List[LinkRef]:
        host = urlparse(self.url).netloc
        return [
            link
            for link in self.links
            if urlparse(link.href).netloc and urlparse(link.href).netloc != host
        ]


class _DocumentParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        # convert_charrefs=True gives us unescaped text in handle_data.
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.doc = Document(url=base_url)

        self._image_count = 0
        self._text_chars = 0
        # Stack of tags we are currently capturing text into.
        self._capture_stack: List[Tuple[str, List[str]]] = []
        self._suppress_depth = 0
        self._current_heading: Optional[Heading] = None
        self._current_link: Optional[LinkRef] = None
        self._in_jsonld = False
        self._jsonld_buffer: List[str] = []

    # -- helpers ---------------------------------------------------------------------

    @staticmethod
    def _attrs_to_dict(attrs) -> Dict[str, Optional[str]]:
        return {name.lower(): value for name, value in attrs}

    def _absolute(self, href: str) -> str:
        try:
            return urljoin(self.base_url, href)
        except ValueError:
            return href

    # -- HTMLParser hooks ------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attr = self._attrs_to_dict(attrs)
        line = self.getpos()[0]

        if tag in _IGNORED_TEXT_TAGS:
            self._suppress_depth += 1
            if tag == "script" and (attr.get("type") or "").lower() == "application/ld+json":
                self._in_jsonld = True
                self._jsonld_buffer = []
            return

        if tag == "html":
            self.doc.lang = attr.get("lang")

        elif tag == "title":
            self._capture_stack.append(("title", []))

        elif tag == "meta":
            self.doc.metas.append({k: (v or "") for k, v in attr.items()})

        elif tag == "link":
            rels = (attr.get("rel") or "").lower().split()
            if "canonical" in rels and attr.get("href"):
                self.doc.canonical = self._absolute(attr["href"])

        elif tag == "img":
            self._image_count += 1
            self.doc.images.append(
                ImageRef(
                    src=self._absolute(attr.get("src") or attr.get("data-src") or ""),
                    alt=attr.get("alt"),
                    width=attr.get("width"),
                    height=attr.get("height"),
                    loading=attr.get("loading"),
                    srcset=attr.get("srcset"),
                    line=line,
                    index=self._image_count,
                )
            )

        elif tag == "source":
            srcset = attr.get("srcset") or attr.get("src")
            if srcset:
                self.doc.picture_sources.append(srcset)

        elif tag in _HEADING_TAGS:
            self._current_heading = Heading(level=int(tag[1]), text="", line=line)
            self._capture_stack.append((tag, []))

        elif tag == "a":
            href = attr.get("href")
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                self._current_link = LinkRef(
                    href=self._absolute(href),
                    rel=(attr.get("rel") or ""),
                    target=(attr.get("target") or ""),
                    line=line,
                )
                self._capture_stack.append(("a", []))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in _IGNORED_TEXT_TAGS:
            self._suppress_depth = max(0, self._suppress_depth - 1)
            if tag == "script" and self._in_jsonld:
                self.doc.jsonld_blocks.append("".join(self._jsonld_buffer).strip())
                self._in_jsonld = False
            return

        if not self._capture_stack or self._capture_stack[-1][0] != tag:
            # Unbalanced markup — nothing to close.
            return

        _, chunks = self._capture_stack.pop()
        text = " ".join("".join(chunks).split())

        if tag == "title":
            self.doc.title = text
        elif tag in _HEADING_TAGS and self._current_heading is not None:
            self._current_heading.text = text
            self.doc.headings.append(self._current_heading)
            self._current_heading = None
        elif tag == "a" and self._current_link is not None:
            self._current_link.text = text
            self.doc.links.append(self._current_link)
            self._current_link = None

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._jsonld_buffer.append(data)
            return

        if self._suppress_depth:
            return

        self._text_chars += len(data.strip())
        # Append to every open frame, not just the innermost: <h2><a>Title</a></h2> must
        # give the h2 its text as well as the anchor.
        for _, chunks in self._capture_stack:
            chunks.append(data)


def parse(html: str, url: str) -> Document:
    """Parse an HTML string into a Document."""
    parser = _DocumentParser(url)
    # A malformed document should degrade to partial results, never crash the audit.
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 - html.parser can raise on pathological input
        pass

    doc = parser.doc
    doc.html = html
    doc.text_length = parser._text_chars
    return doc
