"""Evidence, source, raw document, claim ledger, and anchor models."""

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
    from app.db.models.entity import Entity
    from app.db.models.project import Project
    from app.db.models.workflow import WorkflowRun


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Source(Base):
    """Logical external source representation."""

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("project_id", "canonical_url", name="uq_sources_project_canonical_url"),
        CheckConstraint(
            "source_type IN ('WEB_PAGE', 'API', 'RSS', 'DOCUMENT', 'FIXTURE')",
            name="source_type",
        ),
        Index("ix_sources_project_domain", "project_id", "domain"),
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
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="WEB_PAGE")
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
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
    project: Mapped[Project] = relationship("Project", back_populates="sources")
    raw_documents: Mapped[list[RawDocument]] = relationship(
        "RawDocument",
        back_populates="source",
    )
    claims: Mapped[list[Claim]] = relationship(
        "Claim",
        back_populates="source",
    )


class RawDocument(Base):
    """Immutable retrieval snapshot metadata for acquired content."""

    __tablename__ = "raw_documents"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id", "source_id", "content_hash", name="uq_raw_document_observation"
        ),
        CheckConstraint("size_bytes >= 0", name="size_bytes"),
        Index("ix_raw_documents_project_content_hash", "project_id", "content_hash"),
        Index("ix_raw_documents_source_id", "source_id"),
        Index("ix_raw_documents_workflow_run_id", "workflow_run_id"),
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
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    final_url: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieval_metadata: Mapped[dict[str, Any]] = mapped_column(
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
    workflow_run: Mapped[WorkflowRun | None] = relationship(
        "WorkflowRun",
        back_populates="raw_documents",
    )
    source: Mapped[Source] = relationship("Source", back_populates="raw_documents")
    claims: Mapped[list[Claim]] = relationship(
        "Claim",
        back_populates="raw_document",
    )
    evidence_anchors: Mapped[list[EvidenceAnchor]] = relationship(
        "EvidenceAnchor",
        back_populates="raw_document",
    )


class Claim(Base):
    """Core Claim Ledger table: append-only source assertions about entity fields."""

    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "claim_hash", name="uq_claims_run_hash"),
        Index("ix_claims_project_id", "project_id"),
        Index("ix_claims_entity_field", "entity_id", "field_key"),
        Index("ix_claims_raw_document_id", "raw_document_id"),
        Index("ix_claims_source_id", "source_id"),
        Index("ix_claims_workflow_run_id", "workflow_run_id"),
        Index("ix_claims_claim_hash", "claim_hash"),
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
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    raw_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="RESTRICT"),
        nullable=True,
    )
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    normalized_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    extraction_method: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="deterministic",
    )
    validation_flags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    claim_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    # Relationships
    project: Mapped[Project] = relationship("Project")
    workflow_run: Mapped[WorkflowRun] = relationship(
        "WorkflowRun",
        back_populates="claims",
    )
    raw_document: Mapped[RawDocument] = relationship(
        "RawDocument",
        back_populates="claims",
    )
    source: Mapped[Source] = relationship("Source", back_populates="claims")
    entity: Mapped[Entity | None] = relationship("Entity", back_populates="claims")
    evidence_anchors: Mapped[list[EvidenceAnchor]] = relationship(
        "EvidenceAnchor",
        back_populates="claim",
    )


class EvidenceAnchor(Base):
    """Deterministic anchor linking a claim to its stored RawDocument representation."""

    __tablename__ = "evidence_anchors"
    __table_args__ = (
        CheckConstraint(
            "anchor_type IN ('TEXT_SPAN', 'NORMALIZED_TEXT_SPAN', 'JSON_POINTER', 'DOM_SELECTOR', 'STRUCTURED_FIELD', 'API_RESPONSE_POINTER')",
            name="type",
        ),
        CheckConstraint(
            "verification_status IN ('UNVERIFIED', 'EXACT', 'NORMALIZED', 'JSON_POINTER', 'DOM_SELECTOR', 'UNANCHORED', 'VERIFIED', 'FAILED')",
            name="status",
        ),
        Index("ix_evidence_anchors_claim_id", "claim_id"),
        Index("ix_evidence_anchors_raw_document_id", "raw_document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
    )
    raw_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    anchor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    locator: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    quoted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="UNVERIFIED",
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    # Relationships
    claim: Mapped[Claim] = relationship("Claim", back_populates="evidence_anchors")
    raw_document: Mapped[RawDocument] = relationship(
        "RawDocument",
        back_populates="evidence_anchors",
    )
