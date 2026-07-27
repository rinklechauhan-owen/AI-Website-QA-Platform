"""Celery tasks that drive a scan through crawl → audit → AI analysis.

The orchestration and status transitions are wired up here; the individual audit modules
are still stubs. See app/modules/README.md for the module contract.
"""

import logging
from datetime import UTC, datetime

from app.celery_app import celery_app
from app.db import SessionLocal
from app.enums import ModuleKey, ScanStatus
from app.models import Scan
from app.modules import get_module

logger = logging.getLogger(__name__)

# Modules that need the crawl output but run before the AI passes.
TECHNICAL_MODULES = {
    ModuleKey.SEO,
    ModuleKey.IMAGES,
    ModuleKey.PERFORMANCE,
    ModuleKey.ACCESSIBILITY,
    ModuleKey.RESPONSIVE,
    ModuleKey.FORMS,
    ModuleKey.BUGS,
}

# Modules that call vision or language models and therefore run last.
AI_MODULES = {
    ModuleKey.DESIGN,
    ModuleKey.CONTENT,
    ModuleKey.SCREENSHOTS,
    ModuleKey.CHECKLIST,
}


@celery_app.task(name="scans.run", bind=True)
def run_scan(
    self,
    scan_id: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
) -> dict:
    """Run every requested module for a scan and record its findings."""
    db = SessionLocal()
    try:
        scan = db.get(Scan, scan_id)
        if scan is None:
            logger.error("run_scan called with unknown scan_id=%s", scan_id)
            return {"scan_id": scan_id, "status": "missing"}

        scan.status = ScanStatus.CRAWLING
        scan.started_at = datetime.now(UTC)
        db.commit()

        requested = [ModuleKey(m) for m in scan.requested_modules]
        context = {
            "scan_id": scan_id,
            "url": scan.url,
            "max_pages": max_pages,
            "max_depth": max_depth,
            "design_upload_key": scan.design_upload_key,
            "content_upload_key": scan.content_upload_key,
        }

        # Module 1 always runs first — every other module consumes its output.
        crawl = get_module(ModuleKey.CRAWL)
        context["crawl"] = crawl.run(db, context)

        for phase, status_value in (
            (TECHNICAL_MODULES, ScanStatus.AUDITING),
            (AI_MODULES, ScanStatus.ANALYZING),
        ):
            phase_modules = [m for m in requested if m in phase]
            if not phase_modules:
                continue

            scan.status = status_value
            db.commit()

            for key in phase_modules:
                try:
                    result = get_module(key).run(db, context)
                    if result and (score := result.get("score")) is not None:
                        scan.scores = {**scan.scores, key.value: score}
                    db.commit()
                except NotImplementedError:
                    logger.info("Module '%s' is not implemented yet; skipping", key)
                    db.rollback()
                except Exception:
                    logger.exception("Module '%s' failed for scan %s", key, scan_id)
                    db.rollback()

        scores = list(scan.scores.values())
        scan.overall_score = round(sum(scores) / len(scores), 1) if scores else None
        scan.status = ScanStatus.COMPLETED
        scan.finished_at = datetime.now(UTC)
        db.commit()

        return {"scan_id": scan_id, "status": scan.status.value}

    except Exception as exc:
        db.rollback()
        scan = db.get(Scan, scan_id)
        if scan is not None:
            scan.status = ScanStatus.FAILED
            scan.error = f"{exc.__class__.__name__}: {exc}"
            scan.finished_at = datetime.now(UTC)
            db.commit()
        raise
    finally:
        db.close()
