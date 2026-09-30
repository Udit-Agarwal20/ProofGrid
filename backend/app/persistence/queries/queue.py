"""Transactional SKIP LOCKED queue, scoped by project and fenced by lease attempt."""

from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.execution.contracts import ExecutionContext, StepLease
from app.core.errors import ProofGridError
from app.db.models.evidence import RawDocument
from app.db.models.requirement import DatasetSchema, TrustContract
from app.db.models.workflow import StepRun, WorkflowEvent, WorkflowRun, WorkflowVersion
from app.domain.clock import Clock, utc_now
from app.domain.contracts import DatasetSchema as SchemaContract
from app.domain.contracts import PlanDAG, RequirementSpec
from app.domain.contracts import TrustContract as TrustPolicy
from app.domain.states import TERMINAL_RUNS, transition_run, transition_step


async def append_event(
    session: AsyncSession, run: WorkflowRun, event: str, payload: dict[str, Any]
) -> None:
    # Caller owns the run row lock; sequence allocation and state commit atomically.
    seq = await session.scalar(
        select(func.coalesce(func.max(WorkflowEvent.sequence_number), 0)).where(
            WorkflowEvent.workflow_run_id == run.id
        )
    )
    session.add(
        WorkflowEvent(
            workflow_run_id=run.id,
            sequence_number=int(seq or 0) + 1,
            event_type=event,
            payload=payload,
        )
    )
    await session.flush()


class PostgresQueue:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        project_id: UUID,
        *,
        clock: Clock = utc_now,
        lease_seconds: int = 60,
    ):
        self.sessions, self.project_id, self.clock, self.lease_seconds = (
            sessions,
            project_id,
            clock,
            lease_seconds,
        )

    async def reserve(self, lease: StepLease, resource: str, amount: int = 1) -> None:
        from decimal import Decimal

        async with self.sessions() as session, session.begin():
            owned = await self._owned(session, lease)
            if not owned or owned[1].status != "RUNNING":
                raise ProofGridError("RUN_CANCELLED", "Run no longer owns an active lease.")
            _, run = owned
            limits = run.budget_snapshot
            names = {
                "pages": "max_pages",
                "llm_calls": "max_llm_calls",
                "search_queries": "max_search_queries",
            }
            metrics = dict(run.metrics)
            used = int(metrics.get(resource, 0)) + amount
            elapsed = (self.clock() - (run.started_at or run.created_at)).total_seconds()
            cost = (
                Decimal(str(metrics.get("estimated_usd", "0")))
                + {
                    "pages": Decimal("0"),
                    "llm_calls": Decimal("0.10"),
                    "search_queries": Decimal("0.01"),
                }[resource]
                * amount
            )
            if (
                used > limits[names[resource]]
                or elapsed > limits["max_run_seconds"]
                or cost > Decimal(str(limits["max_estimated_cost_usd"]))
            ):
                raise ProofGridError(
                    "RUN_BUDGET_EXCEEDED", "Confirmed runtime budget is exhausted."
                )
            metrics[resource] = used
            metrics["estimated_usd"] = str(cost)
            run.metrics = metrics

    async def claim(self, worker_id: str) -> StepLease | None:
        async with self.sessions() as session, session.begin():
            # Always lock run before steps. This also serializes sequence allocation and
            # dependency advancement without deadlocking cancellation/recovery.
            run = await session.scalar(
                select(WorkflowRun)
                .where(
                    WorkflowRun.project_id == self.project_id,
                    WorkflowRun.status.in_(["QUEUED", "RUNNING"]),
                    select(StepRun.id)
                    .where(
                        StepRun.workflow_run_id == WorkflowRun.id,
                        StepRun.status == "READY",
                        StepRun.available_at <= self.clock(),
                    )
                    .exists(),
                )
                .order_by(WorkflowRun.created_at, WorkflowRun.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if run is None:
                return None
            step = await session.scalar(
                select(StepRun)
                .where(
                    StepRun.workflow_run_id == run.id,
                    StepRun.status == "READY",
                    StepRun.available_at <= self.clock(),
                )
                .order_by(StepRun.priority.desc(), StepRun.created_at, StepRun.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if step is None:
                return None
            if run.status == "QUEUED":
                run.status = transition_run(run.status, "RUNNING")
                run.started_at = self.clock()
                await append_event(
                    session,
                    run,
                    "run.state_changed",
                    {"status": run.status, "acquisition_mode": run.run_mode},
                )
            step.status = transition_step(step.status, "LEASED")
            step.worker_id = worker_id
            step.lease_expires_at = self.clock() + timedelta(seconds=self.lease_seconds)
            step.started_at = self.clock()
            step.status = transition_step(step.status, "RUNNING")
            await append_event(
                session,
                run,
                "step.started",
                {
                    "step_id": str(step.id),
                    "node_id": step.node_id,
                    "operator": step.operator_type,
                    "attempt": step.attempt,
                },
            )
            return StepLease(
                step_id=step.id,
                run_id=run.id,
                project_id=self.project_id,
                worker_id=worker_id,
                attempt=step.attempt,
                node_id=step.node_id,
                operator=step.operator_type,
            )

    async def _owned(
        self, session: AsyncSession, lease: StepLease
    ) -> tuple[StepRun, WorkflowRun] | None:
        run = await session.scalar(
            select(WorkflowRun)
            .where(WorkflowRun.id == lease.run_id, WorkflowRun.project_id == self.project_id)
            .with_for_update()
        )
        if run is None:
            return None
        step = await session.scalar(
            select(StepRun)
            .join(WorkflowRun)
            .where(StepRun.id == lease.step_id, WorkflowRun.project_id == self.project_id)
            .with_for_update(of=StepRun)
        )
        if (
            step is None
            or lease.project_id != self.project_id
            or step.workflow_run_id != lease.run_id
            or step.worker_id != lease.worker_id
            or step.attempt != lease.attempt
            or step.status != "RUNNING"
            or step.lease_expires_at is None
            or step.lease_expires_at <= self.clock()
        ):
            return None
        return step, run

    async def heartbeat(self, lease: StepLease) -> bool:
        async with self.sessions() as session, session.begin():
            owned = await self._owned(session, lease)
            if not owned or owned[1].status != "RUNNING":
                return False
            owned[0].lease_expires_at = self.clock() + timedelta(seconds=self.lease_seconds)
            return True

    async def context(self, lease: StepLease) -> ExecutionContext:
        async with self.sessions() as session:
            run = await session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.id == lease.run_id, WorkflowRun.project_id == self.project_id
                )
            )
            if run is None:
                raise ProofGridError("NOT_FOUND", "Run not found.", status=404)
            version = await session.get(WorkflowVersion, run.workflow_version_id)
            assert version is not None
            schema = await session.scalar(
                select(DatasetSchema).where(
                    DatasetSchema.id == version.dataset_schema_id,
                    DatasetSchema.project_id == self.project_id,
                )
            )
            trust = await session.scalar(
                select(TrustContract).where(
                    TrustContract.id == version.trust_contract_id,
                    TrustContract.project_id == self.project_id,
                )
            )
            assert schema and trust
            plan = PlanDAG.model_validate(version.plan_dag)
            node = next(n for n in plan.nodes if n.id == lease.node_id)
            parents = list(
                (
                    await session.scalars(
                        select(StepRun).where(
                            StepRun.workflow_run_id == run.id, StepRun.node_id.in_(node.depends_on)
                        )
                    )
                ).all()
            )
            inputs: dict[str, Any] = {}
            for parent in parents:
                for key, value in parent.output.items():
                    if isinstance(value, list):
                        inputs.setdefault(key, []).extend(value)
                    else:
                        inputs[key] = value
            docs = []
            if lease.operator in {"EXTRACT", "VALIDATE"}:
                docs = list(
                    (
                        await session.scalars(
                            select(RawDocument)
                            .where(
                                RawDocument.project_id == self.project_id,
                                RawDocument.workflow_run_id == run.id,
                            )
                            .limit(500)
                        )
                    ).all()
                )
            return ExecutionContext(
                lease=lease,
                requirement=RequirementSpec.model_validate(
                    version.planner_metadata["requirement_snapshot"]
                ),
                dataset_schema=SchemaContract.model_validate(schema.schema_definition),
                trust=TrustPolicy.model_validate(trust.contract_definition),
                plan=plan,
                mode=run.run_mode,
                started_at=run.started_at or run.created_at,
                inputs=inputs,
                metrics=run.metrics,
                documents=[
                    {
                        "id": str(d.id),
                        "source_id": str(d.source_id),
                        "content": d.content or "",
                        "content_type": d.mime_type or "text/plain",
                        "url": d.final_url,
                        "metadata": d.retrieval_metadata,
                    }
                    for d in docs
                ],
            )

    async def complete(self, lease: StepLease, output: dict[str, Any]) -> bool:
        from app.persistence.queries.pipeline import persist_operator_output

        async with self.sessions() as session, session.begin():
            owned = await self._owned(session, lease)
            if owned is None:
                return False
            step, run = owned
            if run.status != "RUNNING":
                return False
            output = await persist_operator_output(session, run, step, output, self.clock())
            step.output = output
            step.status = transition_step(step.status, "SUCCEEDED")
            step.finished_at = self.clock()
            step.lease_expires_at = None
            metrics = dict(run.metrics)
            for key, value in output.get("metrics", {}).items():
                metrics[key] = value
            run.metrics = metrics
            await append_event(
                session,
                run,
                "step.progress",
                {
                    "step_id": str(step.id),
                    "node_id": step.node_id,
                    "status": step.status,
                    "metrics": output.get("metrics", {}),
                },
            )
            await self._advance(session, run)
            return True

    async def _advance(self, session: AsyncSession, run: WorkflowRun) -> None:
        version = await session.get(WorkflowVersion, run.workflow_version_id)
        assert version
        plan = PlanDAG.model_validate(version.plan_dag)
        steps = list(
            (
                await session.scalars(
                    select(StepRun)
                    .where(StepRun.workflow_run_id == run.id)
                    .order_by(StepRun.created_at)
                )
            ).all()
        )
        by_node = {s.node_id: s for s in steps}
        if run.status == "CANCEL_REQUESTED":
            for step in steps:
                if step.status not in {"SUCCEEDED", "FAILED", "SKIPPED", "CANCELLED"}:
                    step.status = transition_step(step.status, "CANCELLED")
                    step.lease_expires_at = None
            run.status = transition_run(run.status, "CANCELLED")
        else:
            # Plans may be valid DAGs without being listed in topological order.
            # Iterate to a fixed point so failure propagates through every descendant.
            for _ in range(len(plan.nodes)):
                changed = False
                for node in plan.nodes:
                    step = by_node[node.id]
                    if step.status == "PENDING":
                        parents = [by_node[key] for key in node.depends_on]
                        if any(s.status in {"FAILED", "SKIPPED", "CANCELLED"} for s in parents):
                            step.status = transition_step(step.status, "SKIPPED")
                            changed = True
                        elif all(s.status == "SUCCEEDED" for s in parents):
                            step.status = transition_step(step.status, "READY")
                            changed = True
                if not changed:
                    break
            if all(s.status in {"SUCCEEDED", "FAILED", "SKIPPED", "CANCELLED"} for s in steps):
                has_dataset = bool(run.metrics.get("dataset_version_id"))
                degraded = bool(
                    run.metrics.get("source_errors")
                    or run.metrics.get("quality_incomplete")
                    or any(s.status != "SUCCEEDED" for s in steps)
                )
                target = (
                    "PARTIAL"
                    if has_dataset and degraded and run.metrics.get("records", 0) > 0
                    else "COMPLETED"
                    if has_dataset and not degraded
                    else "FAILED"
                )
                run.status = transition_run(run.status, target)
        if run.status in TERMINAL_RUNS:
            run.finished_at = self.clock()
            await append_event(
                session, run, "run.completed", {"status": run.status, "metrics": run.metrics}
            )

    async def fail(self, lease: StepLease, code: str, retryable: bool) -> None:
        async with self.sessions() as session, session.begin():
            owned = await self._owned(session, lease)
            if not owned:
                return
            step, run = owned
            version = await session.get(WorkflowVersion, run.workflow_version_id)
            assert version
            plan = PlanDAG.model_validate(version.plan_dag)
            node = next(n for n in plan.nodes if n.id == step.node_id)
            step.error_code = code
            step.lease_expires_at = None
            if (
                retryable
                and step.attempt <= node.constraints.max_retries
                and run.status == "RUNNING"
            ):
                step.status = transition_step(step.status, "RETRY_WAIT")
                step.attempt += 1
                step.available_at = self.clock() + timedelta(seconds=min(2**step.attempt, 30))
                await append_event(
                    session,
                    run,
                    "step.retry_scheduled",
                    {
                        "node_id": step.node_id,
                        "code": code,
                        "attempt": step.attempt,
                        "available_at": step.available_at.isoformat(),
                    },
                )
            else:
                step.status = transition_step(step.status, "FAILED")
                await append_event(
                    session, run, "step.failed", {"node_id": step.node_id, "code": code}
                )
                await self._advance(session, run)

    async def recover(self) -> int:
        count = 0
        async with self.sessions() as session, session.begin():
            runs = list(
                (
                    await session.scalars(
                        select(WorkflowRun)
                        .where(
                            WorkflowRun.project_id == self.project_id,
                            WorkflowRun.status.in_(["RUNNING", "CANCEL_REQUESTED"]),
                        )
                        .order_by(WorkflowRun.id)
                        .with_for_update(skip_locked=True)
                        .limit(100)
                    )
                ).all()
            )
            for run in runs:
                if run.status == "CANCEL_REQUESTED":
                    await self._advance(session, run)
                    continue
                version = await session.get(WorkflowVersion, run.workflow_version_id)
                assert version
                nodes = {n.id: n for n in PlanDAG.model_validate(version.plan_dag).nodes}
                steps = list(
                    (
                        await session.scalars(
                            select(StepRun)
                            .where(
                                StepRun.workflow_run_id == run.id,
                                StepRun.status.in_(["LEASED", "RUNNING", "RETRY_WAIT"]),
                            )
                            .with_for_update()
                        )
                    ).all()
                )
                for step in steps:
                    expired = (
                        step.status in {"LEASED", "RUNNING"}
                        and step.lease_expires_at is not None
                        and step.lease_expires_at <= self.clock()
                    )
                    if expired:
                        step.status = transition_step(
                            step.status,
                            "RETRY_WAIT"
                            if step.attempt <= nodes[step.node_id].constraints.max_retries
                            else "FAILED",
                        )
                        step.attempt += 1
                        step.worker_id = None
                        step.lease_expires_at = None
                        step.available_at = self.clock()
                        step.error_code = "LEASE_EXPIRED"
                        count += 1
                    if step.status == "RETRY_WAIT" and step.available_at <= self.clock():
                        step.status = transition_step(step.status, "READY")
                    if expired:
                        await append_event(
                            session,
                            run,
                            "step.recovered",
                            {
                                "node_id": step.node_id,
                                "status": step.status,
                                "attempt": step.attempt,
                            },
                        )
                await self._advance(session, run)
        return count
