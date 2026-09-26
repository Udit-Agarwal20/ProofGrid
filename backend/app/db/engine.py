"""Runtime Async SQLAlchemy Engine Management.

Connects to Neon PostgreSQL through the pooled DATABASE_URL endpoint using
psycopg 3 async driver. Connection pooling parameters are configured conservatively
for transaction-pooled PgBouncer compatibility.
"""

from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)

from app.core.config import get_settings, redact_database_url
from app.core.logging import get_logger

logger = get_logger("proofgrid.db.engine")

# Module-level engine singleton
_async_engine: AsyncEngine | None = None


def create_engine_instance(
    url: str | None = None,
    **kwargs: Any,
) -> AsyncEngine:
    """Create a new AsyncEngine instance with conservative pooling defaults."""
    settings = get_settings()
    target_url = url or settings.database_url_unmasked

    if not target_url:
        raise ValueError("Cannot initialize database engine: DATABASE_URL is not configured.")

    # Log safe redacted connection target
    logger.info(
        "Initializing runtime async database engine",
        extra={"target": redact_database_url(target_url)},
    )

    default_kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10,
        "max_overflow": 5,
        "echo": False,
    }
    default_kwargs.update(kwargs)

    return create_async_engine(target_url, **default_kwargs)


def get_async_engine() -> AsyncEngine:
    """Return the cached singleton AsyncEngine, creating it if necessary."""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_engine_instance()
    return _async_engine


async def dispose_async_engine() -> None:
    """Cleanly dispose of the singleton AsyncEngine and all connection pools."""
    global _async_engine
    if _async_engine is not None:
        logger.info("Disposing runtime async database engine")
        await _async_engine.dispose()
        _async_engine = None
