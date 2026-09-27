"""Async Unit of Work for transactional persistence boundaries in ProofGrid."""

from __future__ import annotations

import contextlib
import types
from abc import ABC, abstractmethod
from typing import Self

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_session_factory
from app.persistence.errors import (
    PersistenceError,
    translate_db_error,
)
from app.persistence.repositories.claim import ClaimRepository
from app.persistence.repositories.dataset import DatasetRepository
from app.persistence.repositories.entity import EntityRepository
from app.persistence.repositories.outbox import OutboxRepository
from app.persistence.repositories.project import ProjectRepository
from app.persistence.repositories.requirement import RequirementRepository
from app.persistence.repositories.source import SourceRepository
from app.persistence.repositories.workflow import WorkflowRepository


class AbstractUnitOfWork(ABC):
    """Abstract interface defining the Unit of Work contract."""

    @property
    @abstractmethod
    def projects(self) -> ProjectRepository:
        """Project repository bound to the unit of work session."""
        ...

    @property
    @abstractmethod
    def requirements(self) -> RequirementRepository:
        """Requirement repository bound to the unit of work session."""
        ...

    @property
    @abstractmethod
    def workflows(self) -> WorkflowRepository:
        """Workflow repository bound to the unit of work session."""
        ...

    @property
    @abstractmethod
    def sources(self) -> SourceRepository:
        """Source repository bound to the unit of work session."""
        ...

    @property
    @abstractmethod
    def claims(self) -> ClaimRepository:
        """Claim repository bound to the unit of work session."""
        ...

    @property
    @abstractmethod
    def entities(self) -> EntityRepository:
        """Entity repository bound to the unit of work session."""
        ...

    @property
    @abstractmethod
    def datasets(self) -> DatasetRepository:
        """Dataset repository bound to the unit of work session."""
        ...

    @property
    @abstractmethod
    def outbox(self) -> OutboxRepository:
        """Transactional outbox repository bound to the unit of work session."""
        ...

    @abstractmethod
    async def __aenter__(self) -> Self:
        """Enter transactional context."""
        ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Exit transactional context with automatic cleanup."""
        ...

    @abstractmethod
    async def commit(self) -> None:
        """Commit current transaction."""
        ...

    @abstractmethod
    async def rollback(self) -> None:
        """Roll back current transaction."""
        ...


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """SQLAlchemy AsyncSession implementation of Unit of Work.

    Guarantees that all child repositories share the exact same AsyncSession,
    commits must be invoked explicitly, and any uncommitted or errored transaction
    is rolled back cleanly.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._session: AsyncSession | None = None
        self._committed: bool = False
        self._closed: bool = False

        self._projects: ProjectRepository | None = None
        self._requirements: RequirementRepository | None = None
        self._workflows: WorkflowRepository | None = None
        self._sources: SourceRepository | None = None
        self._claims: ClaimRepository | None = None
        self._entities: EntityRepository | None = None
        self._datasets: DatasetRepository | None = None
        self._outbox: OutboxRepository | None = None

    @property
    def session(self) -> AsyncSession:
        """Return the shared session bound to this Unit of Work."""
        if self._session is None or self._closed:
            raise PersistenceError("UnitOfWork is not active or has been closed.")
        return self._session

    @property
    def projects(self) -> ProjectRepository:
        if self._projects is None:
            raise PersistenceError("UnitOfWork must be entered before accessing repositories.")
        return self._projects

    @property
    def requirements(self) -> RequirementRepository:
        if self._requirements is None:
            raise PersistenceError("UnitOfWork must be entered before accessing repositories.")
        return self._requirements

    @property
    def workflows(self) -> WorkflowRepository:
        if self._workflows is None:
            raise PersistenceError("UnitOfWork must be entered before accessing repositories.")
        return self._workflows

    @property
    def sources(self) -> SourceRepository:
        if self._sources is None:
            raise PersistenceError("UnitOfWork must be entered before accessing repositories.")
        return self._sources

    @property
    def claims(self) -> ClaimRepository:
        if self._claims is None:
            raise PersistenceError("UnitOfWork must be entered before accessing repositories.")
        return self._claims

    @property
    def entities(self) -> EntityRepository:
        if self._entities is None:
            raise PersistenceError("UnitOfWork must be entered before accessing repositories.")
        return self._entities

    @property
    def datasets(self) -> DatasetRepository:
        if self._datasets is None:
            raise PersistenceError("UnitOfWork must be entered before accessing repositories.")
        return self._datasets

    @property
    def outbox(self) -> OutboxRepository:
        if self._outbox is None:
            raise PersistenceError("UnitOfWork must be entered before accessing repositories.")
        return self._outbox

    async def __aenter__(self) -> Self:
        if self._closed:
            raise PersistenceError("Cannot reuse a closed UnitOfWork instance.")
        if self._session is not None:
            raise PersistenceError("UnitOfWork is already entered.")

        self._session = self._session_factory()
        self._committed = False

        # All 8 repositories share this exact same AsyncSession instance
        self._projects = ProjectRepository(self._session)
        self._requirements = RequirementRepository(self._session)
        self._workflows = WorkflowRepository(self._session)
        self._sources = SourceRepository(self._session)
        self._claims = ClaimRepository(self._session)
        self._entities = EntityRepository(self._session)
        self._datasets = DatasetRepository(self._session)
        self._outbox = OutboxRepository(self._session)

        await self._session.begin()
        return self

    async def commit(self) -> None:
        """Commit the current Unit of Work transaction.

        Translates database errors into sanitized PersistenceErrors and rolls back.
        """
        if self._session is None or self._closed:
            raise PersistenceError("Cannot commit: UnitOfWork is not active.")
        if self._committed:
            raise PersistenceError("UnitOfWork transaction has already been committed.")

        try:
            await self._session.commit()
            self._committed = True
        except (IntegrityError, SQLAlchemyError) as exc:
            with contextlib.suppress(Exception):
                await self._session.rollback()
            raise translate_db_error(exc) from exc

    async def rollback(self) -> None:
        """Roll back the current Unit of Work transaction."""
        if self._session is not None and not self._closed:
            try:
                await self._session.rollback()
            except Exception as exc:
                raise PersistenceError(
                    f"Error during rollback: {exc}",
                    original_error=exc,
                ) from exc

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                # An exception occurred in the with-block: roll back
                await self.rollback()
            elif not self._committed:
                # Exited with-block without calling commit(): roll back uncommitted state
                await self.rollback()
        finally:
            if self._session is not None:
                await self._session.close()
                self._session = None
            self._closed = True


def get_unit_of_work(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> SqlAlchemyUnitOfWork:
    """Factory returning a new Unit of Work instance."""
    return SqlAlchemyUnitOfWork(session_factory=session_factory)
