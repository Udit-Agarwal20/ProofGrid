"""Application service orchestrating requirement compilation and draft persistence."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.ai.exceptions import AIProviderError, AIProviderTimeoutError
from app.ai.provider import StructuredGenerationProvider
from app.application.requirement_compiler.errors import (
    CompilerProviderError,
    CompilerValidationError,
)
from app.application.requirement_compiler.models import (
    CandidateCompilationDraft,
    CompilationContext,
    CompilationOutcome,
    CompilerResult,
)
from app.application.requirement_compiler.prompts import build_compiler_request
from app.application.requirement_compiler.validation import validate_compilation_draft
from app.db.models.requirement import DatasetSchema, Requirement, TrustContract
from app.persistence.errors import PersistenceConflictError
from app.persistence.repositories.outbox import OutboxEventCreate
from app.persistence.unit_of_work import AbstractUnitOfWork


class RequirementCompiler:
    """Orchestrates structured natural-language requirement compilation.

    Enforces the core architectural doctrine:
    LLM PROPOSES.
    DETERMINISTIC CODE VALIDATES.
    USER CONFIRMS.
    """

    def __init__(
        self,
        provider: StructuredGenerationProvider,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._clock = clock or (lambda: datetime.now(UTC))

    async def compile(
        self,
        user_prompt: str,
        context: CompilationContext | None = None,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CompilationOutcome:
        """Compile a natural language user data request into a validated outcome.

        1. Input normalization & guard.
        2. Structured provider request assembly with temporal reference anchor.
        3. Provider candidate generation.
        4. Deterministic post-validation and semantic consistency checks.
        5. Discriminated outcome: CompilerResult vs CompilerClarificationResult.
        6. Human confirmation boundary enforced.
        """
        # 1. Input normalization & guard
        normalized_prompt = user_prompt.strip()
        if not normalized_prompt:
            raise CompilerValidationError("User prompt cannot be empty or whitespace.")

        # 2. Build structured generation request with temporal context
        comp_context = context or CompilationContext(reference_date=self._clock())
        request = build_compiler_request(
            user_prompt=normalized_prompt,
            context=comp_context,
            scenario=scenario,
            extra_metadata=metadata,
        )

        # 3. Invoke provider adapter
        try:
            candidate_draft, provider_metadata = await self._provider.generate_structured(
                request=request,
                output_schema=CandidateCompilationDraft,
            )
        except AIProviderTimeoutError as exc:
            raise CompilerProviderError(f"Provider invocation timed out: {exc}") from exc
        except AIProviderError as exc:
            raise CompilerProviderError(f"Provider invocation failed: {exc}") from exc
        except Exception as exc:
            raise CompilerProviderError(f"Unexpected provider error: {exc}") from exc

        # 4. Deterministic post-validation and semantic consistency
        outcome = validate_compilation_draft(
            draft=candidate_draft,
            provider_metadata=provider_metadata,
            reference_date=comp_context.reference_date,
            raw_prompt=normalized_prompt,
        )

        # 5. Confirmation boundary is enforced (always True)
        assert outcome.requires_confirmation is True, "requires_confirmation must be True"

        return outcome

    async def _stage_draft(
        self,
        uow: AbstractUnitOfWork,
        project_id: uuid.UUID,
        original_prompt: str,
        compiler_result: CompilerResult,
        requirement_id: uuid.UUID | None = None,
    ) -> tuple[Requirement, DatasetSchema, TrustContract]:
        """Stage compiled draft records into an active Unit of Work session."""
        req_id = requirement_id or uuid.uuid4()

        if requirement_id is not None:
            existing_req = await uow.requirements.get_requirement(req_id)
            if existing_req is not None:
                existing_req.original_prompt = original_prompt
                existing_req.requirement_spec = compiler_result.requirement_spec.model_dump(
                    mode="json"
                )
                existing_req.status = "COMPILED"
                req_model = existing_req
            else:
                req_model = Requirement(
                    id=req_id,
                    project_id=project_id,
                    original_prompt=original_prompt,
                    requirement_spec=compiler_result.requirement_spec.model_dump(mode="json"),
                    status="COMPILED",
                )
                uow.requirements.add_requirement(req_model)
        else:
            req_model = Requirement(
                id=req_id,
                project_id=project_id,
                original_prompt=original_prompt,
                requirement_spec=compiler_result.requirement_spec.model_dump(mode="json"),
                status="COMPILED",
            )
            uow.requirements.add_requirement(req_model)

        # Determine version number: preserve historical versions
        latest_schema = await uow.requirements.get_latest_dataset_schema(req_id)
        version_number = (latest_schema.version_number + 1) if latest_schema else 1

        schema_id = compiler_result.dataset_schema_proposal.id
        if version_number > 1 or (await uow.requirements.get_dataset_schema(schema_id)) is not None:
            schema_id = uuid.uuid4()

        # Propose DatasetSchema
        schema_model = DatasetSchema(
            id=schema_id,
            project_id=project_id,
            requirement_id=req_id,
            version_number=version_number,
            schema_definition=compiler_result.dataset_schema_proposal.model_dump(mode="json"),
        )
        uow.requirements.add_dataset_schema(schema_model)

        # Propose TrustContract (approved_at=None)
        trust_model = TrustContract(
            id=uuid.uuid4(),
            project_id=project_id,
            requirement_id=req_id,
            dataset_schema_id=schema_model.id,
            version_number=version_number,
            contract_definition=compiler_result.trust_contract_proposal.model_dump(mode="json"),
            approved_at=None,  # Crucial: Unapproved proposal
        )
        uow.requirements.add_trust_contract(trust_model)

        # Enqueue transactional outbox event
        outbox_event = OutboxEventCreate(
            project_id=project_id,
            aggregate_type="requirement",
            aggregate_id=req_id,
            event_type="requirement.compiled",
            payload={
                "requirement_id": str(req_id),
                "dataset_schema_id": str(schema_model.id),
                "trust_contract_id": str(trust_model.id),
                "version_number": version_number,
                "requires_confirmation": True,
                "has_blocking_ambiguity": compiler_result.has_blocking_ambiguity,
            },
        )
        uow.outbox.enqueue(outbox_event)

        return req_model, schema_model, trust_model

    async def persist_compilation_draft(
        self,
        uow: AbstractUnitOfWork | Callable[[], AbstractUnitOfWork],
        project_id: uuid.UUID,
        original_prompt: str,
        compiler_result: CompilerResult,
        requirement_id: uuid.UUID | None = None,
        max_attempts: int = 3,
    ) -> tuple[Requirement, DatasetSchema, TrustContract]:
        """Atomically persist a compiled draft using the persistence Unit of Work.

        Maintains strict boundaries:
        - Only complete CompilerResult proposals may be persisted. Incomplete clarification outcomes are rejected.
        - Requirement status is 'COMPILED' (unaccepted).
        - TrustContract approved_at is None (unapproved).
        - Enqueues an outbox event recording the compilation.
        - Previous historical versions are preserved (version_number increments).
        - If a callable factory is provided, retries on version allocation uniqueness race up to max_attempts.
        """
        if not isinstance(compiler_result, CompilerResult):
            raise CompilerValidationError(
                "Cannot persist an incomplete compilation outcome requiring clarification. "
                "Only complete CompilerResult proposals may be persisted as COMPILED."
            )

        if callable(uow):
            for attempt in range(max_attempts):
                active_uow = uow()
                async with active_uow:
                    req_model, schema_model, trust_model = await self._stage_draft(
                        uow=active_uow,
                        project_id=project_id,
                        original_prompt=original_prompt,
                        compiler_result=compiler_result,
                        requirement_id=requirement_id,
                    )
                    try:
                        await active_uow.commit()
                        return req_model, schema_model, trust_model
                    except PersistenceConflictError as exc:
                        err_msg = str(exc).lower()
                        is_version_conflict = (
                            "version" in err_msg
                            or "uq_dataset_schemas_requirement_version" in err_msg
                            or "uq_trust_contracts_requirement_version" in err_msg
                        )
                        if not is_version_conflict:
                            raise
                        if attempt < max_attempts - 1:
                            continue
                        raise PersistenceConflictError(
                            f"Failed to persist draft after {max_attempts} attempts due to concurrent version allocation conflicts."
                        ) from exc

            raise PersistenceConflictError(
                f"Failed to persist draft after {max_attempts} attempts due to concurrent version allocation conflicts."
            )

        # Fallback when active UnitOfWork instance is passed directly
        return await self._stage_draft(
            uow=uow,
            project_id=project_id,
            original_prompt=original_prompt,
            compiler_result=compiler_result,
            requirement_id=requirement_id,
        )
