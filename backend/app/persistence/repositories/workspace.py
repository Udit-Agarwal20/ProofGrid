"""Project-scoped product repository. One caller-owned transaction per operation."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import Numeric, String, and_, cast, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.application.planning.service import validate_plan, validate_requirement, validate_trust
from app.application.requirement_compiler.models import CompilerResult
from app.application.requirement_compiler.validation import _compute_schema_hash
from app.core.errors import ProofGridError
from app.db.models.dataset import (
    CanonicalValue,
    Conflict,
    Dataset,
    DatasetVersion,
    DatasetVersionRecord,
)
from app.db.models.entity import EntityMatch
from app.db.models.evidence import Claim, EvidenceAnchor, RawDocument, Source
from app.db.models.export import Export
from app.db.models.project import Project
from app.db.models.requirement import DatasetSchema, Requirement, TrustContract
from app.db.models.workflow import StepRun, Workflow, WorkflowEvent, WorkflowRun, WorkflowVersion
from app.domain.contracts import DatasetSchema as SchemaContract
from app.domain.contracts import PlanDAG, RequirementSpec
from app.domain.contracts import TrustContract as TrustPolicy
from app.domain.identity import digest
from app.domain.responses import PageResponse, ProofResponse, ResourceResponse
from app.domain.states import TERMINAL_RUNS, transition_run
from app.persistence.queries.queue import append_event


class WorkspaceRepository:
    def __init__(self, session: AsyncSession, project_id: UUID, now: datetime):
        self.session, self.project_id, self.now = session, project_id, now

    async def ensure_project(self) -> None:
        await self.session.execute(
            insert(Project)
            .values(
                id=self.project_id, name="ProofGrid demo workspace", slug=f"demo-{self.project_id}"
            )
            .on_conflict_do_nothing(index_elements=[Project.id])
        )

    async def requirement(
        self, req_id: UUID, *, lock: bool = False
    ) -> tuple[Requirement, DatasetSchema, TrustContract]:
        query = select(Requirement).where(
            Requirement.id == req_id, Requirement.project_id == self.project_id
        )
        req = await self.session.scalar(query.with_for_update() if lock else query)
        if req is None:
            raise ProofGridError("NOT_FOUND", "Requirement not found.", status=404)
        schema = await self.session.scalar(
            select(DatasetSchema)
            .where(
                DatasetSchema.requirement_id == req.id, DatasetSchema.project_id == self.project_id
            )
            .order_by(DatasetSchema.version_number.desc())
            .limit(1)
        )
        trust = await self.session.scalar(
            select(TrustContract)
            .where(
                TrustContract.requirement_id == req.id, TrustContract.project_id == self.project_id
            )
            .order_by(TrustContract.version_number.desc())
            .limit(1)
        )
        assert schema and trust
        return req, schema, trust

    def requirement_response(
        self, req: Requirement, schema: DatasetSchema, trust: TrustContract
    ) -> ResourceResponse:
        return ResourceResponse(
            id=req.id,
            data={
                "status": req.status,
                "original_prompt": req.original_prompt,
                "requirement_spec": req.requirement_spec,
                "schema": schema.schema_definition,
                "trust_contract": trust.contract_definition,
                "schema_id": str(schema.id),
                "trust_contract_id": str(trust.id),
                "version": schema.version_number,
                "confirmed": trust.approved_at is not None,
                "compiler_metadata": req.compiler_metadata,
            },
        )

    async def save_compilation(self, prompt: str, result: CompilerResult) -> UUID:
        await self.ensure_project()
        req = Requirement(
            id=uuid4(),
            project_id=self.project_id,
            original_prompt=prompt,
            requirement_spec=result.requirement_spec.model_dump(mode="json"),
            compiler_metadata={
                "compiler": result.metadata.model_dump(mode="json"),
                "ambiguities": [a.model_dump(mode="json") for a in result.ambiguities],
                "assumptions": [a.model_dump(mode="json") for a in result.assumptions],
            },
            status="COMPILED",
        )
        schema = DatasetSchema(
            id=result.dataset_schema_proposal.id,
            project_id=self.project_id,
            requirement_id=req.id,
            version_number=1,
            schema_definition=result.dataset_schema_proposal.model_dump(mode="json"),
        )
        self.session.add(req)
        await self.session.flush()
        self.session.add(schema)
        await self.session.flush()
        self.session.add(
            TrustContract(
                project_id=self.project_id,
                requirement_id=req.id,
                dataset_schema_id=schema.id,
                version_number=1,
                contract_definition=result.trust_contract_proposal.model_dump(mode="json"),
            )
        )
        return req.id

    async def edit(
        self,
        req_id: UUID,
        expected: int,
        spec: RequirementSpec | None = None,
        policy: TrustPolicy | None = None,
    ) -> ResourceResponse:
        req, old_schema, old_trust = await self.requirement(req_id, lock=True)
        if old_schema.version_number != expected:
            raise ProofGridError(
                "VERSION_CONFLICT", "Requirement changed; reload its latest version.", status=409
            )
        actual = spec or RequirementSpec.model_validate(req.requirement_spec)
        schema = SchemaContract(
            entity_type=actual.entity_type,
            fields=actual.fields,
            schema_hash=_compute_schema_hash(actual.fields),
        )
        validate_requirement(actual, schema)
        req.requirement_spec = actual.model_dump(mode="json")
        req.status = "COMPILED"
        version = old_schema.version_number + 1
        stored_schema = DatasetSchema(
            id=schema.id,
            project_id=self.project_id,
            requirement_id=req.id,
            version_number=version,
            schema_definition=schema.model_dump(mode="json"),
        )
        self.session.add(stored_schema)
        await self.session.flush()
        trust = TrustContract(
            id=uuid4(),
            project_id=self.project_id,
            requirement_id=req.id,
            dataset_schema_id=schema.id,
            version_number=version,
            contract_definition=(
                policy.model_dump(mode="json") if policy else old_trust.contract_definition
            ),
        )
        self.session.add(trust)
        await self.session.flush()
        return self.requirement_response(req, stored_schema, trust)

    async def confirm(self, req_id: UUID, expected: int) -> ResourceResponse:
        req, schema, trust = await self.requirement(req_id, lock=True)
        if schema.version_number != expected:
            raise ProofGridError(
                "VERSION_CONFLICT", "Requirement changed; review the latest version.", status=409
            )
        validate_requirement(
            RequirementSpec.model_validate(req.requirement_spec),
            SchemaContract.model_validate(schema.schema_definition),
        )
        validate_trust(TrustPolicy.model_validate(trust.contract_definition))
        req.status = "ACCEPTED"
        trust.approved_at = self.now
        return self.requirement_response(req, schema, trust)

    async def save_plan(
        self, req_id: UUID, schema_id: UUID, trust_id: UUID, plan: PlanDAG, provider: str
    ) -> ResourceResponse:
        req, schema, trust = await self.requirement(req_id, lock=True)
        if (
            req.status != "ACCEPTED"
            or trust.approved_at is None
            or schema.id != schema_id
            or trust.id != trust_id
        ):
            raise ProofGridError(
                "CONFIRMATION_REQUIRED",
                "Confirm the current schema and Trust Contract before planning.",
                status=409,
            )
        validate_plan(
            plan,
            RequirementSpec.model_validate(req.requirement_spec),
            SchemaContract.model_validate(schema.schema_definition),
            TrustPolicy.model_validate(trust.contract_definition),
        )
        workflow = await self.session.scalar(
            select(Workflow).where(
                Workflow.requirement_id == req.id, Workflow.project_id == self.project_id
            )
        )
        if workflow is None:
            workflow = Workflow(
                id=uuid4(),
                project_id=self.project_id,
                requirement_id=req.id,
                name=str(req.requirement_spec["goal"])[:255],
                status="ACTIVE",
            )
            self.session.add(workflow)
            await self.session.flush()
            self.session.add(
                Dataset(
                    project_id=self.project_id,
                    workflow_id=workflow.id,
                    name=workflow.name,
                    slug=str(workflow.id),
                )
            )
        number = (
            int(
                await self.session.scalar(
                    select(func.coalesce(func.max(WorkflowVersion.version_number), 0)).where(
                        WorkflowVersion.workflow_id == workflow.id
                    )
                )
                or 0
            )
            + 1
        )
        version = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version_number=number,
            dataset_schema_id=schema.id,
            trust_contract_id=trust.id,
            plan_dag=plan.model_dump(mode="json"),
            planner_metadata={
                "provider": provider,
                "prompt_version": "planner-v1",
                "requirement_snapshot": req.requirement_spec,
                "schema_hash": schema.schema_definition["schema_hash"],
                "validated": True,
            },
        )
        self.session.add(version)
        return ResourceResponse(
            id=workflow.id,
            data={
                "workflow_version_id": str(version.id),
                "version": number,
                "plan": version.plan_dag,
                "validated": True,
                "schema_hash": schema.schema_definition["schema_hash"],
            },
        )

    async def workflows(self, limit: int, offset: int) -> PageResponse:
        query = select(Workflow).where(Workflow.project_id == self.project_id)
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = (
            await self.session.scalars(
                query.order_by(Workflow.created_at.desc(), Workflow.id).limit(limit).offset(offset)
            )
        ).all()
        return PageResponse(
            items=[
                {
                    "id": str(w.id),
                    "name": w.name,
                    "requirement_id": str(w.requirement_id),
                    "status": w.status,
                }
                for w in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def workflow_version(self, workflow_id: UUID, version_id: UUID) -> ResourceResponse:
        version = await self.session.scalar(
            select(WorkflowVersion)
            .join(Workflow)
            .where(
                WorkflowVersion.id == version_id,
                WorkflowVersion.workflow_id == workflow_id,
                Workflow.project_id == self.project_id,
            )
        )
        if version is None:
            raise ProofGridError("NOT_FOUND", "Workflow version not found.", status=404)
        return ResourceResponse(
            id=version.id,
            data={
                "workflow_id": str(workflow_id),
                "version": version.version_number,
                "plan": version.plan_dag,
                "schema_id": str(version.dataset_schema_id),
                "trust_contract_id": str(version.trust_contract_id),
                "validation": {"valid": bool(version.planner_metadata.get("validated"))},
                "metadata": version.planner_metadata,
            },
        )

    async def list_runs(self, workflow_id: UUID, limit: int, offset: int) -> PageResponse:
        query = (
            select(WorkflowRun)
            .join(WorkflowVersion)
            .join(Workflow)
            .where(
                Workflow.id == workflow_id,
                Workflow.project_id == self.project_id,
                WorkflowRun.project_id == self.project_id,
            )
        )
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = (
            await self.session.scalars(
                query.order_by(WorkflowRun.created_at.desc(), WorkflowRun.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return PageResponse(
            items=[
                {
                    "id": str(v.id),
                    "status": v.status,
                    "mode": v.run_mode,
                    "metrics": v.metrics,
                    "created_at": v.created_at.isoformat(),
                }
                for v in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def dataset(self, dataset_id: UUID) -> ResourceResponse:
        row = await self.session.scalar(
            select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == self.project_id)
        )
        if row is None:
            raise ProofGridError("NOT_FOUND", "Dataset not found.", status=404)
        latest = await self.versions(dataset_id, 1, 0)
        return ResourceResponse(
            id=row.id,
            data={
                "name": row.name,
                "workflow_id": str(row.workflow_id),
                "latest_version": latest.items[0] if latest.items else None,
            },
        )

    async def create_run(
        self,
        workflow_id: UUID,
        version_id: UUID,
        key: UUID,
        mode: str,
        max_runs: int,
        fixture_set: str = "synthetic",
    ) -> ResourceResponse:
        version = await self.session.scalar(
            select(WorkflowVersion)
            .join(Workflow)
            .where(
                WorkflowVersion.id == version_id,
                Workflow.id == workflow_id,
                Workflow.project_id == self.project_id,
            )
        )
        if version is None:
            raise ProofGridError("NOT_FOUND", "Workflow version not found.", status=404)
        run_id = uuid5(workflow_id, str(key))
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"runs:{self.project_id}"},
        )
        existing = await self.session.scalar(
            select(WorkflowRun).where(
                WorkflowRun.id == run_id, WorkflowRun.project_id == self.project_id
            )
        )
        if existing:
            if existing.workflow_version_id != version_id:
                raise ProofGridError(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key already belongs to another workflow version.",
                    status=409,
                )
            return ResourceResponse(id=existing.id, data={"status": existing.status})
        active = await self.session.scalar(
            select(func.count())
            .select_from(WorkflowRun)
            .where(
                WorkflowRun.project_id == self.project_id,
                WorkflowRun.status.in_(["QUEUED", "RUNNING", "CANCEL_REQUESTED"]),
            )
        )
        if int(active or 0) >= max_runs:
            raise ProofGridError("RUN_CAPACITY", "Concurrent run limit reached.", status=429)
        trust = await self.session.get(TrustContract, version.trust_contract_id)
        assert trust
        if trust.approved_at is None:
            raise ProofGridError(
                "CONFIRMATION_REQUIRED", "Trust Contract must be confirmed.", status=409
            )
        run = WorkflowRun(
            id=run_id,
            project_id=self.project_id,
            workflow_version_id=version.id,
            run_mode=mode,
            status=transition_run("CREATED", "QUEUED"),
            budget_snapshot=TrustPolicy.model_validate(trust.contract_definition).model_dump(
                mode="json"
            ),
            metrics={
                "acquisition_mode": mode,
                "fixture_set": fixture_set if mode == "FIXTURE" else None,
                "fixture_label": (
                    "Captured historical public announcements"
                    if fixture_set == "captured"
                    else "Synthetic showcase evidence, not live business facts"
                )
                if mode == "FIXTURE"
                else None,
            },
        )
        self.session.add(run)
        await self.session.flush()
        plan = PlanDAG.model_validate(version.plan_dag)
        for node in plan.nodes:
            self.session.add(
                StepRun(
                    workflow_run_id=run.id,
                    node_id=node.id,
                    operator_type=str(node.operator),
                    attempt=1,
                    status="READY" if not node.depends_on else "PENDING",
                    input_hash=digest(
                        {"run": str(run.id), "node": node.model_dump(mode="json"), "version": 1}
                    ),
                )
            )
        await append_event(
            self.session, run, "run.state_changed", {"status": run.status, "acquisition_mode": mode}
        )
        return ResourceResponse(
            id=run.id,
            data={
                "status": run.status,
                "workflow_version_id": str(version.id),
                "acquisition_mode": mode,
            },
        )

    async def run(self, run_id: UUID, *, cancel: bool = False) -> ResourceResponse:
        query = select(WorkflowRun).where(
            WorkflowRun.id == run_id, WorkflowRun.project_id == self.project_id
        )
        run = await self.session.scalar(query.with_for_update() if cancel else query)
        if run is None:
            raise ProofGridError("NOT_FOUND", "Run not found.", status=404)
        if cancel and run.status not in TERMINAL_RUNS and run.status != "CANCEL_REQUESTED":
            run.status = transition_run(run.status, "CANCEL_REQUESTED")
            await append_event(self.session, run, "run.state_changed", {"status": run.status})
        steps = list(
            (
                await self.session.scalars(
                    select(StepRun)
                    .where(StepRun.workflow_run_id == run.id)
                    .order_by(StepRun.created_at)
                    .limit(32)
                )
            ).all()
        )
        return ResourceResponse(
            id=run.id,
            data={
                "status": run.status,
                "mode": run.run_mode,
                "metrics": run.metrics,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "steps": [
                    {
                        "id": str(s.id),
                        "node_id": s.node_id,
                        "operator": s.operator_type,
                        "status": s.status,
                        "attempt": s.attempt,
                        "error_code": s.error_code,
                    }
                    for s in steps
                ],
            },
        )

    async def events(self, run_id: UUID, after: int) -> list[dict[str, Any]]:
        await self.run(run_id)
        events = list(
            (
                await self.session.scalars(
                    select(WorkflowEvent)
                    .where(
                        WorkflowEvent.workflow_run_id == run_id,
                        WorkflowEvent.sequence_number > after,
                    )
                    .order_by(WorkflowEvent.sequence_number)
                    .limit(200)
                )
            ).all()
        )
        return [
            {"sequence": e.sequence_number, "event": e.event_type, "data": e.payload}
            for e in events
        ]

    async def dataset_version(
        self, dataset_id: UUID, version_id: UUID
    ) -> tuple[DatasetVersion, SchemaContract]:
        row = (
            await self.session.execute(
                select(DatasetVersion, DatasetSchema)
                .join(DatasetSchema, DatasetSchema.id == DatasetVersion.dataset_schema_id)
                .where(
                    DatasetVersion.id == version_id,
                    DatasetVersion.dataset_id == dataset_id,
                    DatasetVersion.project_id == self.project_id,
                    DatasetSchema.project_id == self.project_id,
                    DatasetVersion.status == "FINALIZED",
                )
            )
        ).one_or_none()
        if row is None:
            raise ProofGridError("NOT_FOUND", "Dataset version not found.", status=404)
        version, schema = row
        return version, SchemaContract.model_validate(schema.schema_definition)

    async def records(
        self,
        dataset_id: UUID,
        version_id: UUID,
        *,
        limit: int,
        offset: int,
        sort: str | None,
        q: str | None,
        filters: list[str],
    ) -> PageResponse:
        _, schema = await self.dataset_version(dataset_id, version_id)
        fields = {field.key: field for field in schema.fields}
        query = select(DatasetVersionRecord).where(
            DatasetVersionRecord.project_id == self.project_id,
            DatasetVersionRecord.dataset_version_id == version_id,
        )
        for rule in filters:
            try:
                selector, expected = rule.split(":", 1)
                key, operator = selector.rsplit(".", 1)
                trust = key.startswith("trust.")
                field = fields[key.removeprefix("trust.")]
                column = (
                    DatasetVersionRecord.trust_summary[field.key].astext
                    if trust
                    else DatasetVersionRecord.record_data[field.key].astext
                )
                if not trust and field.data_type == "money":
                    column = cast(
                        DatasetVersionRecord.record_data[field.key]["amount"].astext, Numeric
                    )
                elif not trust and field.data_type == "number":
                    column = cast(column, Numeric)
                allowed = {"eq", "neq", "in"}
                if not trust and field.data_type in {"number", "money", "date"}:
                    allowed.update({"gt", "gte", "lt", "lte"})
                elif not trust and field.data_type in {
                    "text",
                    "url",
                    "location",
                    "entity_ref",
                    "entity_list",
                }:
                    allowed.add("contains")
                if operator not in allowed:
                    raise ValueError
                if field.data_type == "date" and not trust:
                    column = func.coalesce(
                        DatasetVersionRecord.record_data[field.key]["value"].astext, column
                    )
                value: Any = expected
                if field.data_type == "boolean" and not trust and expected not in {"true", "false"}:
                    raise ValueError
                if operator == "in":
                    candidates: list[Any] = expected.split(",")
                    if not trust and field.data_type in {"money", "number"}:
                        from decimal import Decimal

                        candidates = [Decimal(v) for v in candidates]
                        if not all(v.is_finite() for v in candidates):
                            raise ValueError
                    condition = column.in_(candidates)
                elif operator == "contains":
                    condition = cast(column, String).contains(expected, autoescape=True)
                else:
                    if field.data_type in {"money", "number"} and not trust:
                        from decimal import Decimal

                        value = Decimal(expected)
                        if not value.is_finite():
                            raise ValueError
                    condition = {
                        "eq": column.__eq__,
                        "neq": column.__ne__,
                        "gt": column.__gt__,
                        "gte": column.__ge__,
                        "lt": column.__lt__,
                        "lte": column.__le__,
                    }[operator](value)
                query = query.where(condition)
            except (ValueError, KeyError, ArithmeticError):
                raise ProofGridError(
                    "FILTER_INVALID",
                    "Filter must use a schema field, canonical operator and typed value.",
                ) from None
        if q:
            query = query.where(
                cast(DatasetVersionRecord.record_data, String).ilike(
                    "%" + q.replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"
                )
            )
        if sort:
            try:
                key, direction = sort.split(":")
                field = fields[key]
                if direction not in {"asc", "desc"}:
                    raise ValueError
                order = DatasetVersionRecord.record_data[key].astext
                if field.data_type == "money":
                    order = cast(DatasetVersionRecord.record_data[key]["amount"].astext, Numeric)
                elif field.data_type == "number":
                    order = cast(order, Numeric)
                query = query.order_by(
                    order.asc().nulls_last() if direction == "asc" else order.desc().nulls_last()
                )
            except (ValueError, KeyError):
                raise ProofGridError(
                    "SORT_INVALID", "Sort must reference a schema field and asc/desc."
                ) from None
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(query.order_by(None).subquery())
            )
            or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    query.order_by(DatasetVersionRecord.entity_id).offset(offset).limit(limit)
                )
            ).all()
        )
        return PageResponse(
            items=[
                {
                    "entity_id": str(row.entity_id),
                    "values": row.record_data,
                    "trust": row.trust_summary,
                    "row_hash": row.record_hash,
                }
                for row in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def proof(
        self, dataset_id: UUID, version_id: UUID, entity_id: UUID, key: str
    ) -> ProofResponse:
        cell = (
            await self.session.execute(
                select(CanonicalValue, Conflict)
                .join(DatasetVersion, DatasetVersion.id == CanonicalValue.dataset_version_id)
                .outerjoin(
                    Conflict,
                    and_(
                        Conflict.dataset_version_id == CanonicalValue.dataset_version_id,
                        Conflict.entity_id == CanonicalValue.entity_id,
                        Conflict.field_key == CanonicalValue.field_key,
                        Conflict.project_id == self.project_id,
                    ),
                )
                .where(
                    CanonicalValue.project_id == self.project_id,
                    CanonicalValue.dataset_version_id == version_id,
                    CanonicalValue.entity_id == entity_id,
                    CanonicalValue.field_key == key,
                    DatasetVersion.dataset_id == dataset_id,
                    DatasetVersion.project_id == self.project_id,
                    DatasetVersion.status == "FINALIZED",
                )
            )
        ).one_or_none()
        if cell is None:
            raise ProofGridError("NOT_FOUND", "ProofCell not found.", status=404)
        canonical, conflict = cell
        claim_ids = [UUID(value) for value in canonical.provenance_summary.get("claim_ids", [])]
        rows = (
            await self.session.execute(
                select(Claim, Source, RawDocument, EvidenceAnchor)
                .options(defer(RawDocument.content))
                .join(Source, Source.id == Claim.source_id)
                .join(RawDocument, RawDocument.id == Claim.raw_document_id)
                .join(EvidenceAnchor, EvidenceAnchor.claim_id == Claim.id)
                .where(Claim.id.in_(claim_ids), Claim.project_id == self.project_id)
                .limit(500)
            )
        ).all()
        claims = [self._claim_projection(c, s, d, a) for c, s, d, a in rows]
        return ProofResponse(
            dataset_version_id=version_id,
            entity_id=entity_id,
            field_key=key,
            canonical_value=canonical.value,
            trust_status=canonical.trust_status,
            resolution=canonical.provenance_summary,
            claims=claims,
            conflict={
                "id": str(conflict.id),
                "status": conflict.status,
                "details": conflict.details,
                "selected_claim_id": str(conflict.resolved_claim_id)
                if conflict.resolved_claim_id
                else None,
            }
            if conflict
            else None,
        )

    @staticmethod
    def _claim_projection(c: Claim, s: Source, d: RawDocument, a: EvidenceAnchor) -> dict[str, Any]:
        return {
            "id": str(c.id),
            "raw_value": c.raw_value,
            "normalized_value": c.normalized_value,
            "source_id": str(s.id),
            "source_url": d.final_url,
            "raw_document_id": str(d.id),
            "content_hash": d.content_hash,
            "retrieved_at": d.retrieved_at.isoformat(),
            "extraction_method": c.extraction_method,
            "validation_flags": c.validation_flags,
            "evidence": {
                "type": a.anchor_type,
                "locator": a.locator,
                "quote": a.quoted_text,
                "verification_status": a.verification_status,
            },
            "acquisition": d.retrieval_metadata,
        }

    async def evidence_bundle(self, dataset_id: UUID, version_id: UUID) -> list[dict[str, Any]]:
        version, _ = await self.dataset_version(dataset_id, version_id)
        cells = (
            await self.session.scalars(
                select(CanonicalValue)
                .where(
                    CanonicalValue.project_id == self.project_id,
                    CanonicalValue.dataset_version_id == version_id,
                )
                .limit(25000)
            )
        ).all()
        rows = (
            await self.session.execute(
                select(Claim, Source, RawDocument, EvidenceAnchor)
                .options(defer(RawDocument.content))
                .join(Source, Source.id == Claim.source_id)
                .join(RawDocument, RawDocument.id == Claim.raw_document_id)
                .join(EvidenceAnchor, EvidenceAnchor.claim_id == Claim.id)
                .where(
                    Claim.project_id == self.project_id,
                    Claim.workflow_run_id == version.workflow_run_id,
                )
                .limit(10000)
            )
        ).all()
        claims = {str(c.id): self._claim_projection(c, s, d, a) for c, s, d, a in rows}
        return [
            {
                "dataset_version_id": str(version_id),
                "entity_id": str(c.entity_id),
                "field_key": c.field_key,
                "canonical_value": c.value,
                "trust_status": c.trust_status,
                "resolution": c.provenance_summary,
                "claims": [
                    claims[key]
                    for key in c.provenance_summary.get("claim_ids", [])
                    if key in claims
                ],
            }
            for c in cells
        ]

    async def list_datasets(self, limit: int, offset: int) -> PageResponse:
        query = select(Dataset).where(Dataset.project_id == self.project_id)
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    query.order_by(Dataset.created_at.desc(), Dataset.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
        return PageResponse(
            items=[
                {"id": str(d.id), "name": d.name, "workflow_id": str(d.workflow_id)} for d in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def versions(self, dataset_id: UUID, limit: int, offset: int) -> PageResponse:
        dataset = await self.session.scalar(
            select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == self.project_id)
        )
        if dataset is None:
            raise ProofGridError("NOT_FOUND", "Dataset not found.", status=404)
        query = select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id, DatasetVersion.project_id == self.project_id
        )
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    query.order_by(DatasetVersion.version_number.desc()).limit(limit).offset(offset)
                )
            ).all()
        )
        return PageResponse(
            items=[
                {
                    "id": str(v.id),
                    "version": v.version_number,
                    "record_count": v.record_count,
                    "status": v.status,
                    "workflow_run_id": str(v.workflow_run_id),
                    "created_at": v.created_at.isoformat(),
                }
                for v in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def diff(
        self, dataset_id: UUID, before: UUID, after: UUID, limit: int, offset: int
    ) -> PageResponse:
        left = await self.records(
            dataset_id, before, limit=500, offset=0, sort=None, q=None, filters=[]
        )
        right = await self.records(
            dataset_id, after, limit=500, offset=0, sort=None, q=None, filters=[]
        )
        a, b = {r["entity_id"]: r for r in left.items}, {r["entity_id"]: r for r in right.items}
        evidence: dict[str, dict[tuple[str, str], set[tuple[str, str]]]] = {
            str(before): {},
            str(after): {},
        }
        evidence_rows = (
            await self.session.execute(
                select(
                    DatasetVersion.id,
                    Claim.entity_id,
                    Claim.field_key,
                    Source.canonical_url,
                    RawDocument.content_hash,
                )
                .join(Claim, Claim.workflow_run_id == DatasetVersion.workflow_run_id)
                .join(Source, Source.id == Claim.source_id)
                .join(RawDocument, RawDocument.id == Claim.raw_document_id)
                .where(
                    DatasetVersion.id.in_([before, after]),
                    DatasetVersion.project_id == self.project_id,
                    Claim.project_id == self.project_id,
                )
                .limit(20000)
            )
        ).all()
        for vid, entity, field, url, content_hash in evidence_rows:
            evidence[str(vid)].setdefault((str(entity), field), set()).add((url, content_hash))
        items = []
        for eid in sorted(a.keys() | b.keys()):
            state = (
                "ADDED"
                if eid not in a
                else "MISSING_LATEST"
                if eid not in b
                else "CHANGED"
                if a[eid]["row_hash"] != b[eid]["row_hash"]
                else "UNCHANGED"
            )
            changes = []
            if eid in a and eid in b:
                for field in a[eid]["values"].keys() | b[eid]["values"].keys():
                    flags = []
                    if a[eid]["values"].get(field) != b[eid]["values"].get(field):
                        flags.append("VALUE_CHANGED")
                    if a[eid]["trust"].get(field) != b[eid]["trust"].get(field):
                        flags.append("TRUST_CHANGED")
                        if "CONFLICTING" in {
                            a[eid]["trust"].get(field),
                            b[eid]["trust"].get(field),
                        }:
                            flags.append("CONFLICT_CHANGED")
                    if evidence[str(before)].get((eid, field), set()) != evidence[str(after)].get(
                        (eid, field), set()
                    ):
                        flags.append("EVIDENCE_CHANGED")
                    if flags:
                        state = "CHANGED"
                        changes.append({"field": field, "changes": flags})
            items.append(
                {
                    "entity_id": eid,
                    "state": state,
                    "before": a.get(eid),
                    "after": b.get(eid),
                    "fields": changes,
                }
            )
        return PageResponse(
            items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset
        )

    async def review_list(self, limit: int, offset: int) -> PageResponse:
        conflicts = list(
            (
                await self.session.scalars(
                    select(Conflict)
                    .where(Conflict.project_id == self.project_id, Conflict.status == "OPEN")
                    .order_by(Conflict.created_at)
                    .limit(500)
                )
            ).all()
        )
        matches = list(
            (
                await self.session.scalars(
                    select(EntityMatch)
                    .where(
                        EntityMatch.project_id == self.project_id, EntityMatch.decision == "REVIEW"
                    )
                    .order_by(EntityMatch.created_at)
                    .limit(500)
                )
            ).all()
        )
        items = [
            {
                "kind": "conflict",
                "id": str(c.id),
                "entity_id": str(c.entity_id),
                "field_key": c.field_key,
                "dataset_version_id": str(c.dataset_version_id),
                "details": c.details,
            }
            for c in conflicts
        ] + [
            {
                "kind": "entity_match",
                "id": str(m.id),
                "left": str(m.source_entity_id),
                "right": str(m.target_entity_id),
                "signals": m.signals,
                "reason": m.reason,
            }
            for m in matches
        ]
        return PageResponse(
            items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset
        )

    async def review(
        self, kind: str, item_id: UUID, decision: str, selected: UUID | None, note: str
    ) -> ResourceResponse:
        if kind == "entity-match":
            match = await self.session.scalar(
                select(EntityMatch)
                .where(EntityMatch.id == item_id, EntityMatch.project_id == self.project_id)
                .with_for_update()
            )
            if match is None:
                raise ProofGridError("NOT_FOUND", "Review item not found.", status=404)
            if decision not in {"HUMAN_MERGE", "HUMAN_SEPARATE", "DEFER"}:
                raise ProofGridError("REVIEW_INVALID", "Select merge, separate or defer.")
            if decision != "DEFER":
                match.decision = decision
            match.reason = {
                **match.reason,
                "review_note": note,
                "reviewed_at": self.now.isoformat(),
            }
            return ResourceResponse(
                id=match.id,
                data={"decision": match.decision, "applies_to": "subsequent dataset versions"},
            )
        conflict = await self.session.scalar(
            select(Conflict)
            .where(Conflict.id == item_id, Conflict.project_id == self.project_id)
            .with_for_update()
        )
        if conflict is None:
            raise ProofGridError("NOT_FOUND", "Review item not found.", status=404)
        if decision == "DEFER":
            return ResourceResponse(id=conflict.id, data={"status": conflict.status})
        if (
            decision != "SELECT_DISPLAY"
            or not selected
            or str(selected) not in conflict.details.get("claim_ids", [])
        ):
            raise ProofGridError(
                "REVIEW_INVALID", "Choose one of this conflict's preserved claims."
            )
        conflict.resolved_claim_id = selected
        conflict.resolved_at = self.now
        conflict.status = "RESOLVED"
        conflict.details = {
            **conflict.details,
            "review_note": note,
            "review_decision": "DISPLAY_SELECTION_ONLY",
        }
        return ResourceResponse(
            id=conflict.id,
            data={
                "status": conflict.status,
                "selected_claim_id": str(selected),
                "applies_to": "subsequent dataset versions; historical values and disagreement preserved",
            },
        )

    async def create_export(self, version_id: UUID, format: str) -> ResourceResponse:
        version = await self.session.scalar(
            select(DatasetVersion).where(
                DatasetVersion.id == version_id,
                DatasetVersion.project_id == self.project_id,
                DatasetVersion.status == "FINALIZED",
            )
        )
        if version is None:
            raise ProofGridError("NOT_FOUND", "Dataset version not found.", status=404)
        export_id = uuid5(version_id, format)
        await self.session.execute(
            insert(Export)
            .values(
                id=export_id,
                project_id=self.project_id,
                dataset_version_id=version.id,
                format=format,
                manifest={
                    "dataset_id": str(version.dataset_id),
                    "record_count": version.record_count,
                    "evidence_companion": True,
                },
            )
            .on_conflict_do_nothing()
        )
        return ResourceResponse(
            id=export_id,
            data={
                "status": "READY",
                "dataset_version_id": str(version.id),
                "format": format,
                "download_url": f"/v1/exports/{export_id}/download",
            },
        )

    async def export(self, export_id: UUID) -> Export:
        row = await self.session.scalar(
            select(Export).where(Export.id == export_id, Export.project_id == self.project_id)
        )
        if row is None:
            raise ProofGridError("NOT_FOUND", "Export not found.", status=404)
        return row
