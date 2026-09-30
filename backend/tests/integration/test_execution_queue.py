"""Real PostgreSQL concurrency, lease fencing, retries, cancellation and outbox recovery."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.fixture_provider import FixtureProvider
from app.application.planning.service import fixture_plan
from app.application.requirement_compiler.models import CompilationContext, CompilerResult
from app.application.requirement_compiler.service import RequirementCompiler
from app.core.errors import ProofGridError
from app.db.models.outbox import OutboxEvent
from app.db.models.workflow import StepRun, WorkflowRun
from app.persistence.queries.outbox import OutboxDispatcher
from app.persistence.queries.queue import PostgresQueue
from app.persistence.repositories.workspace import WorkspaceRepository

pytestmark = pytest.mark.integration


async def test_durable_queue_and_outbox_invariants(
    isolated_db: async_sessionmaker[AsyncSession],
) -> None:
    project = uuid4()
    now = datetime.now(UTC) + timedelta(seconds=2)
    clock = lambda: now  # noqa: E731
    compiled = await RequirementCompiler(FixtureProvider()).compile(
        "Find Indian AI startups that raised more than $1M in the last 12 months.",
        context=CompilationContext(reference_date=now),
    )
    assert isinstance(compiled, CompilerResult)
    async with isolated_db() as session, session.begin():
        repo = WorkspaceRepository(session, project, now)
        req = await repo.save_compilation("Queue invariants", compiled)
        await session.flush()
        await repo.confirm(req, 1)
        _, schema, trust = await repo.requirement(req)
        plan = fixture_plan(compiled.requirement_spec, compiled.trust_contract_proposal)
        # Reverse order deliberately: dependency failure must still reach every descendant.
        plan = plan.model_copy(update={"nodes": list(reversed(plan.nodes))})
        saved = await repo.save_plan(req, schema.id, trust.id, plan, "fixture")
        workflow, version = saved.id, UUID(saved.data["workflow_version_id"])
        await session.flush()
        first = await repo.create_run(workflow, version, uuid4(), "FIXTURE", 3)
        second = await repo.create_run(workflow, version, uuid4(), "FIXTURE", 3)
    now = datetime.now(UTC) + timedelta(seconds=1)
    queue = PostgresQueue(isolated_db, project, clock=clock, lease_seconds=15)
    # A locked first run must not block another consumer from claiming the other run.
    async with isolated_db() as locked, locked.begin():
        await locked.scalar(select(WorkflowRun).where(WorkflowRun.id == first.id).with_for_update())
        lease2 = await asyncio.wait_for(queue.claim("worker-b"), timeout=20)
        assert lease2 is not None and lease2.run_id == second.id
    lease1 = await queue.claim("worker-a")
    assert lease1 is not None and lease1.run_id == first.id
    assert await queue.claim("worker-c") is None
    assert await queue.heartbeat(lease1)
    assert not await PostgresQueue(isolated_db, uuid4(), clock=clock).heartbeat(lease1)
    await queue.reserve(lease1, "pages", compiled.trust_contract_proposal.max_pages)
    with pytest.raises(ProofGridError, match="budget"):
        await queue.reserve(lease1, "pages")
    # Expired attempt cannot commit, even after another worker has reclaimed it.
    now += timedelta(seconds=16)
    assert not await queue.complete(lease1, {"urls": []})
    assert await queue.recover() == 2
    recovered = await queue.claim("worker-new")
    assert recovered and recovered.attempt == 2
    assert not await queue.complete(lease1, {"urls": ["https://forged.example"]})
    other_id = second.id if recovered.run_id == first.id else first.id
    active = await queue.claim("worker-cancel")
    assert active and active.run_id == other_id
    async with isolated_db() as session, session.begin():
        await WorkspaceRepository(session, project, now).run(other_id, cancel=True)
    assert not await queue.heartbeat(active)
    assert not await queue.complete(active, {"urls": []})
    await queue.recover()
    await queue.fail(recovered, "SOURCE_TIMEOUT", True)
    now += timedelta(seconds=31)
    await queue.recover()
    retry = await queue.claim("worker-retry")
    assert retry and retry.attempt == 3
    await queue.fail(retry, "SOURCE_TIMEOUT", True)
    async with isolated_db() as session:
        failed = await session.get(WorkflowRun, retry.run_id)
        assert failed and failed.status == "FAILED"
        steps = (
            await session.scalars(select(StepRun).where(StepRun.workflow_run_id == retry.run_id))
        ).all()
        assert all(s.status in {"FAILED", "SKIPPED"} for s in steps)
    async with isolated_db() as session:
        cancelled = await session.get(WorkflowRun, other_id)
        assert cancelled and cancelled.status == "CANCELLED"
    # Projection failure/retry never changes authoritative run state.
    async with isolated_db() as session, session.begin():
        event = OutboxEvent(
            project_id=project,
            aggregate_type="run",
            aggregate_id=other_id,
            event_type="test.projection",
            payload={"safe": True},
            available_at=now,
        )
        session.add(event)
        await session.flush()
        event_id = event.id
    attempts: list[UUID] = []

    async def handler(key: UUID, payload: dict[str, object]) -> None:
        attempts.append(key)
        if len(attempts) == 1:
            raise RuntimeError("secret must not be persisted")

    dispatcher = OutboxDispatcher(isolated_db, project, {"test.projection": handler}, clock)
    assert await dispatcher.tick()
    assert not await dispatcher.tick()
    now += timedelta(seconds=4)
    assert await dispatcher.tick()
    assert attempts == [event_id, event_id]
    async with isolated_db() as session:
        persisted = await session.get(OutboxEvent, event_id)
        assert persisted and persisted.status == "PUBLISHED" and persisted.attempt_count == 2
        cancelled = await session.get(WorkflowRun, other_id)
        assert cancelled and cancelled.status == "CANCELLED"
