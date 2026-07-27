"""FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.config import settings

logging.basicConfig(level=settings.log_level.upper())

app = FastAPI(
    title="AI Website QA Platform API",
    description="Website QA, design review, content review, and automated bug reporting.",
    version=__version__,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": "website-qa-api", "version": __version__, "docs": "/docs"}
