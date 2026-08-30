"""Website crawling.

A scheduler around the existing audit engine, not a second engine. The crawler fetches pages
and hands each :class:`audit.fetch.Response` to :func:`audit.engine.audit_response` — the same
function the single-page audit uses — so one URL and two thousand receive identical analysis.

Nothing in this package modifies the single-page path.
"""

__all__ = ["frontier", "robots", "settings", "sitemap", "store", "urlnorm"]
