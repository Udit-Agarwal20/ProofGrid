"""Workflow execution and orchestration models."""

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
    from app.db.models.dataset import Dataset, DatasetVersion
    from app.db.models.evidence import Claim, RawDocument
    from app.db.models.project import Project
    from app.db.models.requirement import DatasetSchema, Requirement, TrustContract


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Workflow(Base):
    """Stable workflow identity linking requirements to executable plans."""

    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'ARCHIVED', 'PAUSED')",
            name="status",
        ),
        Index("ix_workflows_project_id", "project_id"),
        Index("ix_workflows_requirement_id", "requirement_id"),
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")
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
    project: Mapped[Project] = relationship("Project", back_populates="workflows")
    requirement: Mapped[Requirement] = relationship(
        "Requirement",
        back_populates="workflows",
    )
    versions: Mapped[list[WorkflowVersion]] = relationship(
        "WorkflowVersion",
        back_populates="workflow",
    )
    datasets: Mapped[list[Dataset]] = relationship(
        "Dataset",
        back_populates="workflow",
    )


class WorkflowVersion(Base):
    """Immutable compiled execution plan snapshot."""

    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "version_number",
            name="uq_workflow_versions_workflow_version",
        ),
        CheckConstraint("version_number > 0", name="version_number"),
        Index("ix_workflow_versions_dataset_schema_id", "dataset_schema_id"),
        Index("ix_workflow_versions_trust_contract_id", "trust_contract_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_schema_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_schemas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trust_contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trust_contracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan_dag: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    planner_metadata: Mapped[dict[str, Any]] = mapped_column(
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
    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="versions")
    dataset_schema: Mapped[DatasetSchema] = relationship(
        "DatasetSchema",
        back_populates="workflow_versions",
    )
    trust_contract: Mapped[TrustContract] = relationship(
        "TrustContract",
        back_populates="workflow_versions",
    )
    runs: Mapped[list[WorkflowRun]] = relationship(
        "WorkflowRun",
        back_populates="workflow_version",
    )


class WorkflowRun(Base):
    """Single concrete execution of a workflow version."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED', 'QUEUED', 'RUNNING', 'PARTIAL', 'COMPLETED', 'FAILED', 'CANCEL_REQUESTED', 'CANCELLED')",
            name="status",
        ),
        CheckConstraint("run_mode IN ('LIVE', 'FIXTURE')", name="run_mode"),
        Index("ix_workflow_runs_project_id", "project_id"),
        Index("ix_workflow_runs_status", "status"),
        Index(
            "ix_workflow_runs_version_status_created",
            "workflow_version_id",
            "status",
            "created_at",
        ),
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
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="CREATED")
    run_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="LIVE")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    budget_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    # Relationships
    project: Mapped[Project] = relationship("Project")
    workflow_version: Mapped[WorkflowVersion] = relationship(
        "WorkflowVersion",
        back_populates="runs",
    )
    step_runs: Mapped[list[StepRun]] = relationship(
        "StepRun",
        back_populates="workflow_run",
    )
    events: Mapped[list[WorkflowEvent]] = relationship(
        "WorkflowEvent",
        back_populates="workflow_run",
    )
    raw_documents: Mapped[list[RawDocument]] = relationship(
        "RawDocument",
        back_populates="workflow_run",
    )
    claims: Mapped[list[Claim]] = relationship(
        "Claim",
        back_populates="workflow_run",
    )
    dataset_versions: Mapped[list[DatasetVersion]] = relationship(
        "DatasetVersion",
        back_populates="workflow_run",
    )


class StepRun(Base):
    """Execution attempt and queue state for an individual PlanDAG node."""

    __tablename__ = "step_runs"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id",
            "node_id",
            "attempt",
            name="ux_step_idempotency",
        ),
        UniqueConstraint("workflow_run_id", "node_id", name="uq_step_runs_run_node"),
        CheckConstraint("attempt > 0", name="attempt"),
        CheckConstraint(
            "status IN ('PENDING', 'READY', 'LEASED', 'RUNNING', 'RETRY_WAIT', 'SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELLED')",
            name="status",
        ),
        CheckConstraint(
            "operator_type IN ('DISCOVER', 'FETCH_HTTP', 'FETCH_BROWSER', 'EXTRACT', 'NORMALIZE', 'VALIDATE', 'ENTITY_RESOLVE', 'RECONCILE', 'MATERIALIZE', 'INDEX', 'EXPORT')",
            name="operator_type",
        ),
        Index("ix_step_runs_run_status", "workflow_run_id", "status"),
        Index("ix_step_runs_ready", "status", "available_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_type: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    output: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    workflow_run: Mapped[WorkflowRun] = relationship(
        "WorkflowRun",
        back_populates="step_runs",
    )


class WorkflowEvent(Base):
    """Append-only audit and SSE event stream for workflow progress."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id",
            "sequence_number",
            name="uq_workflow_events_run_sequence",
        ),
        CheckConstraint(
            "sequence_number >= 0",
            name="sequence_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
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
    workflow_run: Mapped[WorkflowRun] = relationship(
        "WorkflowRun",
        back_populates="events",
    )
