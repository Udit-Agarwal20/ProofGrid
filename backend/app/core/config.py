"""Application configuration management using pydantic-settings.

Phase 1 requires fail-fast validation only for local runtime values.
Future service credentials remain optional placeholders.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str, driver: str = "postgresql+psycopg") -> str:
    """Normalize a database URL scheme to use the target driver (default: postgresql+psycopg)."""
    if url.startswith("postgresql://"):
        return f"{driver}://{url[len('postgresql://') :]}"
    if url.startswith("postgres://"):
        return f"{driver}://{url[len('postgres://') :]}"
    return url


def redact_database_url(url: str | SecretStr | None) -> str:
    """Redact credentials from database URL for safe logging and diagnostics.

    Never raises an exception or leaks secrets if parsing fails.
    """
    if url is None:
        return "<none>"
    raw_str = url.get_secret_value() if isinstance(url, SecretStr) else str(url)
    if not raw_str.strip():
        return "<none>"
    try:
        from sqlalchemy.engine import make_url

        u = make_url(raw_str)
        return u.render_as_string(hide_password=True)
    except Exception:
        # Under no circumstance return raw_str on parse failure
        return "<redacted-unparseable-url>"


class Settings(BaseSettings):
    """Authoritative strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../.env"),
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
    # Database Settings (Phase 2A - Neon PostgreSQL Authoritative Persistence)
    # --------------------------------------------------------------------------
    DATABASE_URL: SecretStr | None = None
    DATABASE_DIRECT_URL: SecretStr | None = None
    DATABASE_URL_UNPOOLED: SecretStr | None = None

    @property
    def database_url_unmasked(self) -> str | None:
        """Return the raw pooled DATABASE_URL string with normalized postgresql+psycopg scheme."""
        if not self.DATABASE_URL:
            return None
        return normalize_database_url(self.DATABASE_URL.get_secret_value())

    @property
    def database_direct_url_unmasked(self) -> str | None:
        """Return the raw direct/unpooled connection URL for Alembic migrations."""
        target = self.DATABASE_DIRECT_URL or self.DATABASE_URL_UNPOOLED
        if not target:
            return None
        return normalize_database_url(target.get_secret_value())

    @property
    def database_url_redacted(self) -> str:
        """Return safe redacted string for runtime DATABASE_URL."""
        return redact_database_url(self.DATABASE_URL)

    @property
    def database_direct_url_redacted(self) -> str:
        """Return safe redacted string for direct migration DATABASE_DIRECT_URL."""
        target = self.DATABASE_DIRECT_URL or self.DATABASE_URL_UNPOOLED
        return redact_database_url(target)

    # --------------------------------------------------------------------------
    # Optional Placeholders for Future Phases
    # --------------------------------------------------------------------------
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
