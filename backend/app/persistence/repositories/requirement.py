"""Requirement, schema contract, and trust contract repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models.requirement import DatasetSchema, Requirement, TrustContract
from app.persistence.repositories.base import BaseRepository


class RequirementRepository(BaseRepository):
    """Persistence operations for requirements, versioned schemas, and trust contracts."""

    # -------------------------------------------------------------------------
    # Requirements
    # -------------------------------------------------------------------------

    def add_requirement(self, requirement: Requirement) -> Requirement:
        """Stage a requirement specification for insertion."""
        self._session.add(requirement)
        return requirement

    async def get_requirement(self, requirement_id: uuid.UUID) -> Requirement | None:
        """Retrieve a requirement by its ID."""
        return await self._session.get(Requirement, requirement_id)

    async def list_requirements_for_project(
        self,
        project_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Requirement]:
        """List requirements for a project ordered by creation time descending."""
        stmt = (
            select(Requirement)
            .where(Requirement.project_id == project_id)
            .order_by(Requirement.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Dataset Schemas (Immutable Versioned Contracts)
    # -------------------------------------------------------------------------

    def add_dataset_schema(self, schema: DatasetSchema) -> DatasetSchema:
        """Stage an immutable dataset schema version for insertion."""
        self._session.add(schema)
        return schema

    async def get_dataset_schema(self, schema_id: uuid.UUID) -> DatasetSchema | None:
        """Retrieve a dataset schema by its ID."""
        return await self._session.get(DatasetSchema, schema_id)

    async def get_dataset_schema_by_version(
        self,
        requirement_id: uuid.UUID,
        version_number: int,
    ) -> DatasetSchema | None:
        """Retrieve an exact dataset schema version for a requirement."""
        stmt = select(DatasetSchema).where(
            DatasetSchema.requirement_id == requirement_id,
            DatasetSchema.version_number == version_number,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_latest_dataset_schema(
        self,
        requirement_id: uuid.UUID,
    ) -> DatasetSchema | None:
        """Retrieve the highest version number dataset schema for a requirement."""
        stmt = (
            select(DatasetSchema)
            .where(DatasetSchema.requirement_id == requirement_id)
            .order_by(DatasetSchema.version_number.desc())
            .limit(1)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_dataset_schemas(
        self,
        requirement_id: uuid.UUID,
    ) -> list[DatasetSchema]:
        """List all historical schema versions for a requirement ordered by version."""
        stmt = (
            select(DatasetSchema)
            .where(DatasetSchema.requirement_id == requirement_id)
            .order_by(DatasetSchema.version_number.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Trust Contracts (Immutable Quality & Budget Policies)
    # -------------------------------------------------------------------------

    def add_trust_contract(self, contract: TrustContract) -> TrustContract:
        """Stage an immutable trust contract version for insertion."""
        self._session.add(contract)
        return contract

    async def get_trust_contract(self, contract_id: uuid.UUID) -> TrustContract | None:
        """Retrieve a trust contract by its ID."""
        return await self._session.get(TrustContract, contract_id)

    async def get_trust_contract_by_version(
        self,
        requirement_id: uuid.UUID,
        version_number: int,
    ) -> TrustContract | None:
        """Retrieve an exact trust contract version for a requirement."""
        stmt = select(TrustContract).where(
            TrustContract.requirement_id == requirement_id,
            TrustContract.version_number == version_number,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_latest_trust_contract(
        self,
        requirement_id: uuid.UUID,
    ) -> TrustContract | None:
        """Retrieve the highest version number trust contract for a requirement."""
        stmt = (
            select(TrustContract)
            .where(TrustContract.requirement_id == requirement_id)
            .order_by(TrustContract.version_number.desc())
            .limit(1)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_trust_contracts(
        self,
        requirement_id: uuid.UUID,
    ) -> list[TrustContract]:
        """List all historical trust contracts for a requirement ordered by version."""
        stmt = (
            select(TrustContract)
            .where(TrustContract.requirement_id == requirement_id)
            .order_by(TrustContract.version_number.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
