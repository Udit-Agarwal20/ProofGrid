"""Requirement, dataset schema, and trust contract models."""

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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.dataset import DatasetVersion
    from app.db.models.project import Project
    from app.db.models.workflow import Workflow, WorkflowVersion


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Requirement(Base):
    """User requirement specification and compilation snapshot."""

    __tablename__ = "requirements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'COMPILED', 'ACCEPTED', 'REJECTED')",
            name="status",
        ),
        Index("ix_requirements_project_id", "project_id"),
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
    original_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="COMPILED")
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
    project: Mapped[Project] = relationship("Project", back_populates="requirements")
    dataset_schemas: Mapped[list[DatasetSchema]] = relationship(
        "DatasetSchema",
        back_populates="requirement",
    )
    trust_contracts: Mapped[list[TrustContract]] = relationship(
        "TrustContract",
        back_populates="requirement",
    )
    workflows: Mapped[list[Workflow]] = relationship(
        "Workflow",
        back_populates="requirement",
    )


class DatasetSchema(Base):
    """Immutable versioned schema contract confirmed by user or compiler."""

    __tablename__ = "dataset_schemas"
    __table_args__ = (
        UniqueConstraint(
            "requirement_id",
            "version_number",
            name="uq_dataset_schemas_requirement_version",
        ),
        CheckConstraint("version_number > 0", name="version_number"),
        Index("ix_dataset_schemas_project_id", "project_id"),
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
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    # Relationships
    project: Mapped[Project] = relationship("Project")
    requirement: Mapped[Requirement] = relationship(
        "Requirement",
        back_populates="dataset_schemas",
    )
    trust_contracts: Mapped[list[TrustContract]] = relationship(
        "TrustContract",
        back_populates="dataset_schema",
    )
    workflow_versions: Mapped[list[WorkflowVersion]] = relationship(
        "WorkflowVersion",
        back_populates="dataset_schema",
    )
    dataset_versions: Mapped[list[DatasetVersion]] = relationship(
        "DatasetVersion",
        back_populates="dataset_schema",
    )


class TrustContract(Base):
    """Accepted evidence, quality, and budget constraint contract."""

    __tablename__ = "trust_contracts"
    __table_args__ = (
        UniqueConstraint(
            "requirement_id",
            "version_number",
            name="uq_trust_contracts_requirement_version",
        ),
        CheckConstraint("version_number > 0", name="version_number"),
        Index("ix_trust_contracts_project_id", "project_id"),
        Index("ix_trust_contracts_dataset_schema_id", "dataset_schema_id"),
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
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dataset_schema_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_schemas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    project: Mapped[Project] = relationship("Project")
    requirement: Mapped[Requirement] = relationship(
        "Requirement",
        back_populates="trust_contracts",
    )
    dataset_schema: Mapped[DatasetSchema] = relationship(
        "DatasetSchema",
        back_populates="trust_contracts",
    )
    workflow_versions: Mapped[list[WorkflowVersion]] = relationship(
        "WorkflowVersion",
        back_populates="trust_contract",
    )
