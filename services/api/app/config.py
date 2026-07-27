"""Application settings, loaded from the environment (see .env.example at the repo root)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "info"
    api_base_url: str = "http://localhost:8000"

    # Database
    database_url: str = "postgresql+psycopg://qa:qa@localhost:5432/website_qa"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # AI
    openai_api_key: str = ""
    openai_text_model: str = "gpt-4o"
    openai_vision_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-large"

    # Crawler
    crawl_max_pages: int = 50
    crawl_max_depth: int = 3
    crawl_timeout_seconds: int = 30
    crawl_user_agent: str = "AI-Website-QA-Platform/1.0"
    crawl_respect_robots_txt: bool = True
    crawl_concurrency: int = 4

    # Storage
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = "./storage"
    s3_bucket: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_endpoint_url: str = ""

    # Auth (Phase 4)
    jwt_secret: str = "change-me-in-production"
    google_client_id: str = ""
    google_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — safe to use as a FastAPI dependency."""
    return Settings()


settings = get_settings()
