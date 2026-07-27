"""Module 7 — Content review.

Compares live page copy against an uploaded source document (PDF, DOCX, Markdown, TXT) and
reports missing paragraphs, changed wording, wrong CTAs, grammar, reading level, and tone.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.enums import ModuleKey
from app.modules.base import AuditModule

SUPPORTED_UPLOAD_TYPES = frozenset({".pdf", ".docx", ".md", ".txt"})


class ContentModule(AuditModule):
    key = ModuleKey.CONTENT

    def run(self, db: Session, context: dict[str, Any]) -> dict[str, Any]:
        # Nothing to compare against when no document was attached.
        if not context.get("content_upload_key"):
            return {"skipped": "no content document uploaded"}

        # TODO: parse the upload, embed both sides, align sections, and return
        # {"score": <match percentage>, "missing": [...], "changed": [...]}.
        raise NotImplementedError("Module 7 (content) is not implemented yet")
