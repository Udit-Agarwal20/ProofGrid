"""Atomic persistence of fenced operator results and dataset snapshots."""

import hashlib
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.acquisition.models import AcquiredDocument
from app.application.datasets.entities import identity_decision
from app.application.datasets.trust import TrustClaim, canonicalize
from app.application.extraction.models import ClaimDraft
from app.core.errors import ProofGridError
from app.db.models.dataset import (
    CanonicalValue,
    Conflict,
    Dataset,
    DatasetVersion,
    DatasetVersionRecord,
)
from app.db.models.entity import Entity, EntityMatch
from app.db.models.evidence import Claim, EvidenceAnchor, RawDocument, Source
from app.db.models.outbox import OutboxEvent
from app.db.models.requirement import DatasetSchema, TrustContract
from app.db.models.workflow import StepRun, WorkflowRun, WorkflowVersion
from app.domain.contracts import DatasetSchema as SchemaContract
from app.domain.contracts import RequirementSpec
from app.domain.contracts import TrustContract as TrustPolicy
from app.domain.identity import digest
from app.domain.normalization import normalized_name


async def persist_operator_output(
    session: AsyncSession, run: WorkflowRun, step: StepRun, output: dict[str, Any], now: datetime
) -> dict[str, Any]:
    if step.operator_type == "FETCH_HTTP":
        ids = []
        for raw in output.pop("documents", []):
            doc = AcquiredDocument.model_validate(raw)
            source = await session.scalar(
                select(Source).where(
                    Source.project_id == run.project_id, Source.canonical_url == doc.url
                )
            )
            if source is None:
                source = Source(
                    id=uuid4(),
                    project_id=run.project_id,
                    canonical_url=doc.url,
                    domain=urlsplit(doc.url).hostname or "",
                    source_type="FIXTURE"
                    if doc.acquisition_method == "FIXTURE"
                    else "API"
                    if "json" in doc.content_type
                    else "WEB_PAGE",
                    source_metadata={"first_party": bool(doc.metadata.get("first_party"))},
                )
                session.add(source)
                await session.flush()
            content_hash = hashlib.sha256(doc.content.encode()).hexdigest()
            stored = await session.scalar(
                select(RawDocument).where(
                    RawDocument.workflow_run_id == run.id,
                    RawDocument.source_id == source.id,
                    RawDocument.content_hash == content_hash,
                )
            )
            if stored is None:
                stored = RawDocument(
                    id=uuid4(),
                    project_id=run.project_id,
                    workflow_run_id=run.id,
                    source_id=source.id,
                    retrieved_at=doc.retrieved_at,
                    final_url=doc.url,
                    mime_type=doc.content_type,
                    content=doc.content,
                    size_bytes=len(doc.content.encode()),
                    content_hash=content_hash,
                    http_status=doc.http_status,
                    retrieval_metadata={
                        **doc.metadata,
                        "acquisition_method": doc.acquisition_method,
                        "parser_version": "1.0",
                    },
                )
                session.add(stored)
                await session.flush()
            ids.append(str(stored.id))
        return {**output, "document_ids": ids}
    if step.operator_type == "ENTITY_RESOLVE":
        return await persist_claims(session, run, output)
    if step.operator_type == "RECONCILE":
        return await reconcile(session, run, now)
    if step.operator_type == "MATERIALIZE":
        return await materialize(session, run, output, now)
    if step.operator_type == "EXPORT":
        from app.persistence.repositories.workspace import WorkspaceRepository

        version_id = run.metrics.get("dataset_version_id")
        if not version_id:
            raise ProofGridError(
                "EXPORT_VERSION_MISSING", "Export requires a finalized dataset version."
            )
        export = await WorkspaceRepository(session, run.project_id, now).create_export(
            UUID(version_id), output.get("format", "json")
        )
        return {"export_id": str(export.id), **export.data}
    if step.operator_type == "INDEX":
        session.add(
            OutboxEvent(
                project_id=run.project_id,
                aggregate_type="run",
                aggregate_id=run.id,
                event_type="dataset.index_requested",
                payload={"run_id": str(run.id)},
                status="PENDING",
            )
        )
    return output


async def persist_claims(
    session: AsyncSession, run: WorkflowRun, output: dict[str, Any]
) -> dict[str, Any]:
    # Identity allocation serialized within a workspace. Does not serialize HTTP/extraction.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"entities:{run.project_id}"},
    )
    drafts = [ClaimDraft.model_validate(raw) for raw in output.get("claims", [])]
    groups: dict[tuple[str, str], list[ClaimDraft]] = {}
    for draft in drafts:
        groups.setdefault((draft.entity_key, draft.raw_document_id), []).append(draft)
    claim_ids = []
    entity_ids = []
    for (name, _document_id), values in groups.items():
        website = next(
            (
                d.normalized_value
                for d in values
                if d.field_key == "website" and d.evidence.verified and not d.validation_flags
            ),
            "",
        )
        domains = {
            urlsplit(str(d.normalized_value)).hostname
            for d in values
            if d.field_key == "website" and d.evidence.verified and not d.validation_flags
        }
        if len(domains) > 1:
            website = ""
            for draft in values:
                draft.validation_flags.append("IDENTITY_AMBIGUOUS")
        identity = {"name": name, "website": website}
        stable_key = digest(
            {
                "name": normalized_name(name),
                "domain": urlsplit(str(website)).hostname or "",
                "source_without_domain": values[0].source_id if not website else None,
            }
        )
        entity = await session.scalar(
            select(Entity).where(
                Entity.project_id == run.project_id, Entity.stable_entity_key == stable_key
            )
        )
        if entity is None:
            entity = Entity(
                id=uuid4(),
                project_id=run.project_id,
                canonical_name=name[:255],
                stable_entity_key=stable_key,
                attributes={**identity, "resolution_reason": "EXACT_NORMALIZED_NAME_AND_DOMAIN"},
            )
            session.add(entity)
            await session.flush()
            candidates = list(
                (
                    await session.scalars(
                        select(Entity)
                        .where(
                            Entity.project_id == run.project_id,
                            Entity.id != entity.id,
                            Entity.canonical_name.ilike(name[:3] + "%"),
                        )
                        .limit(30)
                    )
                ).all()
            )
            for candidate in candidates:
                decision, features = identity_decision(
                    identity, {"name": candidate.canonical_name, **candidate.attributes}
                )
                if decision == "KEEP_SEPARATE":
                    continue
                source_id, target_id = sorted([entity.id, candidate.id])
                existing = await session.scalar(
                    select(EntityMatch).where(
                        EntityMatch.project_id == run.project_id,
                        EntityMatch.source_entity_id == source_id,
                        EntityMatch.target_entity_id == target_id,
                    )
                )
                if existing is None:
                    session.add(
                        EntityMatch(
                            project_id=run.project_id,
                            source_entity_id=source_id,
                            target_entity_id=target_id,
                            decision=decision,
                            signals=features,
                            reason={"rule": features["reason"]},
                        )
                    )
        # Human decisions affect subsequent snapshots, never rewrite historical claims.
        reviewed = await session.scalar(
            select(EntityMatch)
            .where(
                EntityMatch.project_id == run.project_id,
                EntityMatch.decision == "HUMAN_MERGE",
                (
                    (EntityMatch.source_entity_id == entity.id)
                    | (EntityMatch.target_entity_id == entity.id)
                ),
            )
            .limit(1)
        )
        entity_id = reviewed.source_entity_id if reviewed else entity.id
        entity_ids.append(str(entity_id))
        for draft in values:
            raw_id, source_id = UUID(draft.raw_document_id), UUID(draft.source_id)
            raw_doc = await session.scalar(
                select(RawDocument).where(
                    RawDocument.id == raw_id,
                    RawDocument.project_id == run.project_id,
                    RawDocument.workflow_run_id == run.id,
                    RawDocument.source_id == source_id,
                )
            )
            if raw_doc is None:
                raise ProofGridError(
                    "PROVENANCE_INVALID", "Claim does not belong to this run's raw evidence."
                )
            claim_hash = digest(
                {
                    "document": str(raw_id),
                    "entity": str(entity_id),
                    "field": draft.field_key,
                    "raw": draft.raw_value,
                    "extractor": "v1",
                }
            )
            claim = await session.scalar(
                select(Claim).where(Claim.workflow_run_id == run.id, Claim.claim_hash == claim_hash)
            )
            if claim is None:
                claim = Claim(
                    id=uuid4(),
                    project_id=run.project_id,
                    workflow_run_id=run.id,
                    raw_document_id=raw_id,
                    source_id=source_id,
                    entity_id=entity_id,
                    field_key=draft.field_key,
                    raw_value=draft.raw_value,
                    normalized_value=draft.normalized_value,
                    extraction_method=draft.extraction_method,
                    validation_flags=draft.validation_flags,
                    claim_hash=claim_hash,
                )
                session.add(claim)
                await session.flush()
                anchor = draft.evidence
                session.add(
                    EvidenceAnchor(
                        claim_id=claim.id,
                        raw_document_id=raw_id,
                        anchor_type=str(anchor.anchor_type),
                        locator=anchor.model_dump(mode="json"),
                        quoted_text=anchor.quote,
                        verification_status=str(anchor.status),
                        verified_at=raw_doc.retrieved_at if anchor.verified else None,
                    )
                )
            claim_ids.append(str(claim.id))
    return {
        "claim_ids": claim_ids,
        "entity_ids": sorted(set(entity_ids)),
        "metrics": {"claims_extracted": len(claim_ids), "entities_resolved": len(set(entity_ids))},
    }


async def reconcile(session: AsyncSession, run: WorkflowRun, now: datetime) -> dict[str, Any]:
    version = await session.get(WorkflowVersion, run.workflow_version_id)
    assert version
    schema_row = await session.get(DatasetSchema, version.dataset_schema_id)
    contract_row = await session.get(TrustContract, version.trust_contract_id)
    assert schema_row and contract_row
    schema = SchemaContract.model_validate(schema_row.schema_definition)
    contract = TrustPolicy.model_validate(contract_row.contract_definition)
    documents = {
        d.id: d
        for d in (
            await session.scalars(
                select(RawDocument)
                .where(
                    RawDocument.project_id == run.project_id, RawDocument.workflow_run_id == run.id
                )
                .limit(500)
            )
        ).all()
    }
    rows = (
        await session.execute(
            select(Claim, Source, EvidenceAnchor)
            .join(Source, Source.id == Claim.source_id)
            .join(EvidenceAnchor, EvidenceAnchor.claim_id == Claim.id)
            .where(Claim.project_id == run.project_id, Claim.workflow_run_id == run.id)
            .limit(10000)
        )
    ).all()
    grouped: dict[str, dict[str, list[TrustClaim]]] = {}
    for claim, source, anchor in rows:
        doc = documents[claim.raw_document_id]
        grouped.setdefault(str(claim.entity_id), {}).setdefault(claim.field_key, []).append(
            TrustClaim(
                id=str(claim.id),
                value=claim.normalized_value,
                domain=source.domain,
                content_hash=doc.content_hash,
                document_text=doc.content or "",
                first_party=bool(doc.retrieval_metadata.get("first_party")),
                verified=anchor.verified_at is not None,
                flags=claim.validation_flags,
                observed_at=doc.retrieved_at,
            )
        )
    # A review chooses a value for later snapshots, without deleting disagreement.
    # Match the selected assertion by source + value, because every run owns fresh claim IDs.
    reviewed = (
        await session.execute(
            select(Conflict, Claim)
            .join(Claim, Claim.id == Conflict.resolved_claim_id)
            .join(DatasetVersion, DatasetVersion.id == Conflict.dataset_version_id)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(
                Conflict.project_id == run.project_id,
                Conflict.status == "RESOLVED",
                Dataset.workflow_id == version.workflow_id,
            )
            .order_by(Conflict.resolved_at.desc())
            .limit(500)
        )
    ).all()
    overrides: dict[tuple[str, str], tuple[Conflict, Claim]] = {}
    for conflict, claim in reviewed:
        overrides.setdefault((str(claim.entity_id), claim.field_key), (conflict, claim))
    current_sources = {str(c.id): c.source_id for c, _, _ in rows}
    result: list[dict[str, Any]] = []
    for entity_id, fields in grouped.items():
        canonical = {
            field.key: canonicalize(fields.get(field.key, []), str(field.data_type), contract, now)
            for field in schema.fields
        }
        for key, cell in canonical.items():
            prior = overrides.get((entity_id, key))
            if not prior or cell["status"] != "CONFLICTING":
                continue
            decision, selected = prior
            eligible = next(
                (
                    c
                    for c in fields.get(key, [])
                    if c.verified
                    and not c.flags
                    and c.value == selected.normalized_value
                    and current_sources[c.id] == selected.source_id
                ),
                None,
            )
            if eligible:
                cell.update(
                    value=eligible.value,
                    selected_claim_id=eligible.id,
                    review_id=str(decision.id),
                    reason="HUMAN_DISPLAY_SELECTION_DISAGREEMENT_PRESERVED",
                )
        result.append({"entity_id": entity_id, "canonical": canonical})
    return {
        "rows": result,
        "metrics": {
            "conflicts_found": sum(
                c["status"] == "CONFLICTING" for row in result for c in row["canonical"].values()
            )
        },
    }


async def materialize(
    session: AsyncSession, run: WorkflowRun, output: dict[str, Any], now: datetime
) -> dict[str, Any]:
    from app.application.datasets.filters import matches_requirement
    from app.persistence.queries.queue import append_event

    workflow_version = await session.get(WorkflowVersion, run.workflow_version_id)
    assert workflow_version
    dataset = await session.scalar(
        select(Dataset).where(
            Dataset.project_id == run.project_id,
            Dataset.workflow_id == workflow_version.workflow_id,
        )
    )
    assert dataset
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": str(dataset.id)}
    )
    existing = await session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.workflow_run_id == run.id, DatasetVersion.project_id == run.project_id
        )
    )
    if existing:
        return {
            "metrics": {"dataset_version_id": str(existing.id), "records": existing.record_count}
        }
    spec = RequirementSpec.model_validate(workflow_version.planner_metadata["requirement_snapshot"])
    number = (
        int(
            await session.scalar(
                select(func.coalesce(func.max(DatasetVersion.version_number), 0)).where(
                    DatasetVersion.dataset_id == dataset.id
                )
            )
            or 0
        )
        + 1
    )
    version = DatasetVersion(
        id=uuid4(),
        project_id=run.project_id,
        dataset_id=dataset.id,
        dataset_schema_id=workflow_version.dataset_schema_id,
        workflow_run_id=run.id,
        version_number=number,
        status="FINALIZING",
        record_count=0,
    )
    session.add(version)
    await session.flush()
    trust_row = await session.get(TrustContract, workflow_version.trust_contract_id)
    assert trust_row
    policy = TrustPolicy.model_validate(trust_row.contract_definition)
    incomplete = False
    excluded = 0
    for row in output.get("rows", []):
        canonical = row["canonical"]
        data = {key: cell["value"] for key, cell in canonical.items()}
        if not matches_requirement(data, spec):
            continue
        entity_id = UUID(row["entity_id"])
        trust = {key: cell["status"] for key, cell in canonical.items()}
        missing_required = any(
            field.required and trust.get(field.key) in {"MISSING", "NEEDS_REVIEW"}
            for field in spec.fields
        )
        incomplete |= missing_required
        if policy.strict_required_fields and missing_required:
            excluded += 1
            continue
        for key, cell in canonical.items():
            selected = UUID(cell["selected_claim_id"]) if cell.get("selected_claim_id") else None
            session.add(
                CanonicalValue(
                    project_id=run.project_id,
                    dataset_version_id=version.id,
                    entity_id=entity_id,
                    field_key=key,
                    value=cell["value"],
                    trust_status=cell["status"],
                    selected_claim_id=selected,
                    provenance_summary=cell,
                )
            )
            if cell["status"] == "CONFLICTING":
                session.add(
                    Conflict(
                        project_id=run.project_id,
                        dataset_version_id=version.id,
                        entity_id=entity_id,
                        field_key=key,
                        details=cell,
                    )
                )
        incomplete |= any(
            field.required and trust.get(field.key) in {"MISSING", "NEEDS_REVIEW"}
            for field in spec.fields
        )
        session.add(
            DatasetVersionRecord(
                project_id=run.project_id,
                dataset_version_id=version.id,
                entity_id=entity_id,
                record_data=data,
                trust_summary=trust,
                record_hash=digest({"data": data, "trust": trust}),
            )
        )
        version.record_count += 1
        if version.record_count >= spec.limit:
            break
    version.status = "FINALIZED"
    session.add(
        OutboxEvent(
            project_id=run.project_id,
            aggregate_type="dataset_version",
            aggregate_id=version.id,
            event_type="dataset.version_created",
            payload={"dataset_id": str(dataset.id), "dataset_version_id": str(version.id)},
            status="PENDING",
        )
    )
    await append_event(
        session,
        run,
        "dataset.version_created",
        {
            "dataset_id": str(dataset.id),
            "dataset_version_id": str(version.id),
            "record_count": version.record_count,
        },
    )
    return {
        "metrics": {
            "dataset_id": str(dataset.id),
            "dataset_version_id": str(version.id),
            "records": version.record_count,
            "quality_incomplete": incomplete,
            "strict_rows_excluded": excluded,
        }
    }
