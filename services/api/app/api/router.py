"""Top-level API router — mounted at /api/v1 by app.main."""

from fastapi import APIRouter

from app.api.routes import health, reports, scans

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(scans.router, prefix="/scans", tags=["scans"])
api_router.include_router(reports.router, prefix="/scans", tags=["reports"])
