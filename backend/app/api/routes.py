"""Versioned HTTP composition layer for the confirmed workflow lifecycle."""

import asyncio
import csv
import hmac
import io
import json
import zipfile
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response, StreamingResponse

from app.ai.factory import structured_provider
from app.api.contracts import (
    CompileRequest,
    CompileResponse,
    ConfirmRequest,
    ExportRequest,
    PageResponse,
    ProofResponse,
    RequirementEdit,
    ResourceResponse,
    ReviewRequest,
    RunRequest,
    TrustEdit,
)
from app.application.planning.service import WorkflowPlanner
from app.application.requirement_compiler.models import CompilationContext, CompilerResult
from app.application.requirement_compiler.service import RequirementCompiler
from app.core.config import get_settings
from app.core.errors import ProofGridError
from app.db.session import get_session_factory
from app.domain.clock import utc_now
from app.domain.contracts import DatasetSchema, RequirementSpec, TrustContract
from app.domain.states import TERMINAL_RUNS
from app.persistence.repositories.workspace import WorkspaceRepository

router = APIRouter(prefix="/v1")


async def workspace(
    authorization: Annotated[str | None, Header()] = None,
) -> AsyncIterator[WorkspaceRepository]:
    settings = get_settings()
    if settings.AUTH_ENABLED:
        expected = settings.API_AUTH_TOKEN
        if (
            expected is None
            or not expected.get_secret_value()
            or not authorization
            or not hmac.compare_digest(authorization, "Bearer " + expected.get_secret_value())
        ):
            raise ProofGridError("UNAUTHORIZED", "A valid workspace token is required.", status=401)
    if not settings.DATABASE_URL:
        raise ProofGridError(
            "DATABASE_UNCONFIGURED", "Configure PostgreSQL before using the workspace.", status=503
        )
    async with get_session_factory()() as session, session.begin():
        yield WorkspaceRepository(session, settings.DEMO_PROJECT_ID, utc_now())


Repo = Annotated[WorkspaceRepository, Depends(workspace, scope="function")]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0, le=100000)]


@router.post("/requirements/compile", response_model=CompileResponse)
async def compile_requirement(body: CompileRequest, repo: Repo) -> CompileResponse:
    reference = body.reference_date or utc_now()
    if reference.tzinfo is None:
        raise ProofGridError("REFERENCE_DATE_INVALID", "Reference date must include a timezone.")
    async with structured_provider(get_settings()) as provider:
        result = await RequirementCompiler(provider).compile(
            body.prompt, context=CompilationContext(reference_date=reference)
        )
    req_id = (
        await repo.save_compilation(body.prompt, result)
        if isinstance(result, CompilerResult)
        else None
    )
    return CompileResponse(requirement_id=req_id, outcome=result)


@router.get("/requirements/{req_id}", response_model=ResourceResponse)
async def requirement(req_id: UUID, repo: Repo) -> ResourceResponse:
    return repo.requirement_response(*await repo.requirement(req_id))


@router.patch("/requirements/{req_id}", response_model=ResourceResponse)
async def edit_requirement(req_id: UUID, body: RequirementEdit, repo: Repo) -> ResourceResponse:
    return await repo.edit(req_id, body.expected_version, spec=body.requirement_spec)


@router.post("/requirements/{req_id}/trust-contract", response_model=ResourceResponse)
async def edit_trust(req_id: UUID, body: TrustEdit, repo: Repo) -> ResourceResponse:
    return await repo.edit(req_id, body.expected_version, policy=body.trust_contract)


@router.post("/requirements/{req_id}/confirm", response_model=ResourceResponse)
async def confirm(req_id: UUID, body: ConfirmRequest, repo: Repo) -> ResourceResponse:
    return await repo.confirm(req_id, body.expected_version)


@router.post("/requirements/{req_id}/plan", response_model=ResourceResponse)
async def plan(req_id: UUID, repo: Repo) -> ResourceResponse:
    req, schema, trust = await repo.requirement(req_id)
    if req.status != "ACCEPTED" or trust.approved_at is None:
        raise ProofGridError(
            "CONFIRMATION_REQUIRED",
            "Confirm the schema and Trust Contract before planning.",
            status=409,
        )
    settings = get_settings()
    async with structured_provider(settings) as provider:
        planner = WorkflowPlanner(None if settings.AI_PROVIDER == "fixture" else provider)
        result = await planner.generate(
            RequirementSpec.model_validate(req.requirement_spec),
            DatasetSchema.model_validate(schema.schema_definition),
            TrustContract.model_validate(trust.contract_definition),
        )
    return await repo.save_plan(req_id, schema.id, trust.id, result, settings.AI_PROVIDER)


@router.get("/requirements/{req_id}/schema", response_model=ResourceResponse)
async def read_schema(req_id: UUID, repo: Repo) -> ResourceResponse:
    _, schema, _ = await repo.requirement(req_id)
    return ResourceResponse(
        id=schema.id, data={"version": schema.version_number, "schema": schema.schema_definition}
    )


@router.get("/requirements/{req_id}/trust-contract", response_model=ResourceResponse)
async def read_trust(req_id: UUID, repo: Repo) -> ResourceResponse:
    _, _, policy = await repo.requirement(req_id)
    return ResourceResponse(
        id=policy.id,
        data={
            "version": policy.version_number,
            "contract": policy.contract_definition,
            "confirmed": policy.approved_at is not None,
        },
    )


@router.get("/workflows", response_model=PageResponse)
async def workflows(repo: Repo, limit: Limit = 50, offset: Offset = 0) -> PageResponse:
    return await repo.workflows(limit, offset)


@router.get("/workflows/{workflow_id}/versions/{version_id}", response_model=ResourceResponse)
async def workflow_version(workflow_id: UUID, version_id: UUID, repo: Repo) -> ResourceResponse:
    return await repo.workflow_version(workflow_id, version_id)


@router.get("/workflows/{workflow_id}/runs", response_model=PageResponse)
async def list_runs(
    workflow_id: UUID, repo: Repo, limit: Limit = 50, offset: Offset = 0
) -> PageResponse:
    return await repo.list_runs(workflow_id, limit, offset)


@router.post("/workflows/{workflow_id}/runs", response_model=ResourceResponse)
async def create_run(workflow_id: UUID, body: RunRequest, repo: Repo) -> ResourceResponse:
    settings = get_settings()
    return await repo.create_run(
        workflow_id,
        body.workflow_version_id,
        body.idempotency_key,
        settings.ACQUISITION_MODE,
        settings.MAX_CONCURRENT_RUNS,
        settings.FIXTURE_SET,
    )


@router.get("/runs/{run_id}", response_model=ResourceResponse)
async def run(run_id: UUID, repo: Repo) -> ResourceResponse:
    return await repo.run(run_id)


@router.post("/runs/{run_id}/cancel", response_model=ResourceResponse)
async def cancel(run_id: UUID, repo: Repo) -> ResourceResponse:
    return await repo.run(run_id, cancel=True)


@router.get("/runs/{run_id}/events")
async def events(
    run_id: UUID,
    request: Request,
    repo: Repo,
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    await repo.run(run_id)
    try:
        cursor = int(last_event_id) if last_event_id is not None else after
        if cursor < 0:
            raise ValueError
    except ValueError:
        raise ProofGridError(
            "EVENT_CURSOR_INVALID", "Event cursor must be a non-negative integer."
        ) from None
    project_id = repo.project_id

    async def stream() -> AsyncIterator[str]:
        nonlocal cursor
        while not await request.is_disconnected():
            async with get_session_factory()() as session:
                scoped = WorkspaceRepository(session, project_id, utc_now())
                batch = await scoped.events(run_id, cursor)
                state = await scoped.run(run_id)
            for event in batch:
                cursor = event["sequence"]
                yield f"id: {cursor}\nevent: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
            if state.data["status"] in TERMINAL_RUNS and len(batch) < 200:
                break
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/datasets", response_model=PageResponse)
async def datasets(repo: Repo, limit: Limit = 50, offset: Offset = 0) -> PageResponse:
    return await repo.list_datasets(limit, offset)


@router.get("/datasets/{dataset_id}", response_model=ResourceResponse)
async def dataset(dataset_id: UUID, repo: Repo) -> ResourceResponse:
    return await repo.dataset(dataset_id)


@router.get("/datasets/{dataset_id}/versions/{version_id}", response_model=ResourceResponse)
async def dataset_version(dataset_id: UUID, version_id: UUID, repo: Repo) -> ResourceResponse:
    version, schema = await repo.dataset_version(dataset_id, version_id)
    return ResourceResponse(
        id=version.id,
        data={
            "version": version.version_number,
            "record_count": version.record_count,
            "schema": schema.model_dump(mode="json"),
            "status": version.status,
        },
    )


@router.get("/datasets/{dataset_id}/versions", response_model=PageResponse)
async def versions(
    dataset_id: UUID, repo: Repo, limit: Limit = 50, offset: Offset = 0
) -> PageResponse:
    return await repo.versions(dataset_id, limit, offset)


@router.get("/datasets/{dataset_id}/versions/{version_id}/records", response_model=PageResponse)
async def records(
    dataset_id: UUID,
    version_id: UUID,
    repo: Repo,
    limit: Limit = 50,
    offset: Offset = 0,
    sort: str | None = None,
    q: Annotated[str | None, Query(max_length=300)] = None,
    filters: Annotated[list[str] | None, Query(alias="filter", max_length=20)] = None,
) -> PageResponse:
    return await repo.records(
        dataset_id, version_id, limit=limit, offset=offset, sort=sort, q=q, filters=filters or []
    )


@router.get(
    "/datasets/{dataset_id}/versions/{version_id}/records/{entity_id}/proof/{field}",
    response_model=ProofResponse,
)
async def proof(
    dataset_id: UUID, version_id: UUID, entity_id: UUID, field: str, repo: Repo
) -> ProofResponse:
    return await repo.proof(dataset_id, version_id, entity_id, field)


@router.get("/datasets/{dataset_id}/diff", response_model=PageResponse)
async def diff(
    dataset_id: UUID, before: UUID, after: UUID, repo: Repo, limit: Limit = 50, offset: Offset = 0
) -> PageResponse:
    return await repo.diff(dataset_id, before, after, limit, offset)


@router.get("/review", response_model=PageResponse)
async def review_queue(repo: Repo, limit: Limit = 50, offset: Offset = 0) -> PageResponse:
    return await repo.review_list(limit, offset)


@router.post("/review/{kind}/{item_id}", response_model=ResourceResponse)
async def review(kind: str, item_id: UUID, body: ReviewRequest, repo: Repo) -> ResourceResponse:
    if kind not in {"entity-match", "conflict"}:
        raise ProofGridError("NOT_FOUND", "Review type not found.", status=404)
    return await repo.review(kind, item_id, body.decision, body.selected_claim_id, body.note)


@router.post("/exports", response_model=ResourceResponse)
async def create_export(body: ExportRequest, repo: Repo) -> ResourceResponse:
    return await repo.create_export(body.dataset_version_id, body.format)


@router.get("/exports/{export_id}", response_model=ResourceResponse)
async def export(export_id: UUID, repo: Repo) -> ResourceResponse:
    row = await repo.export(export_id)
    return ResourceResponse(
        id=row.id,
        data={
            "dataset_version_id": str(row.dataset_version_id),
            "format": row.format,
            "manifest": row.manifest,
            "download_url": f"/v1/exports/{row.id}/download",
        },
    )


@router.get("/exports/{export_id}/download")
async def download(export_id: UUID, repo: Repo) -> Response:
    export = await repo.export(export_id)
    dataset_id = UUID(export.manifest["dataset_id"])
    rows = await repo.records(
        dataset_id, export.dataset_version_id, limit=500, offset=0, sort=None, q=None, filters=[]
    )
    evidence = await repo.evidence_bundle(dataset_id, export.dataset_version_id)
    if export.format == "json":
        data = json.dumps(rows.model_dump(mode="json"), indent=2)
    else:
        text = io.StringIO()
        keys = list(rows.items[0]["values"]) if rows.items else []
        writer = csv.writer(text)
        writer.writerow(["entity_id", *keys])
        for row in rows.items:
            values = []
            for key in keys:
                value = row["values"].get(key)
                cell = (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else ""
                    if value is None
                    else str(value)
                )
                values.append(
                    "'" + cell if cell.lstrip().startswith(("=", "+", "-", "@")) else cell
                )
            writer.writerow([row["entity_id"], *values])
        data = text.getvalue()
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dataset." + export.format, data)
        archive.writestr(
            "evidence.json",
            json.dumps(
                {"dataset_version_id": str(export.dataset_version_id), "cells": evidence}, indent=2
            ),
        )
        archive.writestr("manifest.json", json.dumps(export.manifest))
    return Response(
        bundle.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="proofgrid-{export.id}.zip"'},
    )
