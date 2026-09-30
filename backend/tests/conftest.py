"""Database tests own an isolated schema; never truncate an existing workspace."""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import get_settings, normalize_database_url


@pytest.fixture
async def isolated_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    settings = get_settings()
    url = os.getenv("TEST_DATABASE_URL") or settings.database_direct_url_unmasked
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an ephemeral/local PostgreSQL database.")
    url = normalize_database_url(url)
    schema = "proofgrid_test_" + uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url,
        pool_size=5,
        max_overflow=5,
        hide_parameters=True,
        connect_args={"options": f"-csearch_path={schema},public"},
    )

    def migrate(connection: Connection) -> None:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.set_main_option(
            "script_location", str(Path(__file__).resolve().parents[1] / "alembic")
        )
        config.attributes["connection"] = connection
        config.attributes["version_table_schema"] = schema
        command.upgrade(config, "head")

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
        yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()
