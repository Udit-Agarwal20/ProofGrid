"""Bounded retention that never removes artifacts referenced by preserved claims."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.evidence import Claim, RawDocument
from app.db.models.export import Export


async def retain_history(
    session: AsyncSession, now: datetime, raw_days: int, export_days: int, project_id: UUID
) -> dict[str, int]:
    rows = (
        await session.scalars(
            select(RawDocument)
            .where(
                RawDocument.project_id == project_id,
                RawDocument.retrieved_at < now - timedelta(days=raw_days),
                RawDocument.content.is_not(None),
                ~exists(select(Claim.id).where(Claim.raw_document_id == RawDocument.id)),
            )
            .with_for_update(skip_locked=True)
            .limit(100)
        )
    ).all()
    for row in rows:
        row.content = None
        row.retrieval_metadata = {
            **row.retrieval_metadata,
            "artifact_status": "EXPIRED_UNREFERENCED",
            "expired_at": now.isoformat(),
        }
    exports = (
        await session.scalars(
            select(Export)
            .where(
                Export.project_id == project_id,
                Export.created_at < now - timedelta(days=export_days),
            )
            .with_for_update(skip_locked=True)
            .limit(100)
        )
    ).all()
    for export in exports:
        await session.delete(export)
    # Export bytes are generated on demand; metadata is regeneratable from the immutable version.
    return {"unreferenced_artifacts_expired": len(rows), "export_manifests_expired": len(exports)}
