"""Workflow execution and orchestration persistence repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models.workflow import (
    StepRun,
    Workflow,
    WorkflowEvent,
    WorkflowRun,
    WorkflowVersion,
)
from app.persistence.repositories.base import BaseRepository


class WorkflowRepository(BaseRepository):
    """Persistence operations for workflows, versioned DAGs, runs, steps, and audit events."""

    # -------------------------------------------------------------------------
    # Workflows (Logical Identity)
    # -------------------------------------------------------------------------

    def add_workflow(self, workflow: Workflow) -> Workflow:
        """Stage a new workflow for insertion."""
        self._session.add(workflow)
        return workflow

    async def get_workflow(self, workflow_id: uuid.UUID) -> Workflow | None:
        """Retrieve a workflow by its ID."""
        return await self._session.get(Workflow, workflow_id)

    async def list_workflows_for_project(
        self,
        project_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Workflow]:
        """List workflows for a project ordered by creation time."""
        stmt = (
            select(Workflow)
            .where(Workflow.project_id == project_id)
            .order_by(Workflow.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Workflow Versions (Immutable PlanDAG Snapshots)
    # -------------------------------------------------------------------------

    def add_workflow_version(self, version: WorkflowVersion) -> WorkflowVersion:
        """Stage an immutable compiled execution plan snapshot for insertion."""
        self._session.add(version)
        return version

    async def get_workflow_version(self, version_id: uuid.UUID) -> WorkflowVersion | None:
        """Retrieve a workflow version by its ID."""
        return await self._session.get(WorkflowVersion, version_id)

    async def get_workflow_version_by_number(
        self,
        workflow_id: uuid.UUID,
        version_number: int,
    ) -> WorkflowVersion | None:
        """Retrieve an exact workflow version by version number."""
        stmt = select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow_id,
            WorkflowVersion.version_number == version_number,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_latest_workflow_version(
        self,
        workflow_id: uuid.UUID,
    ) -> WorkflowVersion | None:
        """Retrieve the highest version number compiled plan for a workflow."""
        stmt = (
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version_number.desc())
            .limit(1)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_workflow_versions(
        self,
        workflow_id: uuid.UUID,
    ) -> list[WorkflowVersion]:
        """List all historical workflow versions ordered by version number."""
        stmt = (
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version_number.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Workflow Runs
    # -------------------------------------------------------------------------

    def add_workflow_run(self, run: WorkflowRun) -> WorkflowRun:
        """Stage a concrete workflow execution run for insertion."""
        self._session.add(run)
        return run

    async def get_workflow_run(self, run_id: uuid.UUID) -> WorkflowRun | None:
        """Retrieve a workflow run by its ID."""
        return await self._session.get(WorkflowRun, run_id)

    async def list_workflow_runs_for_version(
        self,
        version_id: uuid.UUID,
        limit: int = 50,
    ) -> list[WorkflowRun]:
        """List runs for a workflow version ordered by creation time descending."""
        stmt = (
            select(WorkflowRun)
            .where(WorkflowRun.workflow_version_id == version_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Step Runs
    # -------------------------------------------------------------------------

    def add_step_run(self, step: StepRun) -> StepRun:
        """Stage a node execution attempt for insertion."""
        self._session.add(step)
        return step

    async def get_step_run(self, step_id: uuid.UUID) -> StepRun | None:
        """Retrieve a step run by its ID."""
        return await self._session.get(StepRun, step_id)

    async def get_step_run_by_node(
        self,
        workflow_run_id: uuid.UUID,
        node_id: str,
        attempt: int = 1,
    ) -> StepRun | None:
        """Retrieve a specific node attempt within a run."""
        stmt = select(StepRun).where(
            StepRun.workflow_run_id == workflow_run_id,
            StepRun.node_id == node_id,
            StepRun.attempt == attempt,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_step_runs_for_run(
        self,
        workflow_run_id: uuid.UUID,
    ) -> list[StepRun]:
        """List all step execution attempts for a run."""
        stmt = (
            select(StepRun)
            .where(StepRun.workflow_run_id == workflow_run_id)
            .order_by(StepRun.created_at.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Workflow Events (Append-Only Audit Stream)
    # -------------------------------------------------------------------------

    def add_workflow_event(self, event: WorkflowEvent) -> WorkflowEvent:
        """Stage an append-only SSE/audit event for insertion."""
        self._session.add(event)
        return event

    async def list_workflow_events(
        self,
        workflow_run_id: uuid.UUID,
        after_sequence: int | None = None,
        limit: int = 100,
    ) -> list[WorkflowEvent]:
        """List workflow events in ascending sequence order for replay or audit."""
        stmt = select(WorkflowEvent).where(WorkflowEvent.workflow_run_id == workflow_run_id)
        if after_sequence is not None:
            stmt = stmt.where(WorkflowEvent.sequence_number > after_sequence)
        stmt = stmt.order_by(WorkflowEvent.sequence_number.asc()).limit(limit)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
