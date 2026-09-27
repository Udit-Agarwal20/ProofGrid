"""Base repository abstraction providing session reference."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Base repository wrapping an active AsyncSession.

    Repositories NEVER create independent engines, never create sessions,
    never call commit(), and never call rollback(). Transaction ownership
    belongs exclusively to the Unit of Work.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """Return the shared AsyncSession bound to this repository."""
        return self._session
