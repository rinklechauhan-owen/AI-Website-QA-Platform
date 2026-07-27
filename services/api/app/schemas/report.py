"""Schemas for report export (PRD Module 14)."""

import uuid

from pydantic import BaseModel

from app.enums import ModuleKey, ReportFormat


class ReportRequest(BaseModel):
    format: ReportFormat = ReportFormat.PDF
    # Restrict the export to a subset of modules; empty means every module in the scan.
    modules: list[ModuleKey] = []
    include_screenshots: bool = True


class ReportOut(BaseModel):
    scan_id: uuid.UUID
    format: ReportFormat
    download_url: str
    size_bytes: int | None = None
