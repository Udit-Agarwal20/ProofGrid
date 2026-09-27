"""Claim ledger and evidence anchor persistence repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models.evidence import Claim, EvidenceAnchor
from app.persistence.repositories.base import BaseRepository


class ClaimRepository(BaseRepository):
    """Append-only persistence operations for the Claim Ledger and evidence anchors.

    Claims and evidence anchors represent immutable historical assertions and
    verifiable locators. This repository provides NO update or replacement methods.
    """

    # -------------------------------------------------------------------------
    # Claims (Append-Only Ledger)
    # -------------------------------------------------------------------------

    def add_claim(self, claim: Claim) -> Claim:
        """Append a new claim assertion to the Claim Ledger."""
        self._session.add(claim)
        return claim

    async def get_claim(self, claim_id: uuid.UUID) -> Claim | None:
        """Retrieve a single claim by its ID."""
        return await self._session.get(Claim, claim_id)

    async def list_claims_for_entity_field(
        self,
        project_id: uuid.UUID,
        entity_id: uuid.UUID,
        field_key: str,
        limit: int = 50,
    ) -> list[Claim]:
        """List all claims asserting values for a specific entity field."""
        stmt = (
            select(Claim)
            .where(
                Claim.project_id == project_id,
                Claim.entity_id == entity_id,
                Claim.field_key == field_key,
            )
            .order_by(Claim.created_at.asc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def list_claims_for_source(
        self,
        source_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Claim]:
        """List claims directly attributed to a source for source-centric ledger audits."""
        stmt = (
            select(Claim)
            .where(Claim.source_id == source_id)
            .order_by(Claim.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def list_claims_for_raw_document(
        self,
        raw_document_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Claim]:
        """List all claims extracted from a specific raw document snapshot."""
        stmt = (
            select(Claim)
            .where(Claim.raw_document_id == raw_document_id)
            .order_by(Claim.created_at.asc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def list_claims_for_run(
        self,
        workflow_run_id: uuid.UUID,
        limit: int = 100,
    ) -> list[Claim]:
        """List all claims produced during a specific workflow execution run."""
        stmt = (
            select(Claim)
            .where(Claim.workflow_run_id == workflow_run_id)
            .order_by(Claim.created_at.asc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Evidence Anchors (Deterministic Locators)
    # -------------------------------------------------------------------------

    def add_evidence_anchor(self, anchor: EvidenceAnchor) -> EvidenceAnchor:
        """Stage an evidence anchor linking a claim to a document locator."""
        self._session.add(anchor)
        return anchor

    async def get_evidence_anchor(self, anchor_id: uuid.UUID) -> EvidenceAnchor | None:
        """Retrieve an evidence anchor by its ID."""
        return await self._session.get(EvidenceAnchor, anchor_id)

    async def list_evidence_anchors_for_claim(
        self,
        claim_id: uuid.UUID,
    ) -> list[EvidenceAnchor]:
        """List all evidence anchors grounding a claim."""
        stmt = (
            select(EvidenceAnchor)
            .where(EvidenceAnchor.claim_id == claim_id)
            .order_by(EvidenceAnchor.created_at.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
