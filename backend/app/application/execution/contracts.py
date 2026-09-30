"""Persistence and execution interfaces; worker logic never owns ORM instances."""

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel

from app.domain.contracts import DatasetSchema, PlanDAG, RequirementSpec, TrustContract


class StepLease(BaseModel):
    step_id: UUID
    run_id: UUID
    project_id: UUID
    worker_id: str
    attempt: int
    node_id: str
    operator: str


class ExecutionContext(BaseModel):
    lease: StepLease
    requirement: RequirementSpec
    dataset_schema: DatasetSchema
    trust: TrustContract
    plan: PlanDAG
    mode: str
    started_at: datetime
    inputs: dict[str, Any]
    metrics: dict[str, Any]
    documents: list[dict[str, Any]] = []


class ExecutionStore(Protocol):
    async def reserve(self, lease: StepLease, resource: str, amount: int = 1) -> None: ...
    async def claim(self, worker_id: str) -> StepLease | None: ...
    async def context(self, lease: StepLease) -> ExecutionContext: ...
    async def heartbeat(self, lease: StepLease) -> bool: ...
    async def complete(self, lease: StepLease, output: dict[str, Any]) -> bool: ...
    async def fail(self, lease: StepLease, code: str, retryable: bool) -> None: ...
    async def recover(self) -> int: ...
