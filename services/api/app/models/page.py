"""Page record — one row per URL discovered by the crawler (PRD Module 1)."""

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), index=True
    )

    url: Mapped[str] = mapped_column(String(2048), index=True)
    status_code: Mapped[int | None] = mapped_column(Integer)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str | None] = mapped_column(String(1024))

    # Extracted document data: meta tags, headings, links, images, fonts, console errors.
    extracted: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Storage keys for full-page screenshots, keyed by viewport width (PRD Module 9).
    screenshot_keys: Mapped[dict] = mapped_column(JSONB, default=dict)

    scan: Mapped["Scan"] = relationship(back_populates="pages")  # noqa: F821
