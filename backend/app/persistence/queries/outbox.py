"""At-least-once projection dispatch after authoritative transactions commit."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.outbox import OutboxEvent
from app.domain.clock import Clock, utc_now

Handler = Callable[[UUID, dict[str, Any]], Awaitable[None]]


class OutboxDispatcher:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        project_id: UUID,
        handlers: dict[str, Handler],
        clock: Clock = utc_now,
    ):
        self.sessions, self.project_id, self.handlers, self.clock = (
            sessions,
            project_id,
            handlers,
            clock,
        )

    async def tick(self) -> bool:
        if not self.handlers:
            return False
        async with self.sessions() as session, session.begin():
            event = await session.scalar(
                select(OutboxEvent)
                .where(
                    OutboxEvent.project_id == self.project_id,
                    OutboxEvent.event_type.in_(self.handlers),
                    OutboxEvent.available_at <= self.clock(),
                    or_(
                        OutboxEvent.status.in_(["PENDING", "FAILED"]),
                        OutboxEvent.status == "PROCESSING",
                    ),
                )
                .order_by(OutboxEvent.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if event is None:
                return False
            event.status = "PROCESSING"
            event.attempt_count += 1
            event.available_at = self.clock() + timedelta(seconds=60)
            event_id, attempt, event_type, payload = (
                event.id,
                event.attempt_count,
                event.event_type,
                event.payload,
            )
        # No database transaction is held during remote effects. Handler must use event_id as its idempotency key.
        failed = False
        try:
            await self.handlers[event_type](event_id, payload)
        except Exception:
            failed = True
        async with self.sessions() as session, session.begin():
            event = await session.scalar(
                select(OutboxEvent)
                .where(OutboxEvent.id == event_id, OutboxEvent.project_id == self.project_id)
                .with_for_update()
            )
            if event is None or event.attempt_count != attempt or event.status != "PROCESSING":
                return True
            if failed:
                event.status = "DEAD_LETTER" if attempt >= 5 else "FAILED"
                event.last_error = "PROJECTION_DISPATCH_FAILED"
                event.available_at = self.clock() + timedelta(seconds=min(2**attempt, 300))
            else:
                event.status = "PUBLISHED"
                event.processed_at = self.clock()
                event.last_error = None
        return True
