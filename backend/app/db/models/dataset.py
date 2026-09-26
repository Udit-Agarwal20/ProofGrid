"""Dataset, versioning, canonical values, conflicts, and materialized records models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.entity import Entity
    from app.db.models.evidence import Claim
    from app.db.models.project import Project
    from app.db.models.requirement import DatasetSchema
    from app.db.models.workflow import Workflow, WorkflowRun


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Dataset(Base):
    """Stable logical dataset identity."""

    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_datasets_project_slug"),
        Index("ix_datasets_workflow_id", "workflow_id"),
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
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="RESTRICT"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
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
    project: Mapped[Project] = relationship("Project", back_populates="datasets")
    workflow: Mapped[Workflow | None] = relationship("Workflow", back_populates="datasets")
    versions: Mapped[list[DatasetVersion]] = relationship(
        "DatasetVersion",
        back_populates="dataset",
    )


class DatasetVersion(Base):
    """Immutable snapshot of one dataset generation resulting from a workflow run."""

    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "version_number", name="uq_dataset_versions_dataset_version"
        ),
        CheckConstraint("version_number > 0", name="version_number"),
        CheckConstraint("record_count >= 0", name="record_count"),
        CheckConstraint(
            "status IN ('DRAFT', 'FINALIZING', 'FINALIZED', 'FAILED')",
            name="status",
        ),
        Index("ix_dataset_versions_project_id", "project_id"),
        Index("ix_dataset_versions_schema_id", "dataset_schema_id"),
        Index("ix_dataset_versions_run_id", "workflow_run_id"),
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
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dataset_schema_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_schemas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diff_summary: Mapped[dict[str, Any]] = mapped_column(
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
    project: Mapped[Project] = relationship("Project")
    dataset: Mapped[Dataset] = relationship("Dataset", back_populates="versions")
    dataset_schema: Mapped[DatasetSchema] = relationship(
        "DatasetSchema",
        back_populates="dataset_versions",
    )
    workflow_run: Mapped[WorkflowRun | None] = relationship(
        "WorkflowRun",
        back_populates="dataset_versions",
    )
    records: Mapped[list[DatasetVersionRecord]] = relationship(
        "DatasetVersionRecord",
        back_populates="dataset_version",
    )
    canonical_values: Mapped[list[CanonicalValue]] = relationship(
        "CanonicalValue",
        back_populates="dataset_version",
    )
    conflicts: Mapped[list[Conflict]] = relationship(
        "Conflict",
        back_populates="dataset_version",
    )


class CanonicalValue(Base):
    """Field-level canonical read model derived from claims for a dataset version."""

    __tablename__ = "canonical_values"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id",
            "entity_id",
            "field_key",
            name="uq_canonical_values_version_entity_field",
        ),
        CheckConstraint(
            "trust_status IN ('VERIFIED', 'SUPPORTED', 'SINGLE_SOURCE', 'CONFLICTING', 'NEEDS_REVIEW', 'MISSING')",
            name="trust_status",
        ),
        Index("ix_canonical_values_project_id", "project_id"),
        Index("ix_canonical_values_field_key", "field_key"),
        Index("ix_canonical_values_selected_claim_id", "selected_claim_id"),
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
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    trust_status: Mapped[str] = mapped_column(String(50), nullable=False)
    selected_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=True,
    )
    provenance_summary: Mapped[dict[str, Any]] = mapped_column(
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
    project: Mapped[Project] = relationship("Project")
    dataset_version: Mapped[DatasetVersion] = relationship(
        "DatasetVersion",
        back_populates="canonical_values",
    )
    entity: Mapped[Entity] = relationship("Entity", back_populates="canonical_values")
    selected_claim: Mapped[Claim | None] = relationship("Claim")


class Conflict(Base):
    """Field-level disagreement or competing assertions across sources."""

    __tablename__ = "conflicts"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id",
            "entity_id",
            "field_key",
            name="uq_conflicts_version_entity_field",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'RESOLVED', 'DISMISSED')",
            name="status",
        ),
        CheckConstraint(
            "conflict_type IN ('VALUE_MISMATCH', 'SOURCE_CONTRADICTION', 'STALE_DATA', 'FORMAT_AMBIGUITY')",
            name="type",
        ),
        Index("ix_conflicts_project_id", "project_id"),
        Index("ix_conflicts_status", "status"),
        Index("ix_conflicts_resolved_claim_id", "resolved_claim_id"),
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
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    conflict_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="VALUE_MISMATCH",
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="OPEN")
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    resolved_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    project: Mapped[Project] = relationship("Project")
    dataset_version: Mapped[DatasetVersion] = relationship(
        "DatasetVersion",
        back_populates="conflicts",
    )
    entity: Mapped[Entity] = relationship("Entity", back_populates="conflicts")
    resolved_claim: Mapped[Claim | None] = relationship("Claim")


class DatasetVersionRecord(Base):
    """Materialized denormalized record read model for fast grid queries."""

    __tablename__ = "dataset_version_records"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id",
            "entity_id",
            name="uq_dataset_version_records_version_entity",
        ),
        Index("ix_dataset_version_records_project_id", "project_id"),
        Index("ix_dataset_version_records_entity_id", "entity_id"),
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
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    record_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    trust_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    # Relationships
    project: Mapped[Project] = relationship("Project")
    dataset_version: Mapped[DatasetVersion] = relationship(
        "DatasetVersion",
        back_populates="records",
    )
    entity: Mapped[Entity] = relationship("Entity", back_populates="records")
