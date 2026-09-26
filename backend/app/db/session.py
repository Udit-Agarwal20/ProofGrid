"""AsyncSession management and lifecycle dependency.

Provides request-scoped AsyncSession instances with automatic rollback on error
and guaranteed session cleanup.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.db.engine import get_async_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return an async session factory bound to the singleton engine."""
    engine = get_async_engine()
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an AsyncSession.

    Ensures clean session closure and automatic transaction rollback on unhandled errors.
    Commits must be invoked explicitly at the workflow or endpoint transaction boundary.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
