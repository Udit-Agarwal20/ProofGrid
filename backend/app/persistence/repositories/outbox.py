"""Transactional outbox persistence repository."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.db.models.outbox import OutboxEvent
from app.persistence.repositories.base import BaseRepository


@dataclass(frozen=True)
class OutboxEventCreate:
    """Typed application input for enqueuing a transactional outbox event."""

    aggregate_type: str
    aggregate_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    project_id: uuid.UUID | None = None
    status: str = "PENDING"
    attempt_count: int = 0
    available_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class OutboxRepository(BaseRepository):
    """Persistence operations for the transactional outbox ledger.

    Responsible solely for transactional enqueueing alongside business entity writes.
    Queue consumption, polling, row claiming, leases, and worker dispatch are deferred
    to Phase 5 — Workflow Execution.
    """

    def enqueue(self, event: OutboxEventCreate | OutboxEvent) -> OutboxEvent:
        """Enqueue an outbox event atomically within the current Unit of Work."""
        if isinstance(event, OutboxEvent):
            model = event
        else:
            model = OutboxEvent(
                project_id=event.project_id,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
                payload=event.payload,
                status=event.status,
                attempt_count=event.attempt_count,
                available_at=event.available_at,
            )
        self._session.add(model)
        return model

    async def get_by_id(self, event_id: uuid.UUID) -> OutboxEvent | None:
        """Retrieve an outbox event by its primary key ID."""
        return await self._session.get(OutboxEvent, event_id)

    async def list_by_status(
        self,
        status: str = "PENDING",
        limit: int = 50,
        offset: int = 0,
    ) -> list[OutboxEvent]:
        """Administrative read-only query to inspect outbox events by status with bounded pagination.

        NOTE: This is a purely passive read query for administrative and diagnostic inspection.
        It does NOT lock rows, claim tasks, mutate state, or implement queue consumption.
        Queue consumption, polling, row claiming, leases, and worker dispatch are deferred
        to Phase 5 — Workflow Execution.
        """
        bounded_limit = max(1, min(limit, 100))
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == status)
            .order_by(OutboxEvent.created_at.asc())
            .offset(offset)
            .limit(bounded_limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
