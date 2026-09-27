"""Dataset, dataset versioning, canonical values, conflicts, and records repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models.dataset import (
    CanonicalValue,
    Conflict,
    Dataset,
    DatasetVersion,
    DatasetVersionRecord,
)
from app.persistence.repositories.base import BaseRepository


class DatasetRepository(BaseRepository):
    """Persistence operations for datasets, historical versions, canonical fields, and read models."""

    # -------------------------------------------------------------------------
    # Datasets (Stable Logical Identity)
    # -------------------------------------------------------------------------

    def add_dataset(self, dataset: Dataset) -> Dataset:
        """Stage a stable logical dataset identity for insertion."""
        self._session.add(dataset)
        return dataset

    async def get_dataset(self, dataset_id: uuid.UUID) -> Dataset | None:
        """Retrieve a dataset by its ID."""
        return await self._session.get(Dataset, dataset_id)

    async def get_by_slug(self, project_id: uuid.UUID, slug: str) -> Dataset | None:
        """Retrieve a dataset by tenant-scoped slug."""
        stmt = select(Dataset).where(
            Dataset.project_id == project_id,
            Dataset.slug == slug,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_datasets_for_project(
        self,
        project_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Dataset]:
        """List datasets for a project ordered by creation time."""
        stmt = (
            select(Dataset)
            .where(Dataset.project_id == project_id)
            .order_by(Dataset.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Dataset Versions (Immutable Historical Snapshots)
    # -------------------------------------------------------------------------

    def add_dataset_version(self, version: DatasetVersion) -> DatasetVersion:
        """Stage an immutable dataset version snapshot for insertion."""
        self._session.add(version)
        return version

    async def get_dataset_version(self, version_id: uuid.UUID) -> DatasetVersion | None:
        """Retrieve a dataset version by its ID."""
        return await self._session.get(DatasetVersion, version_id)

    async def get_dataset_version_by_number(
        self,
        dataset_id: uuid.UUID,
        version_number: int,
    ) -> DatasetVersion | None:
        """Retrieve an exact dataset version by version number."""
        stmt = select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.version_number == version_number,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_latest_dataset_version(
        self,
        dataset_id: uuid.UUID,
    ) -> DatasetVersion | None:
        """Retrieve the highest version number snapshot for a dataset."""
        stmt = (
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number.desc())
            .limit(1)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_dataset_versions(
        self,
        dataset_id: uuid.UUID,
    ) -> list[DatasetVersion]:
        """List all historical versions of a dataset ordered by version number."""
        stmt = (
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Canonical Values (Version-Scoped Field Truth)
    # -------------------------------------------------------------------------

    def add_canonical_value(self, canonical_value: CanonicalValue) -> CanonicalValue:
        """Stage a version-scoped canonical field value for insertion."""
        self._session.add(canonical_value)
        return canonical_value

    async def get_canonical_value(
        self,
        dataset_version_id: uuid.UUID,
        entity_id: uuid.UUID,
        field_key: str,
    ) -> CanonicalValue | None:
        """Retrieve a canonical value for a specific dataset version, entity, and field."""
        stmt = select(CanonicalValue).where(
            CanonicalValue.dataset_version_id == dataset_version_id,
            CanonicalValue.entity_id == entity_id,
            CanonicalValue.field_key == field_key,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_canonical_values(
        self,
        dataset_version_id: uuid.UUID,
        entity_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[CanonicalValue]:
        """List canonical values for a dataset version, optionally filtered by entity."""
        stmt = select(CanonicalValue).where(CanonicalValue.dataset_version_id == dataset_version_id)
        if entity_id is not None:
            stmt = stmt.where(CanonicalValue.entity_id == entity_id)
        stmt = stmt.order_by(CanonicalValue.field_key.asc()).limit(limit)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Conflicts (Version-Scoped Disagreements)
    # -------------------------------------------------------------------------

    def add_conflict(self, conflict: Conflict) -> Conflict:
        """Stage a version-scoped field conflict for insertion."""
        self._session.add(conflict)
        return conflict

    async def get_conflict(
        self,
        dataset_version_id: uuid.UUID,
        entity_id: uuid.UUID,
        field_key: str,
    ) -> Conflict | None:
        """Retrieve a field conflict for a specific version, entity, and field."""
        stmt = select(Conflict).where(
            Conflict.dataset_version_id == dataset_version_id,
            Conflict.entity_id == entity_id,
            Conflict.field_key == field_key,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_conflicts(
        self,
        dataset_version_id: uuid.UUID,
        entity_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[Conflict]:
        """List conflicts for a dataset version, optionally filtered by entity."""
        stmt = select(Conflict).where(Conflict.dataset_version_id == dataset_version_id)
        if entity_id is not None:
            stmt = stmt.where(Conflict.entity_id == entity_id)
        stmt = stmt.order_by(Conflict.field_key.asc()).limit(limit)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Dataset Version Records (Materialized Denormalized Read Model)
    # -------------------------------------------------------------------------

    def add_dataset_version_record(
        self,
        record: DatasetVersionRecord,
    ) -> DatasetVersionRecord:
        """Stage a materialized record for insertion into a dataset version."""
        self._session.add(record)
        return record

    async def get_dataset_version_record(
        self,
        dataset_version_id: uuid.UUID,
        entity_id: uuid.UUID,
    ) -> DatasetVersionRecord | None:
        """Retrieve a single materialized record by dataset version and entity ID."""
        stmt = select(DatasetVersionRecord).where(
            DatasetVersionRecord.dataset_version_id == dataset_version_id,
            DatasetVersionRecord.entity_id == entity_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_dataset_version_records(
        self,
        dataset_version_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DatasetVersionRecord]:
        """List materialized records for a dataset version with deterministic pagination."""
        stmt = (
            select(DatasetVersionRecord)
            .where(DatasetVersionRecord.dataset_version_id == dataset_version_id)
            .order_by(DatasetVersionRecord.entity_id.asc())
            .offset(offset)
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
