"""Standalone schema.org generator: content in, JSON-LD out.

Distinct from inventory.suggest_schema, which derives markup from a *fetched page*. This
takes content typed or pasted by a user — HTML or plain text — and builds JSON-LD from it.

The guiding rule is the same in both places: never invent a value. A field that cannot be
read from the input is omitted and reported as a note, because structured data that misstates
a page is worse for the site than having none at all.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_TYPES: List[Tuple[str, str]] = [
    ("auto", "Auto-detect from HTML"),
    ("Article", "Article / blog post"),
    ("FAQPage", "FAQ page"),
    ("HowTo", "How-to / step guide"),
    ("Organization", "Organization"),
    ("LocalBusiness", "Local business"),
    ("Product", "Product"),
    ("Event", "Event"),
    ("BreadcrumbList", "Breadcrumb trail"),
    ("WebPage", "Generic web page"),
]

VALID_TYPES = {key for key, _ in SCHEMA_TYPES}

# "Key: value" metadata lines, the most predictable way to hand us specific fields.
_FIELD_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _-]{0,40})\s*:\s*(.+?)\s*$")
# Ordered or bulleted steps: "1. Do this", "- Do this", "Step 2: Do this".
_STEP_LINE = re.compile(r"^\s*(?:step\s*)?(?:\d+[.)]|[-*•])\s*(.+?)\s*$", re.I)
_BREADCRUMB_SPLIT = re.compile(r"\s*(?:>|›|→|/|\|)\s*")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

_LOCAL_BUSINESS_ADDRESS_KEYS = {
    "street": "streetAddress",
    "streetaddress": "streetAddress",
    "address": "streetAddress",
    "city": "addressLocality",
    "locality": "addressLocality",
    "region": "addressRegion",
    "county": "addressRegion",
    "state": "addressRegion",
    "postcode": "postalCode",
    "postalcode": "postalCode",
    "zip": "postalCode",
    "country": "addressCountry",
}


@dataclass
class GeneratedSchema:
    """Result of one generation.

    ``notes`` are advisory — the markup is valid but could be richer. ``warnings`` are
    blocking: a required property was missing, so no markup is emitted at all.
    """

    schema_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.data)

    @property
    def json_ld(self) -> str:
        return json.dumps(self.data, indent=2, ensure_ascii=False) if self.data else ""

    @property
    def script_block(self) -> str:
        if not self.json_ld:
            return ""
        return f'<script type="application/ld+json">\n{self.json_ld}\n</script>'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_type": self.schema_type,
            "notes": self.notes,
            "warnings": self.warnings,
            "json_ld": self.data,
        }


# ---------------------------------------------------------------------------------------
# Input parsing helpers
# ---------------------------------------------------------------------------------------


def looks_like_html(text: str) -> bool:
    stripped = text.strip()
    return bool(re.search(r"<\s*[a-zA-Z!/]", stripped))


def _lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def split_fields(text: str) -> Tuple[Dict[str, str], List[str]]:
    """Separate "Key: value" lines from free prose.

    A line only counts as a field when its key is a single short phrase, so ordinary prose
    containing a colon is not mistaken for metadata.
    """
    fields: Dict[str, str] = {}
    prose: List[str] = []

    for line in _lines(text):
        match = _FIELD_LINE.match(line)
        if match and len(match.group(1).split()) <= 3 and not line.endswith(":"):
            fields[match.group(1).strip().lower().replace(" ", "")] = match.group(2).strip()
        else:
            prose.append(line)

    return fields, prose


def _first_sentence(text: str, limit: int = 300) -> str:
    parts = _SENTENCE_END.split(text.strip(), maxsplit=1)
    sentence = parts[0].strip() if parts else text.strip()
    return sentence[:limit]


def _pick(fields: Dict[str, str], *keys: str) -> Optional[str]:
    for key in keys:
        if fields.get(key):
            return fields[key]
    return None


def _html_to_blocks(html: str) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    """Reuse the audit parser so pasted markup is read the same way a live page would be."""
    from audit.parse import parse

    doc = parse(html, "https://example.invalid/")
    blocks = [(block.tag, block.text) for block in doc.blocks if block.text]
    return doc.title, blocks


# ---------------------------------------------------------------------------------------
# Per-type builders
# ---------------------------------------------------------------------------------------


def _build_article(fields, prose, blocks, result: GeneratedSchema) -> Dict[str, Any]:
    headline = _pick(fields, "headline", "title", "name")
    body_lines = list(prose)

    if not headline and blocks:
        heading = next((text for tag, text in blocks if tag.startswith("h")), None)
        headline = heading
        body_lines = [text for tag, text in blocks if not tag.startswith("h")] or body_lines
    if not headline and body_lines:
        headline = body_lines.pop(0)

    if not headline:
        result.warnings.append("No headline found. Give a title line or a heading.")
        return {}

    body = " ".join(body_lines).strip()
    data: Dict[str, Any] = {"@context": "https://schema.org", "@type": "Article", "headline": headline}

    description = _pick(fields, "description", "summary") or (_first_sentence(body) if body else None)
    if description:
        data["description"] = description
    if body:
        data["articleBody"] = body

    author = _pick(fields, "author", "by", "writer")
    if author:
        data["author"] = {"@type": "Person", "name": author}
    else:
        result.notes.append("No author given — add an `Author:` line, or set it before publishing.")

    published = _pick(fields, "datepublished", "published", "date")
    if published:
        data["datePublished"] = published
    else:
        result.notes.append("No publication date given — add a `Date:` line in YYYY-MM-DD form.")

    for key, target in (("image", "image"), ("url", "url"), ("publisher", "publisher")):
        value = _pick(fields, key)
        if value:
            data[target] = (
                {"@type": "Organization", "name": value} if target == "publisher" else value
            )

    return data


def _build_faq(fields, prose, blocks, result: GeneratedSchema) -> Dict[str, Any]:
    pairs: List[Dict[str, Any]] = []

    # From markup: a question-shaped heading followed by its paragraph.
    if blocks:
        for index, (tag, text) in enumerate(blocks):
            if tag.startswith("h") and text.rstrip().endswith("?"):
                answer = next(
                    (t for tg, t in blocks[index + 1 :] if tg == "p" and t), None
                )
                if answer:
                    pairs.append((text, answer))

    # From plain text: a line ending in "?" followed by the next non-question line.
    if not pairs:
        pending: Optional[str] = None
        for line in prose:
            if line.rstrip().endswith("?"):
                pending = line
            elif pending:
                pairs.append((pending, line))
                pending = None

    if not pairs:
        result.warnings.append(
            "No question and answer pairs found. Put each question on its own line ending "
            "in '?', with the answer on the line below."
        )
        return {}

    if len(pairs) == 1:
        result.notes.append(
            "Only one pair found. Google generally expects an FAQ page to hold several."
        )

    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
            for question, answer in pairs
        ],
    }


def _build_howto(fields, prose, blocks, result: GeneratedSchema) -> Dict[str, Any]:
    source = [text for _, text in blocks] if blocks else prose
    steps = [match.group(1) for line in source if (match := _STEP_LINE.match(line))]

    if not steps:
        result.warnings.append(
            "No steps found. Number them '1.', '2.' or start each with '-'."
        )
        return {}

    name = _pick(fields, "name", "title") or next(
        (line for line in source if not _STEP_LINE.match(line)), "How to"
    )

    data: Dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "HowTo",
        "name": name,
        "step": [
            {"@type": "HowToStep", "position": index, "text": text}
            for index, text in enumerate(steps, start=1)
        ],
    }
    total_time = _pick(fields, "totaltime", "time", "duration")
    if total_time:
        data["totalTime"] = total_time
    else:
        result.notes.append(
            "No duration given — add `Time: PT30M` (ISO 8601) to qualify for richer results."
        )
    return data


def _build_organization(fields, prose, blocks, result, kind="Organization") -> Dict[str, Any]:
    name = _pick(fields, "name", "organization", "business", "company") or (
        prose[0] if prose else None
    )
    if not name:
        result.warnings.append("No name found. Add a `Name:` line.")
        return {}

    data: Dict[str, Any] = {"@context": "https://schema.org", "@type": kind, "name": name}

    for key, target in (
        ("url", "url"),
        ("logo", "logo"),
        ("email", "email"),
        ("phone", "telephone"),
        ("telephone", "telephone"),
        ("pricerange", "priceRange"),
    ):
        value = _pick(fields, key)
        if value:
            data[target] = value

    address = {
        target: fields[key]
        for key, target in _LOCAL_BUSINESS_ADDRESS_KEYS.items()
        if fields.get(key)
    }
    if address:
        data["address"] = {"@type": "PostalAddress", **address}
    elif kind == "LocalBusiness":
        result.warnings.append(
            "A LocalBusiness needs an address. Add `Street:`, `City:`, `Postcode:` lines."
        )

    description = _pick(fields, "description") or (" ".join(prose[1:]).strip() or None)
    if description:
        data["description"] = description

    profiles = _pick(fields, "sameas", "social", "profiles")
    if profiles:
        data["sameAs"] = [item.strip() for item in profiles.split(",") if item.strip()]

    if kind == "LocalBusiness" and not _pick(fields, "openinghours", "hours"):
        result.notes.append("Add `Hours:` to describe opening times.")

    return data


def _build_product(fields, prose, blocks, result: GeneratedSchema) -> Dict[str, Any]:
    name = _pick(fields, "name", "product", "title") or (prose[0] if prose else None)
    if not name:
        result.warnings.append("No product name found. Add a `Name:` line.")
        return {}

    data: Dict[str, Any] = {"@context": "https://schema.org", "@type": "Product", "name": name}

    description = _pick(fields, "description") or (" ".join(prose[1:]).strip() or None)
    if description:
        data["description"] = description
    for key, target in (("sku", "sku"), ("mpn", "mpn"), ("image", "image")):
        if fields.get(key):
            data[target] = fields[key]
    brand = _pick(fields, "brand", "manufacturer")
    if brand:
        data["brand"] = {"@type": "Brand", "name": brand}

    price = _pick(fields, "price", "cost")
    if price:
        currency = _pick(fields, "currency", "pricecurrency") or "GBP"
        offer: Dict[str, Any] = {
            "@type": "Offer",
            "price": re.sub(r"[^\d.]", "", price) or price,
            "priceCurrency": currency,
        }
        availability = _pick(fields, "availability", "stock")
        if availability:
            offer["availability"] = f"https://schema.org/{availability.strip().replace(' ', '')}"
        if fields.get("url"):
            offer["url"] = fields["url"]
        data["offers"] = offer
        if not _pick(fields, "currency", "pricecurrency"):
            result.notes.append("No currency given, so GBP was assumed — add `Currency:` to fix.")
    else:
        result.notes.append("No price given. Add `Price:` and `Currency:` to be eligible for "
                            "product rich results.")

    return data


def _build_event(fields, prose, blocks, result: GeneratedSchema) -> Dict[str, Any]:
    name = _pick(fields, "name", "event", "title") or (prose[0] if prose else None)
    if not name:
        result.warnings.append("No event name found. Add a `Name:` line.")
        return {}

    data: Dict[str, Any] = {"@context": "https://schema.org", "@type": "Event", "name": name}

    start = _pick(fields, "startdate", "start", "date", "when")
    if start:
        data["startDate"] = start
    else:
        result.warnings.append("An Event needs a start date. Add `Start: 2026-09-01T19:00`.")

    end = _pick(fields, "enddate", "end")
    if end:
        data["endDate"] = end

    location = _pick(fields, "location", "venue", "where")
    if location:
        data["location"] = {"@type": "Place", "name": location}
    else:
        result.notes.append("No location given — add `Location:` or mark the event as online.")

    description = _pick(fields, "description") or (" ".join(prose[1:]).strip() or None)
    if description:
        data["description"] = description
    for key, target in (("url", "url"), ("image", "image")):
        if fields.get(key):
            data[target] = fields[key]
    organiser = _pick(fields, "organizer", "organiser", "host")
    if organiser:
        data["organizer"] = {"@type": "Organization", "name": organiser}

    return data


def _build_breadcrumbs(fields, prose, blocks, result: GeneratedSchema) -> Dict[str, Any]:
    source = _pick(fields, "breadcrumb", "trail", "path") or (prose[0] if prose else "")
    crumbs = [part.strip() for part in _BREADCRUMB_SPLIT.split(source) if part.strip()]

    if len(crumbs) < 2:
        result.warnings.append(
            "Give a trail with at least two levels, e.g. Home > Services > Branding."
        )
        return {}

    base = (_pick(fields, "url", "baseurl") or "").rstrip("/")
    items = []
    for position, label in enumerate(crumbs, start=1):
        entry: Dict[str, Any] = {"@type": "ListItem", "position": position, "name": label}
        if base:
            slug = "" if position == 1 else "/" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
            entry["item"] = base + (slug or "/")
        items.append(entry)

    if not base:
        result.notes.append("No `URL:` given, so no item links were generated — add one for "
                            "fully valid breadcrumbs.")

    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}


def _build_webpage(fields, prose, blocks, result: GeneratedSchema) -> Dict[str, Any]:
    name = _pick(fields, "name", "title") or (prose[0] if prose else None)
    if not name:
        result.warnings.append("No page title found. Add a `Title:` line.")
        return {}

    data: Dict[str, Any] = {"@context": "https://schema.org", "@type": "WebPage", "name": name}
    description = _pick(fields, "description") or (
        _first_sentence(" ".join(prose[1:])) if len(prose) > 1 else None
    )
    if description:
        data["description"] = description
    for key, target in (("url", "url"), ("language", "inLanguage"), ("lang", "inLanguage")):
        if fields.get(key):
            data[target] = fields[key]
    return data


_BUILDERS = {
    "Article": _build_article,
    "FAQPage": _build_faq,
    "HowTo": _build_howto,
    "Organization": _build_organization,
    "LocalBusiness": lambda f, p, b, r: _build_organization(f, p, b, r, kind="LocalBusiness"),
    "Product": _build_product,
    "Event": _build_event,
    "BreadcrumbList": _build_breadcrumbs,
    "WebPage": _build_webpage,
}


def generate(content: str, schema_type: str = "auto") -> GeneratedSchema:
    """Build JSON-LD from pasted content.

    ``auto`` parses HTML input with the audit engine's own page-level generator; for plain
    text it picks the type the content most resembles.
    """
    result = GeneratedSchema(schema_type=schema_type)

    if not content or not content.strip():
        result.warnings.append("Nothing to work with — paste some content first.")
        return result

    if schema_type not in VALID_TYPES:
        result.warnings.append(f"Unknown schema type {schema_type!r}.")
        return result

    is_html = looks_like_html(content)
    title, blocks = _html_to_blocks(content) if is_html else (None, [])

    if is_html:
        # Builders read prose as well as blocks, so give them the extracted text rather than
        # the raw markup — otherwise every HTML input comes back empty.
        prose = [text for _, text in blocks]
        fields = {}
        if title:
            fields["title"] = title
    else:
        fields, prose = split_fields(content)

    if schema_type == "auto":
        detected = _detect(is_html, fields, prose, blocks)
        result.schema_type = detected
        result.notes.insert(0, f"Detected {detected} from the content.")
        schema_type = detected

    builder = _BUILDERS[schema_type]
    result.data = builder(fields, prose, blocks, result)

    # Warnings mean a *required* property could not be derived; notes are advisory. Emitting
    # markup that is missing something required would hand the user invalid structured data
    # with a caveat attached, which is precisely the failure mode this tool exists to avoid.
    if result.warnings:
        result.data = {}

    return result


def _detect(is_html: bool, fields, prose, blocks) -> str:
    """Best guess at the most fitting type. Deliberately conservative."""
    source = [text for _, text in blocks] if blocks else prose

    questions = sum(1 for line in source if line.rstrip().endswith("?"))
    if questions >= 2:
        return "FAQPage"

    if sum(1 for line in source if _STEP_LINE.match(line)) >= 2:
        return "HowTo"

    if fields.get("price") or fields.get("sku"):
        return "Product"
    if fields.get("startdate") or fields.get("start"):
        return "Event"
    if any(fields.get(key) for key in _LOCAL_BUSINESS_ADDRESS_KEYS):
        return "LocalBusiness"
    if fields.get("author") or fields.get("datepublished") or fields.get("published"):
        return "Article"

    body_words = sum(len(line.split()) for line in source)
    if body_words > 120:
        return "Article"

    return "WebPage"
