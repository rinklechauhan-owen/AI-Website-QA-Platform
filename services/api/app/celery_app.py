"""Celery application. Scans run out-of-band so the API stays responsive."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "website_qa",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.scan_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # A full-site scan with Lighthouse and AI passes can legitimately run for minutes.
    task_soft_time_limit=15 * 60,
    task_time_limit=20 * 60,
    worker_prefetch_multiplier=1,
    result_expires=7 * 24 * 60 * 60,
)
