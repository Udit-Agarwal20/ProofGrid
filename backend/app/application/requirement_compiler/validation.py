"""Deterministic post-validation and semantic consistency rules for the Requirement Compiler.

Enforces:
LLM PROPOSES.
DETERMINISTIC CODE VALIDATES.
USER CONFIRMS.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError

from app.ai.contracts import ProviderMetadata
from app.application.requirement_compiler.errors import CompilerValidationError
from app.application.requirement_compiler.models import (
    Ambiguity,
    AmbiguitySeverity,
    CandidateCompilationDraft,
    ClarificationContext,
    ClarificationQuestion,
    CompilationOutcome,
    CompilerClarificationResult,
    CompilerMetadata,
    CompilerResult,
)
from app.application.requirement_compiler.prompts import REQUIREMENT_COMPILER_PROMPT_VERSION
from app.domain.contracts import (
    DatasetSchema,
    FieldSpec,
    FilterSpec,
    RequirementSpec,
    TrustContract,
)
from app.domain.enums import FieldDataType, FieldOrigin

# Regex matching lowercase snake_case machine identifiers
_FIELD_KEY_REGEX = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

# Disallowed internal/reserved field keys
_RESERVED_FIELD_KEYS = {
    "id",
    "raw_document_id",
    "source_id",
    "schema_hash",
    "__metadata__",
}


def _compute_schema_hash(fields: list[FieldSpec]) -> str:
    """Compute a stable, deterministic SHA-256 hash of dataset schema field definitions."""
    sorted_specs = sorted(
        [
            {
                "key": f.key,
                "data_type": str(f.data_type),
                "required": f.required,
                "origin": str(f.origin),
            }
            for f in fields
        ],
        key=lambda item: str(item["key"]),
    )
    serialized = json.dumps(sorted_specs, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def validate_compilation_draft(
    draft: CandidateCompilationDraft,
    provider_metadata: ProviderMetadata,
    reference_date: datetime | None = None,
    raw_prompt: str = "",
) -> CompilationOutcome:
    """Deterministically validate candidate provider output and construct the CompilationOutcome."""
    ref_dt = reference_date or datetime.now(UTC)
    ref_str = ref_dt.astimezone(UTC).strftime("%Y-%m-%d")

    # -------------------------------------------------------------------------
    # 1. Rejection of illicit PlanDAG / workflow operator injections
    # -------------------------------------------------------------------------
    if draft.plan_dag is not None or draft.nodes is not None or draft.operators is not None:
        raise CompilerValidationError(
            "PlanDAG or workflow operator injection detected in candidate output. "
            "Requirement Compiler must not emit execution plans."
        )

    # Check for unexpected extra fields from provider
    extra_fields = getattr(draft, "__pydantic_extra__", None)
    if extra_fields:
        for extra_key in extra_fields:
            if any(op.lower() in extra_key.lower() for op in ("plan", "node", "operator", "dag")):
                raise CompilerValidationError(
                    f"Illicit workflow planning field '{extra_key}' detected in candidate output."
                )

    # -------------------------------------------------------------------------
    # 2. Goal validation
    # -------------------------------------------------------------------------
    goal = draft.goal.strip() if draft.goal else ""
    if len(goal) < 3:
        raise CompilerValidationError("Candidate goal must be at least 3 characters.")

    # -------------------------------------------------------------------------
    # 3. Ambiguity & Clarification Questions validation
    # -------------------------------------------------------------------------
    ambiguities = list(draft.ambiguities)

    # Temporal / Date range consistency check
    if draft.time_window and draft.time_window.start and draft.time_window.end:
        start_str = draft.time_window.start
        end_str = draft.time_window.end
        if start_str > end_str:
            has_date_ambiguity = any(
                a.code in ("INVALID_DATE_RANGE", "CONTRADICTORY_DATE_RANGE") for a in ambiguities
            )
            if not has_date_ambiguity:
                ambiguities.append(
                    Ambiguity(
                        code="CONTRADICTORY_DATE_RANGE",
                        field_path="time_window",
                        message=f"Start date '{start_str}' cannot be after end date '{end_str}'.",
                        severity=AmbiguitySeverity.BLOCKING,
                        blocking=True,
                        possible_interpretations=["Inverted calendar bounds"],
                    )
                )

    validated_ambiguities: list[Ambiguity] = []
    ambiguity_map: dict[str, Ambiguity] = {}

    for amb in ambiguities:
        is_blocking = amb.blocking or (amb.severity == AmbiguitySeverity.BLOCKING)
        actual_severity = AmbiguitySeverity.BLOCKING if is_blocking else amb.severity
        validated_amb = Ambiguity(
            code=amb.code,
            field_path=amb.field_path,
            message=amb.message,
            severity=actual_severity,
            blocking=is_blocking,
            possible_interpretations=amb.possible_interpretations,
        )
        validated_ambiguities.append(validated_amb)
        ambiguity_map[amb.code] = validated_amb

    # Clarification questions must map to a known material ambiguity
    validated_questions: list[ClarificationQuestion] = []
    for cq in draft.clarification_questions:
        if cq.ambiguity_code not in ambiguity_map:
            raise CompilerValidationError(
                f"Clarification question '{cq.question_id}' references unknown ambiguity code '{cq.ambiguity_code}'."
            )
        matched_amb = ambiguity_map[cq.ambiguity_code]
        if matched_amb.severity == AmbiguitySeverity.INFO:
            raise CompilerValidationError(
                f"Clarification question '{cq.question_id}' generated for non-material INFO ambiguity '{cq.ambiguity_code}'. "
                "Clarification questions are reserved for material WARNING or BLOCKING ambiguities."
            )
        validated_questions.append(cq)

    # -------------------------------------------------------------------------
    # 4. Distinguish User Ambiguity from Provider Invalidity
    # -------------------------------------------------------------------------
    entity_type = draft.entity_type.strip() if draft.entity_type else ""
    has_blocking_entity_ambiguity = any(
        amb.blocking and (amb.code == "AMBIGUOUS_TARGET_ENTITY" or amb.field_path == "entity_type")
        for amb in validated_ambiguities
    )
    has_entity_clarification = any(
        cq.ambiguity_code in ambiguity_map
        and (
            cq.ambiguity_code == "AMBIGUOUS_TARGET_ENTITY"
            or ambiguity_map[cq.ambiguity_code].field_path == "entity_type"
        )
        for cq in validated_questions
    )

    if not entity_type:
        if has_blocking_entity_ambiguity and has_entity_clarification:
            # Genuine user blocking ambiguity: entity cannot be determined
            metadata = CompilerMetadata(
                compiler_version="1.0.0",
                prompt_version=REQUIREMENT_COMPILER_PROMPT_VERSION,
                provider_name=provider_metadata.provider_name,
                model_name=provider_metadata.model_name,
                scenario=provider_metadata.scenario,
                reference_date=ref_str,
            )
            partial_context = ClarificationContext(
                raw_prompt=raw_prompt or goal,
                detected_entity_type=None,
                detected_geography=draft.geography,
                detected_time_window=draft.time_window,
                candidate_fields=[f.key for f in draft.fields if f.key],
            )
            return CompilerClarificationResult(
                status="NEEDS_CLARIFICATION",
                ambiguities=validated_ambiguities,
                assumptions=list(draft.assumptions),
                clarification_questions=validated_questions,
                requires_confirmation=True,
                metadata=metadata,
                partial_context=partial_context,
            )
        # Provider omitted entity_type without user clarification ambiguity: Provider/Structural Invalidity!
        raise CompilerValidationError(
            "Candidate compilation has an empty entity_type without user clarification ambiguity. "
            "Provider failed to output an identifiable entity_type."
        )

    # If entity is present, but there is another user BLOCKING ambiguity with questions (e.g. contradictory dates)
    has_blocking_ambiguity = any(amb.blocking for amb in validated_ambiguities)
    if has_blocking_ambiguity and validated_questions:
        metadata = CompilerMetadata(
            compiler_version="1.0.0",
            prompt_version=REQUIREMENT_COMPILER_PROMPT_VERSION,
            provider_name=provider_metadata.provider_name,
            model_name=provider_metadata.model_name,
            scenario=provider_metadata.scenario,
            reference_date=ref_str,
        )
        partial_context = ClarificationContext(
            raw_prompt=raw_prompt or goal,
            detected_entity_type=entity_type,
            detected_geography=draft.geography,
            detected_time_window=draft.time_window,
            candidate_fields=[f.key for f in draft.fields if f.key],
        )
        return CompilerClarificationResult(
            status="NEEDS_CLARIFICATION",
            ambiguities=validated_ambiguities,
            assumptions=list(draft.assumptions),
            clarification_questions=validated_questions,
            requires_confirmation=True,
            metadata=metadata,
            partial_context=partial_context,
        )

    # -------------------------------------------------------------------------
    # 5. Deterministic FieldSpec & Schema validation (Complete Proposal)
    # -------------------------------------------------------------------------
    if not draft.fields:
        raise CompilerValidationError(
            "Dataset schema proposal must contain at least one field specification."
        )

    validated_fields: list[FieldSpec] = []
    seen_keys: set[str] = set()

    for cand_field in draft.fields:
        key = cand_field.key.strip() if cand_field.key else ""

        # Key regex validation
        if not _FIELD_KEY_REGEX.match(key):
            raise CompilerValidationError(
                f"Field key '{key}' is invalid. Must be lowercase snake_case (e.g. 'company_name')."
            )

        # Reserved keys check
        if key in _RESERVED_FIELD_KEYS:
            raise CompilerValidationError(
                f"Field key '{key}' is a reserved internal name and cannot be used in a dataset schema."
            )

        # Duplicate field key check
        if key in seen_keys:
            raise CompilerValidationError(
                f"Duplicate field key '{key}' detected in proposed dataset schema."
            )
        seen_keys.add(key)

        # Data type validation against canonical enum
        try:
            field_data_type = FieldDataType(cand_field.data_type)
        except ValueError:
            valid_types = [t.value for t in FieldDataType]
            raise CompilerValidationError(
                f"Unsupported field data_type '{cand_field.data_type}' for key '{key}'. "
                f"Allowed types: {valid_types}."
            ) from None

        # Origin validation
        try:
            field_origin = FieldOrigin(cand_field.origin)
        except ValueError:
            field_origin = FieldOrigin.USER

        try:
            spec = FieldSpec(
                key=key,
                label=cand_field.label.strip() or key,
                data_type=field_data_type,
                required=cand_field.required,
                origin=field_origin,
                description=cand_field.description.strip() if cand_field.description else None,
            )
            validated_fields.append(spec)
        except ValidationError as exc:
            raise CompilerValidationError(
                f"FieldSpec validation failed for key '{key}': {exc.errors()[0]['msg']}"
            ) from exc

    # Deterministic schema hash calculation
    schema_hash = _compute_schema_hash(validated_fields)
    schema_proposal = DatasetSchema(
        entity_type=entity_type,
        fields=validated_fields,
        schema_hash=schema_hash,
    )

    # -------------------------------------------------------------------------
    # 6. Filters & Cross-Object semantic consistency
    # -------------------------------------------------------------------------
    validated_filters: list[FilterSpec] = []
    for cand_filter in draft.filters:
        f_key = cand_filter.field_key.strip()
        if f_key not in seen_keys:
            raise CompilerValidationError(
                f"Filter references non-existent field key '{f_key}'. "
                f"All filtered fields must exist in proposed dataset schema."
            )

        allowed_operators = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "contains"}
        if cand_filter.operator not in allowed_operators:
            raise CompilerValidationError(
                f"Filter operator '{cand_filter.operator}' is not supported. "
                f"Allowed operators: {sorted(allowed_operators)}."
            )

        try:
            f_spec = FilterSpec(
                field_key=f_key,
                operator=cand_filter.operator,  # type: ignore[arg-type]
                value=cand_filter.value,
            )
            validated_filters.append(f_spec)
        except ValidationError as exc:
            raise CompilerValidationError(
                f"FilterSpec validation failed for '{f_key}': {exc.errors()[0]['msg']}"
            ) from exc

    # -------------------------------------------------------------------------
    # 7. TrustContract Proposal Validation
    # -------------------------------------------------------------------------
    tp = draft.trust_preferences
    if tp.max_pages < 1 or tp.max_pages > 500:
        raise CompilerValidationError(f"max_pages must be between 1 and 500 (got {tp.max_pages}).")
    if tp.max_browser_pages < 0 or tp.max_browser_pages > 50:
        raise CompilerValidationError(
            f"max_browser_pages must be between 0 and 50 (got {tp.max_browser_pages})."
        )
    if tp.max_llm_calls < 1 or tp.max_llm_calls > 500:
        raise CompilerValidationError(
            f"max_llm_calls must be between 1 and 500 (got {tp.max_llm_calls})."
        )
    if tp.max_run_seconds < 10 or tp.max_run_seconds > 600:
        raise CompilerValidationError(
            f"max_run_seconds must be between 10 and 600 (got {tp.max_run_seconds})."
        )
    if tp.max_estimated_cost_usd < Decimal("0.00"):
        raise CompilerValidationError(
            f"max_estimated_cost_usd cannot be negative (got {tp.max_estimated_cost_usd})."
        )

    try:
        trust_contract_proposal = TrustContract(
            require_evidence_anchor=tp.require_evidence_anchor,
            minimum_independent_sources=tp.minimum_independent_sources,
            prefer_first_party=tp.prefer_first_party,
            allow_secondary_sources=tp.allow_secondary_sources,
            allow_single_source_output=tp.allow_single_source_output,
            preserve_conflicts=tp.preserve_conflicts,
            strict_required_fields=tp.strict_required_fields,
            max_source_age_days=tp.max_source_age_days,
            max_pages=tp.max_pages,
            max_browser_pages=tp.max_browser_pages,
            max_llm_calls=tp.max_llm_calls,
            max_run_seconds=tp.max_run_seconds,
            max_estimated_cost_usd=tp.max_estimated_cost_usd,
        )
    except ValidationError as exc:
        raise CompilerValidationError(
            f"TrustContract validation failed: {exc.errors()[0]['msg']}"
        ) from exc

    # -------------------------------------------------------------------------
    # 8. RequirementSpec Construction
    # -------------------------------------------------------------------------
    try:
        requirement_spec = RequirementSpec(
            entity_type=entity_type,
            goal=goal,
            fields=validated_fields,
            filters=validated_filters,
            geography=draft.geography,
            time_window=draft.time_window,
            source_hints=draft.source_hints,
            limit=draft.limit,
            refresh=draft.refresh,
        )
    except ValidationError as exc:
        raise CompilerValidationError(
            f"RequirementSpec validation failed: {exc.errors()[0]['msg']}"
        ) from exc

    # -------------------------------------------------------------------------
    # 9. CompilerMetadata & Final CompilerResult
    # -------------------------------------------------------------------------
    metadata = CompilerMetadata(
        compiler_version="1.0.0",
        prompt_version=REQUIREMENT_COMPILER_PROMPT_VERSION,
        provider_name=provider_metadata.provider_name,
        model_name=provider_metadata.model_name,
        scenario=provider_metadata.scenario,
        reference_date=ref_str,
    )

    return CompilerResult(
        status="COMPILED",
        requirement_spec=requirement_spec,
        dataset_schema_proposal=schema_proposal,
        trust_contract_proposal=trust_contract_proposal,
        ambiguities=validated_ambiguities,
        assumptions=list(draft.assumptions),
        clarification_questions=validated_questions,
        requires_confirmation=True,  # ALWAYS True
        metadata=metadata,
    )
