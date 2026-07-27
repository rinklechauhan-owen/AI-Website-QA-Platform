"""Finding record — a single issue produced by any audit module.

All modules emit findings in this shape so the dashboard, checklist, and exports can render
results uniformly regardless of which module found the issue.
"""

import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import ModuleKey, Priority, Severity


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), index=True
    )
    page_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), index=True
    )

    module: Mapped[ModuleKey] = mapped_column(
        Enum(ModuleKey, native_enum=False, length=32), index=True
    )
    # Stable machine-readable identifier, e.g. "image.missing-alt" or "seo.duplicate-h1".
    rule: Mapped[str] = mapped_column(String(128), index=True)

    severity: Mapped[Severity] = mapped_column(Enum(Severity, native_enum=False, length=16))
    priority: Mapped[Priority | None] = mapped_column(Enum(Priority, native_enum=False, length=8))

    title: Mapped[str] = mapped_column(String(512))
    detail: Mapped[str | None] = mapped_column(Text)

    # CSS selector / XPath and element context, when the finding points at markup.
    selector: Mapped[str | None] = mapped_column(String(1024))
    snippet: Mapped[str | None] = mapped_column(Text)

    # AI recommendation payload (PRD Module 13): why it matters, how to fix,
    # suggested replacement, impact, estimated effort.
    recommendation: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Module-specific extras, e.g. image byte savings or the viewport width that reproduced it.
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)

    scan: Mapped["Scan"] = relationship(back_populates="findings")  # noqa: F821
