import asyncio
from logging.config import fileConfig
from pathlib import Path
import sys

# Ensure backend root is on sys.path
_backend_root = str(Path(__file__).resolve().parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set model metadata for autogenerate support
target_metadata = Base.metadata

settings = get_settings()
direct_url = settings.database_direct_url_unmasked


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    if not direct_url:
        raise RuntimeError(
            "Alembic migration failed: DATABASE_DIRECT_URL (or DATABASE_URL_UNPOOLED) is not configured."
        )

    context.configure(
        url=direct_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using AsyncEngine connected to DATABASE_DIRECT_URL."""
    if not direct_url:
        raise RuntimeError(
            "Alembic migration failed: DATABASE_DIRECT_URL (or DATABASE_URL_UNPOOLED) is not configured."
        )

    connectable = create_async_engine(
        direct_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
