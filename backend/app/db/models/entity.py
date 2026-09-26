"""Entity resolution and identity models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.dataset import CanonicalValue, Conflict, DatasetVersionRecord
    from app.db.models.evidence import Claim
    from app.db.models.project import Project


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Entity(Base):
    """Canonical real-world entity identity."""

    __tablename__ = "entities"
    __table_args__ = (
        Index(
            "ux_entities_project_stable_key",
            "project_id",
            "stable_entity_key",
            unique=True,
            postgresql_where=text("stable_entity_key IS NOT NULL"),
        ),
        Index("ix_entities_project_type", "project_id", "entity_type"),
        Index("ix_entities_canonical_name", "canonical_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="company",
    )
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stable_entity_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
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
    project: Mapped[Project] = relationship("Project", back_populates="entities")
    claims: Mapped[list[Claim]] = relationship(
        "Claim",
        back_populates="entity",
    )
    canonical_values: Mapped[list[CanonicalValue]] = relationship(
        "CanonicalValue",
        back_populates="entity",
    )
    conflicts: Mapped[list[Conflict]] = relationship(
        "Conflict",
        back_populates="entity",
    )
    records: Mapped[list[DatasetVersionRecord]] = relationship(
        "DatasetVersionRecord",
        back_populates="entity",
    )


class EntityMatch(Base):
    """Candidate entity matching and merge/review decisions."""

    __tablename__ = "entity_matches"
    __table_args__ = (
        CheckConstraint(
            "source_entity_id < target_entity_id",
            name="canonical_pair_order",
        ),
        CheckConstraint(
            "decision IN ('AUTO_MERGE', 'REVIEW', 'KEEP_SEPARATE', 'HUMAN_MERGE', 'HUMAN_SEPARATE')",
            name="decision",
        ),
        CheckConstraint(
            "score IS NULL OR (score >= 0.0 AND score <= 1.0)",
            name="score",
        ),
        UniqueConstraint(
            "project_id", "source_entity_id", "target_entity_id", name="uq_entity_matches_pair"
        ),
        Index("ix_entity_matches_source_entity", "source_entity_id"),
        Index("ix_entity_matches_target_entity", "target_entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    signals: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    reason: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    # Relationships
    project: Mapped[Project] = relationship("Project", back_populates="entity_matches")
    source_entity: Mapped[Entity] = relationship("Entity", foreign_keys=[source_entity_id])
    target_entity: Mapped[Entity] = relationship("Entity", foreign_keys=[target_entity_id])
