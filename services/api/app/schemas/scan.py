"""Request and response schemas for the scan endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.enums import ModuleKey, ScanStatus

DEFAULT_MODULES: list[ModuleKey] = [
    ModuleKey.CRAWL,
    ModuleKey.SEO,
    ModuleKey.ACCESSIBILITY,
    ModuleKey.IMAGES,
    ModuleKey.PERFORMANCE,
]


class ScanCreate(BaseModel):
    url: HttpUrl
    modules: list[ModuleKey] = Field(default_factory=lambda: list(DEFAULT_MODULES))
    max_pages: int | None = Field(default=None, ge=1, le=500)
    max_depth: int | None = Field(default=None, ge=0, le=10)

    # Storage keys returned by the upload endpoints (PRD Modules 7 and 10).
    design_upload_key: str | None = None
    content_upload_key: str | None = None


class ScanOut(BaseModel):
    """Status payload the web app polls while a scan is running."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    status: ScanStatus
    requested_modules: list[str]
    overall_score: float | None
    scores: dict[str, float]
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ScanSummary(BaseModel):
    """Counts rendered by the dashboard (PRD Module 16)."""

    total_findings: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    pages_crawled: int = 0


class ScanDetail(ScanOut):
    summary: ScanSummary
