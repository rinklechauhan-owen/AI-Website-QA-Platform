"""Report export endpoints (PRD Module 14)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.enums import ScanStatus
from app.models import Scan
from app.schemas import ReportOut, ReportRequest

router = APIRouter()


@router.post("/{scan_id}/report", response_model=ReportOut)
def create_report(
    scan_id: uuid.UUID,
    payload: ReportRequest,
    db: Session = Depends(get_db),
) -> ReportOut:
    """Render a completed scan into the requested export format."""
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Scan not found")

    if scan.status is not ScanStatus.COMPLETED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Scan is '{scan.status}'; reports require a completed scan",
        )

    # TODO(Module 14): render via app.modules.reporting and upload to configured storage.
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Report export to '{payload.format}' is not implemented yet",
    )
