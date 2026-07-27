"""Scan record — one row per submitted URL audit."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import ScanStatus


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(String(2048), index=True)
    status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, native_enum=False, length=32),
        default=ScanStatus.QUEUED,
        index=True,
    )

    # Which audit modules were requested for this scan.
    requested_modules: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Per-area scores (0–100) plus the rolled-up overall score. Populated as modules finish.
    overall_score: Mapped[float | None] = mapped_column(Float)
    scores: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Optional uploads (PRD Modules 7 and 10) — storage keys, not file bytes.
    design_upload_key: Mapped[str | None] = mapped_column(String(512))
    content_upload_key: Mapped[str | None] = mapped_column(String(512))

    celery_task_id: Mapped[str | None] = mapped_column(String(255), index=True)
    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pages: Mapped[list["Page"]] = relationship(  # noqa: F821
        back_populates="scan", cascade="all, delete-orphan"
    )
    findings: Mapped[list["Finding"]] = relationship(  # noqa: F821
        back_populates="scan", cascade="all, delete-orphan"
    )
