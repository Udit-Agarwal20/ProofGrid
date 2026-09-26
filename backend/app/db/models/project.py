"""Project model representing workspace and tenant boundaries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.dataset import Dataset
    from app.db.models.entity import Entity, EntityMatch
    from app.db.models.evidence import Claim, RawDocument, Source
    from app.db.models.outbox import OutboxEvent
    from app.db.models.requirement import Requirement
    from app.db.models.workflow import Workflow


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Project(Base):
    """Logical workspace boundary.

    Hackathon mode operates as a single workspace, but project_id provides
    authoritative multi-tenancy and data isolation for all core entities.
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
    )

    # Relationships
    requirements: Mapped[list[Requirement]] = relationship(
        "Requirement",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    workflows: Mapped[list[Workflow]] = relationship(
        "Workflow",
        back_populates="project",
    )
    sources: Mapped[list[Source]] = relationship(
        "Source",
        back_populates="project",
    )
    raw_documents: Mapped[list[RawDocument]] = relationship(
        "RawDocument",
        back_populates="project",
    )
    claims: Mapped[list[Claim]] = relationship(
        "Claim",
        back_populates="project",
    )
    entities: Mapped[list[Entity]] = relationship(
        "Entity",
        back_populates="project",
    )
    entity_matches: Mapped[list[EntityMatch]] = relationship(
        "EntityMatch",
        back_populates="project",
    )
    datasets: Mapped[list[Dataset]] = relationship(
        "Dataset",
        back_populates="project",
    )
    outbox_events: Mapped[list[OutboxEvent]] = relationship(
        "OutboxEvent",
        back_populates="project",
    )
