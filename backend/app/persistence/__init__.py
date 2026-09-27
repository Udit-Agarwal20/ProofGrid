"""ProofGrid Persistence Application Layer.

Exposes Unit of Work, repositories, and persistence error hierarchy.
"""

from app.persistence.errors import (
    PersistenceConflictError,
    PersistenceConnectionError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
)
from app.persistence.repositories import (
    BaseRepository,
    ClaimRepository,
    DatasetRepository,
    EntityRepository,
    OutboxEventCreate,
    OutboxRepository,
    ProjectRepository,
    RequirementRepository,
    SourceRepository,
    WorkflowRepository,
)
from app.persistence.unit_of_work import (
    AbstractUnitOfWork,
    SqlAlchemyUnitOfWork,
    get_unit_of_work,
)

__all__ = [
    "AbstractUnitOfWork",
    "BaseRepository",
    "ClaimRepository",
    "DatasetRepository",
    "EntityRepository",
    "OutboxEventCreate",
    "OutboxRepository",
    "PersistenceConflictError",
    "PersistenceConnectionError",
    "PersistenceError",
    "PersistenceIntegrityError",
    "PersistenceNotFoundError",
    "ProjectRepository",
    "RequirementRepository",
    "SourceRepository",
    "SqlAlchemyUnitOfWork",
    "WorkflowRepository",
    "get_unit_of_work",
]
