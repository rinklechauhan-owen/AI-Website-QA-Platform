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

# Elements that never have a closing tag.
_VOID_TAGS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }
)

# Elements worth showing in a structure outline. Inline formatting is excluded — it describes
# text, not layout, and including it would bury the shape of the page.
_STRUCTURAL_TAGS = frozenset(
    {
        "html", "body", "header", "nav", "main", "section", "article", "aside", "footer",
        "div", "form", "fieldset", "table", "thead", "tbody", "tr", "td", "th",
        "ul", "ol", "li", "dl", "dt", "dd", "figure", "figcaption", "picture",
        "video", "audio", "iframe", "canvas", "svg", "img", "p", "blockquote", "pre",
        "h1", "h2", "h3", "h4", "h5", "h6", "button", "label", "select", "textarea", "input",
    }
)

# Starting one of these implicitly closes an open <p>, which HTML permits and authors rely on.
_CLOSES_PARAGRAPH = frozenset(
    {
        "p", "div", "section", "article", "aside", "header", "footer", "main", "nav",
        "ul", "ol", "li", "table", "form", "blockquote", "pre", "figure", "hr",
        "h1", "h2", "h3", "h4", "h5", "h6",
    }
)


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

    @property
    def alt_state(self) -> str:
        """One of: missing, empty, present."""
        if self.alt is None:
            return "missing"
        if self.alt.strip() == "":
            return "empty"
        return "present"


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
class TextBlock:
    """A heading or paragraph, kept in document order."""

    tag: str
    text: str
    line: int = 0

    @property
    def level(self) -> Optional[int]:
        return int(self.tag[1]) if self.tag in _HEADING_TAGS else None

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class Node:
    """A node in the structure outline."""

    tag: str
    depth: int = 0
    element_id: Optional[str] = None
    classes: List[str] = field(default_factory=list)
    children: List["Node"] = field(default_factory=list)
    line: int = 0

    @property
    def selector(self) -> str:
        """CSS-ish label, e.g. div#hero.wrapper.dark"""
        label = self.tag
        if self.element_id:
            label += f"#{self.element_id}"
        for cls in self.classes[:3]:
            label += f".{cls}"
        return label

    def walk(self):
        """Depth-first traversal including self."""
        yield self
        for child in self.children:
            yield from child.walk()

    def count(self) -> int:
        return sum(1 for _ in self.walk())


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
    # <link rel="alternate" hreflang="..."> entries: {"hreflang": ..., "href": ...}
    hreflang: List[Dict[str, str]] = field(default_factory=list)
    # Headings and paragraphs in document order.
    blocks: List[TextBlock] = field(default_factory=list)
    root: Optional[Node] = None

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

    def blocks_for(self, *tags: str) -> List[TextBlock]:
        """Content blocks limited to the given tags, in document order."""
        wanted = {tag.lower() for tag in tags}
        return [block for block in self.blocks if block.tag in wanted]

    @property
    def paragraphs(self) -> List[TextBlock]:
        return self.blocks_for("p")

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
        self._current_block: Optional[TextBlock] = None
        self._current_link: Optional[LinkRef] = None
        self._in_jsonld = False
        self._jsonld_buffer: List[str] = []

        # Structure outline.
        self._root = Node(tag="document", depth=-1)
        self._node_stack: List[Node] = [self._root]

    # -- helpers ---------------------------------------------------------------------

    @staticmethod
    def _attrs_to_dict(attrs) -> Dict[str, Optional[str]]:
        return {name.lower(): value for name, value in attrs}

    def _absolute(self, href: str) -> str:
        try:
            return urljoin(self.base_url, href)
        except ValueError:
            return href

    def _finish_capture(self, tag: str) -> Optional[str]:
        """Pop the innermost capture frame if it matches, returning its collapsed text."""
        if not self._capture_stack or self._capture_stack[-1][0] != tag:
            return None
        _, chunks = self._capture_stack.pop()
        return " ".join("".join(chunks).split())

    def _close_paragraph(self) -> None:
        """HTML lets <p> be left unclosed; close it before the next block starts."""
        if self._current_block is not None and self._current_block.tag == "p":
            text = self._finish_capture("p")
            if text:
                self._current_block.text = text
                self.doc.blocks.append(self._current_block)
            self._current_block = None
            # Keep the outline in step, or the next block would nest inside this paragraph.
            self._pop_node("p")

    def _push_node(self, tag: str, attr: Dict[str, Optional[str]], line: int) -> None:
        parent = self._node_stack[-1]
        node = Node(
            tag=tag,
            depth=parent.depth + 1,
            element_id=attr.get("id"),
            classes=(attr.get("class") or "").split(),
            line=line,
        )
        parent.children.append(node)
        if tag not in _VOID_TAGS:
            self._node_stack.append(node)

    def _pop_node(self, tag: str) -> None:
        # Pop to the nearest matching ancestor; tolerate mismatched markup.
        for index in range(len(self._node_stack) - 1, 0, -1):
            if self._node_stack[index].tag == tag:
                del self._node_stack[index:]
                return

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

        if tag in _CLOSES_PARAGRAPH:
            self._close_paragraph()

        if tag in _STRUCTURAL_TAGS:
            self._push_node(tag, attr, line)

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
            if "alternate" in rels and attr.get("hreflang"):
                self.doc.hreflang.append(
                    {
                        "hreflang": attr["hreflang"],
                        "href": self._absolute(attr.get("href") or ""),
                    }
                )

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

        elif tag in _HEADING_TAGS or tag == "p":
            self._current_block = TextBlock(tag=tag, text="", line=line)
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

        if tag in _STRUCTURAL_TAGS:
            self._pop_node(tag)

        text = self._finish_capture(tag)
        if text is None:
            return

        if tag == "title":
            self.doc.title = text
        elif tag in _HEADING_TAGS or tag == "p":
            if self._current_block is not None:
                self._current_block.text = text
                if text:
                    self.doc.blocks.append(self._current_block)
                if tag in _HEADING_TAGS:
                    # Headings are also exposed as their own list, empty ones included,
                    # because "heading with no text" is itself a finding.
                    self.doc.headings.append(
                        Heading(level=int(tag[1]), text=text, line=self._current_block.line)
                    )
                self._current_block = None
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

    parser._close_paragraph()

    doc = parser.doc
    doc.html = html
    doc.text_length = parser._text_chars
    doc.root = parser._root
    return doc
