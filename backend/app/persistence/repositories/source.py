"""Source and raw document provenance persistence repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models.evidence import RawDocument, Source
from app.persistence.repositories.base import BaseRepository


class SourceRepository(BaseRepository):
    """Persistence operations for external sources and immutable retrieval snapshots."""

    # -------------------------------------------------------------------------
    # Sources (Logical Origin)
    # -------------------------------------------------------------------------

    def add_source(self, source: Source) -> Source:
        """Stage a logical source for insertion."""
        self._session.add(source)
        return source

    async def get_source(self, source_id: uuid.UUID) -> Source | None:
        """Retrieve a source by its ID."""
        return await self._session.get(Source, source_id)

    async def get_source_by_canonical_url(
        self,
        project_id: uuid.UUID,
        canonical_url: str,
    ) -> Source | None:
        """Retrieve a source by its tenant-scoped canonical URL."""
        stmt = select(Source).where(
            Source.project_id == project_id,
            Source.canonical_url == canonical_url,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_sources_for_project(
        self,
        project_id: uuid.UUID,
        domain: str | None = None,
        limit: int = 50,
    ) -> list[Source]:
        """List sources for a project optionally filtered by domain."""
        stmt = select(Source).where(Source.project_id == project_id)
        if domain is not None:
            stmt = stmt.where(Source.domain == domain)
        stmt = stmt.order_by(Source.created_at.desc()).limit(limit)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Raw Documents (Immutable Content-Addressed Retrieval Snapshots)
    # -------------------------------------------------------------------------

    def add_raw_document(self, raw_document: RawDocument) -> RawDocument:
        """Stage an immutable retrieval snapshot for insertion.

        Note: Identical content_hash from different sources or acquisition events
        must NOT be suppressed. Each retrieval is an independent provenance record.
        """
        self._session.add(raw_document)
        return raw_document

    async def get_raw_document(self, document_id: uuid.UUID) -> RawDocument | None:
        """Retrieve a raw document by its ID."""
        return await self._session.get(RawDocument, document_id)

    async def list_raw_documents_for_source(
        self,
        source_id: uuid.UUID,
        limit: int = 50,
    ) -> list[RawDocument]:
        """List historical retrieval snapshots for a source ordered by retrieval time."""
        stmt = (
            select(RawDocument)
            .where(RawDocument.source_id == source_id)
            .order_by(RawDocument.retrieved_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def find_by_content_hash(
        self,
        project_id: uuid.UUID,
        content_hash: str,
        limit: int = 10,
    ) -> list[RawDocument]:
        """Find existing retrieval snapshots with the same content hash for diagnostics or caching.

        Does not suppress the insertion of new independent raw document rows.
        """
        stmt = (
            select(RawDocument)
            .where(
                RawDocument.project_id == project_id,
                RawDocument.content_hash == content_hash,
            )
            .order_by(RawDocument.retrieved_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
