"""Liveness and readiness endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.config import settings
from app.db import get_db

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Liveness — does not touch dependencies."""
    return {"status": "ok", "version": __version__, "environment": settings.environment}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    """Readiness — confirms the database is reachable."""
    checks: dict[str, str] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - surface the reason to the caller
        checks["database"] = f"error: {exc.__class__.__name__}"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
