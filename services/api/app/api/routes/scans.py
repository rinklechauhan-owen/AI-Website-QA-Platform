"""Scan lifecycle endpoints: submit, poll, list findings, cancel."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.enums import ModuleKey, ScanStatus, Severity
from app.models import Finding, Page, Scan
from app.schemas import FindingOut, ScanCreate, ScanDetail, ScanOut, ScanSummary
from app.tasks.scan_tasks import run_scan

router = APIRouter()

TERMINAL_STATUSES = {ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED}


def _get_scan_or_404(scan_id: uuid.UUID, db: Session) -> Scan:
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return scan


@router.post("", response_model=ScanOut, status_code=status.HTTP_202_ACCEPTED)
def create_scan(payload: ScanCreate, db: Session = Depends(get_db)) -> Scan:
    """Queue a scan. Returns immediately; poll GET /scans/{id} for progress."""
    scan = Scan(
        url=str(payload.url),
        status=ScanStatus.QUEUED,
        requested_modules=[m.value for m in payload.modules],
        design_upload_key=payload.design_upload_key,
        content_upload_key=payload.content_upload_key,
        scores={},
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    task = run_scan.delay(
        str(scan.id),
        max_pages=payload.max_pages,
        max_depth=payload.max_depth,
    )
    scan.celery_task_id = task.id
    db.commit()
    db.refresh(scan)

    return scan


@router.get("", response_model=list[ScanOut])
def list_scans(
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Scan]:
    """Recent scans, newest first (PRD §21 — scan history)."""
    stmt = select(Scan).order_by(Scan.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.get("/{scan_id}", response_model=ScanDetail)
def get_scan(scan_id: uuid.UUID, db: Session = Depends(get_db)) -> ScanDetail:
    scan = _get_scan_or_404(scan_id, db)

    counts = dict(
        db.execute(
            select(Finding.severity, func.count())
            .where(Finding.scan_id == scan_id)
            .group_by(Finding.severity)
        ).all()
    )
    pages_crawled = db.scalar(
        select(func.count()).select_from(Page).where(Page.scan_id == scan_id)
    )

    summary = ScanSummary(
        total_findings=sum(counts.values()),
        critical=counts.get(Severity.CRITICAL, 0),
        high=counts.get(Severity.HIGH, 0),
        medium=counts.get(Severity.MEDIUM, 0),
        low=counts.get(Severity.LOW, 0),
        info=counts.get(Severity.INFO, 0),
        pages_crawled=pages_crawled or 0,
    )

    return ScanDetail(**ScanOut.model_validate(scan).model_dump(), summary=summary)


@router.get("/{scan_id}/findings", response_model=list[FindingOut])
def list_findings(
    scan_id: uuid.UUID,
    db: Session = Depends(get_db),
    module: ModuleKey | None = None,
    severity: Severity | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Finding]:
    _get_scan_or_404(scan_id, db)

    stmt = select(Finding).where(Finding.scan_id == scan_id)
    if module is not None:
        stmt = stmt.where(Finding.module == module)
    if severity is not None:
        stmt = stmt.where(Finding.severity == severity)

    stmt = stmt.order_by(Finding.severity, Finding.rule).limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.post("/{scan_id}/cancel", response_model=ScanOut)
def cancel_scan(scan_id: uuid.UUID, db: Session = Depends(get_db)) -> Scan:
    scan = _get_scan_or_404(scan_id, db)

    if scan.status in TERMINAL_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Scan already finished with status '{scan.status}'",
        )

    if scan.celery_task_id:
        run_scan.AsyncResult(scan.celery_task_id).revoke(terminate=True)

    scan.status = ScanStatus.CANCELLED
    db.commit()
    db.refresh(scan)
    return scan
