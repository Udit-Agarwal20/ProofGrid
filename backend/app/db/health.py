"""Database health checking utility.

Executes a bounded SELECT 1 query against the database engine to verify
connectivity without exposing connection parameters, credentials, or DSNs.
"""

import asyncio
import time
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.engine import get_async_engine

logger = get_logger("proofgrid.db.health")


class DatabaseHealthResult(BaseModel):
    """Structured health check result for database connectivity."""

    status: Literal["healthy", "unhealthy", "unconfigured"]
    latency_ms: float | None = Field(
        default=None, description="Round-trip query latency in milliseconds"
    )
    error: str | None = Field(default=None, description="Sanitized error description on failure")


async def check_database_health(
    engine: AsyncEngine | None = None,
    timeout_seconds: float = 10.0,
) -> DatabaseHealthResult:
    """Execute a bounded SELECT 1 check against the database.

    Guarantees no raw connection strings, usernames, or passwords appear in error messages.
    """
    settings = get_settings()
    if not settings.DATABASE_URL:
        return DatabaseHealthResult(
            status="unconfigured",
            error="DATABASE_URL is not configured",
        )

    start_time = time.perf_counter()
    try:
        target_engine = engine or get_async_engine()

        async def _ping() -> None:
            async with target_engine.connect() as conn:
                res = await conn.execute(text("SELECT 1"))
                val = res.scalar()
                if val != 1:
                    raise RuntimeError("Unexpected scalar response from database ping query")

        await asyncio.wait_for(_ping(), timeout=timeout_seconds)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return DatabaseHealthResult(
            status="healthy",
            latency_ms=latency_ms,
        )

    except TimeoutError:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning("Database health check timed out", extra={"timeout": timeout_seconds})
        return DatabaseHealthResult(
            status="unhealthy",
            latency_ms=latency_ms,
            error=f"Database ping timed out after {timeout_seconds}s",
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        # Sanitize exception message so no connection details or credentials can leak
        err_type = exc.__class__.__name__
        logger.warning("Database health check failed", extra={"error_type": err_type})
        return DatabaseHealthResult(
            status="unhealthy",
            latency_ms=latency_ms,
            error=f"Database connection error: {err_type}",
        )
