"""Application configuration management using pydantic-settings.

Phase 1 requires fail-fast validation only for local runtime values.
Future service credentials remain optional placeholders.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Authoritative strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --------------------------------------------------------------------------
    # Core Application Settings (Phase 1 required)
    # --------------------------------------------------------------------------
    APP_ENV: Literal["local", "test", "staging", "production"] = "local"
    APP_NAME: str = "proofgrid-api"
    APP_VERSION: str = "0.1.0"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = Field(default=8000, ge=1, le=65535)
    PUBLIC_APP_URL: str = "http://localhost:3000"
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # --------------------------------------------------------------------------
    # Optional Placeholders for Future Phases (Phase 2+)
    # --------------------------------------------------------------------------
    DATABASE_URL: str | None = None
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    SUPABASE_JWKS_URL: str | None = None
    RAW_EVIDENCE_BUCKET: str = "proofgrid-raw-evidence"

    LLM_PROVIDER: str = "openai"
    LLM_API_KEY: str | None = None
    PLANNER_MODEL: str = "gpt-4o-2024-08-06"
    EXTRACTOR_MODEL: str = "gpt-4o-mini-2024-07-18"

    SEARCH_PROVIDER: str = "tavily"
    SEARCH_API_KEY: str | None = None

    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION: str = "proofgrid_entities"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    SENTRY_DSN: str | None = None
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None

    AUTH_ENABLED: bool = False
    ENABLE_BROWSER: bool = False
    ENABLE_QDRANT: bool = False
    ENABLE_PATHWAY: bool = False
    ENABLE_N8N_WEBHOOKS: bool = False
    STRICT_EVIDENCE: bool = True
    ACQUISITION_MODE: Literal["LIVE", "FIXTURE"] = "LIVE"
    MAX_CONCURRENT_RUNS: int = Field(default=3, ge=1)
    MAX_HTTP_CONCURRENCY: int = Field(default=8, ge=1)
    MAX_DOMAIN_CONCURRENCY: int = Field(default=2, ge=1)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
