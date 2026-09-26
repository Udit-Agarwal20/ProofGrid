"""Real Neon PostgreSQL integration tests.

Verifies live pooled connection, direct migration connection, async engine lifecycle,
AsyncSession transaction rollback, health checks, and Alembic version state.
Requires DATABASE_URL and DATABASE_DIRECT_URL.
"""

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings, get_settings
from app.db.engine import create_engine_instance
from app.db.health import check_database_health
from app.db.session import get_session_factory

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def settings() -> Settings:
    s = get_settings()
    if not s.DATABASE_URL or not s.database_direct_url_unmasked:
        pytest.skip(
            "Skipping database integration tests: DATABASE_URL or DATABASE_DIRECT_URL not configured"
        )
    return s


@pytest.mark.asyncio
async def test_real_neon_pooled_connectivity(settings: Settings) -> None:
    """Verify live connectivity and SELECT 1 against Neon pooled connection."""
    engine = create_engine_instance()
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            assert res.scalar() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_neon_direct_connectivity(settings: Settings) -> None:
    """Verify live connectivity and SELECT 1 against Neon direct migration connection."""
    direct_url = settings.database_direct_url_unmasked
    assert direct_url is not None
    engine = create_async_engine(direct_url)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            assert res.scalar() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_async_engine_lifecycle(settings: Settings) -> None:
    """Verify async engine instance creation, execution, and disposal."""
    engine = create_engine_instance(pool_size=2, max_overflow=0)
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT 42 AS answer"))
        row = res.mappings().one()
        assert row["answer"] == 42
    await engine.dispose()


@pytest.mark.asyncio
async def test_async_session_creation_and_cleanup(settings: Settings) -> None:
    """Verify AsyncSession lifecycle and clean closure."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        res = await session.execute(text("SELECT 100"))
        assert res.scalar() == 100
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_transaction_rollback_behavior(settings: Settings) -> None:
    """Verify that transaction rollbacks cleanly discard uncommitted transaction state."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Start transaction explicitly
        tx = await session.begin()
        assert session.in_transaction()

        await session.execute(text("SELECT 1"))

        # Rollback transaction
        await tx.rollback()
        assert not session.in_transaction()


@pytest.mark.asyncio
async def test_health_checker_success_against_neon(settings: Settings) -> None:
    """Verify check_database_health succeeds and returns healthy status and latency."""
    result = await check_database_health(timeout_seconds=10.0)
    assert result.status == "healthy"
    assert result.latency_ms is not None
    assert result.latency_ms > 0
    assert result.error is None


@pytest.mark.asyncio
async def test_health_checker_graceful_failure_simulation() -> None:
    """Verify check_database_health sanitizes error messages and handles faults gracefully."""

    class FaultyEngine:
        def connect(self) -> Any:
            raise ConnectionRefusedError(
                "Connection refused to postgresql://user:supersecretpass@badhost:5432/db"
            )

    result = await check_database_health(engine=FaultyEngine(), timeout_seconds=1.0)  # type: ignore[arg-type]
    assert result.status == "unhealthy"
    assert result.error is not None
    assert "ConnectionRefusedError" in result.error
    # Non-negotiable security requirement: password must never appear in error
    assert "supersecretpass" not in result.error


@pytest.mark.asyncio
async def test_alembic_current_revision_is_head(settings: Settings) -> None:
    """Verify that Alembic's tracking table in Neon contains the baseline migration revision ID."""
    direct_url = settings.database_direct_url_unmasked
    assert direct_url is not None
    engine = create_async_engine(direct_url)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT version_num FROM alembic_version"))
            row = res.fetchone()
            assert row is not None, "alembic_version table is empty"
            version_num = row[0]
            assert version_num == "21242d5d8505", (
                f"Expected revision '21242d5d8505', got: {version_num}"
            )
    finally:
        await engine.dispose()
