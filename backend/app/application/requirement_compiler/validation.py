"""Deterministic post-validation and semantic consistency rules for the Requirement Compiler.

Enforces:
LLM PROPOSES.
DETERMINISTIC CODE VALIDATES.
USER CONFIRMS.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.ai.contracts import ProviderMetadata
from app.application.requirement_compiler.errors import CompilerValidationError
from app.application.requirement_compiler.models import (
    Ambiguity,
    AmbiguitySeverity,
    CandidateClarificationDraft,
    CandidateCompilationDraft,
    CandidateCompilerEnvelope,
    ClarificationContext,
    ClarificationQuestion,
    CompilationOutcome,
    CompilerClarificationResult,
    CompilerMetadata,
    CompilerResult,
)
from app.application.requirement_compiler.prompts import REQUIREMENT_COMPILER_PROMPT_VERSION
from app.domain.clock import utc_now
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


def _check_sentinel_injections(obj: Any, label: str) -> None:
    """Reject illicit PlanDAG / workflow operator injections on candidate objects."""
    if (
        getattr(obj, "plan_dag", None) is not None
        or getattr(obj, "nodes", None) is not None
        or getattr(obj, "operators", None) is not None
    ):
        raise CompilerValidationError(
            f"PlanDAG or workflow operator injection detected in {label}. "
            "Requirement Compiler must not emit execution plans."
        )

    extra_fields = getattr(obj, "__pydantic_extra__", None)
    if extra_fields:
        for extra_key in extra_fields:
            if any(op.lower() in extra_key.lower() for op in ("plan", "node", "operator", "dag")):
                raise CompilerValidationError(
                    f"Illicit workflow planning field '{extra_key}' detected in {label}."
                )


def validate_compilation_draft(
    draft: CandidateCompilerEnvelope | CandidateCompilationDraft,
    provider_metadata: ProviderMetadata,
    reference_date: datetime | None = None,
    raw_prompt: str = "",
) -> CompilationOutcome:
    """Deterministically validate candidate provider output and construct the CompilationOutcome.

    Supports branch-specific CandidateCompilerEnvelope and backwards-compatible CandidateCompilationDraft.
    Enforces the XOR invariant:
    - COMPILED: compiled must not be null; clarification must be null.
    - NEEDS_CLARIFICATION: clarification must not be null; compiled must be null.
    """
    ref_dt = reference_date or utc_now()
    ref_str = ref_dt.astimezone(UTC).strftime("%Y-%m-%d")

    # -------------------------------------------------------------------------
    # 1. Normalize into CandidateCompilerEnvelope if legacy draft passed
    # -------------------------------------------------------------------------
    if not isinstance(draft, CandidateCompilerEnvelope):
        # Legacy monolithic draft adapter
        _check_sentinel_injections(draft, "candidate draft")
        has_blocking = any(
            a.blocking or (a.severity == AmbiguitySeverity.BLOCKING) for a in draft.ambiguities
        )
        if not draft.entity_type or has_blocking:
            envelope = CandidateCompilerEnvelope(
                outcome_type="NEEDS_CLARIFICATION",
                requires_confirmation=True,
                compiled=None,
                clarification=CandidateClarificationDraft(
                    ambiguities=draft.ambiguities,
                    assumptions=draft.assumptions,
                    clarification_questions=draft.clarification_questions,
                    detected_entity_type=draft.entity_type or None,
                    detected_geography=draft.geography,
                    detected_time_window=draft.time_window,
                    candidate_fields=[f.key for f in draft.fields if f.key],
                ),
            )
        else:
            envelope = CandidateCompilerEnvelope(
                outcome_type="COMPILED",
                requires_confirmation=True,
                compiled=draft,
                clarification=None,
            )
    else:
        envelope = draft

    # -------------------------------------------------------------------------
    # 2. Check Sentinel Injections & Confirmation on Envelope
    # -------------------------------------------------------------------------
    _check_sentinel_injections(envelope, "candidate envelope")

    if envelope.requires_confirmation is not True:
        raise CompilerValidationError("Candidate envelope requires_confirmation must be True.")

    # -------------------------------------------------------------------------
    # 3. Enforce XOR Invariant between compiled and clarification branches
    # -------------------------------------------------------------------------
    if envelope.outcome_type == "COMPILED":
        if envelope.compiled is None:
            raise CompilerValidationError(
                "Candidate envelope with outcome_type 'COMPILED' must have non-null 'compiled' draft."
            )
        if envelope.clarification is not None:
            raise CompilerValidationError(
                "Candidate envelope with outcome_type 'COMPILED' must have null 'clarification' draft."
            )
    elif envelope.outcome_type == "NEEDS_CLARIFICATION":
        if envelope.clarification is None:
            raise CompilerValidationError(
                "Candidate envelope with outcome_type 'NEEDS_CLARIFICATION' must have non-null 'clarification' draft."
            )
        if envelope.compiled is not None:
            raise CompilerValidationError(
                "Candidate envelope with outcome_type 'NEEDS_CLARIFICATION' must have null 'compiled' draft."
            )
    else:
        raise CompilerValidationError(
            f"Invalid envelope outcome_type '{envelope.outcome_type}'. Must be 'COMPILED' or 'NEEDS_CLARIFICATION'."
        )

    # -------------------------------------------------------------------------
    # 4. Branch A: NEEDS_CLARIFICATION
    # -------------------------------------------------------------------------
    if envelope.outcome_type == "NEEDS_CLARIFICATION":
        clar = envelope.clarification
        assert clar is not None
        _check_sentinel_injections(clar, "clarification draft")

        ambiguities = list(clar.ambiguities)
        if not ambiguities:
            raise CompilerValidationError(
                "Candidate clarification branch must contain at least one ambiguity."
            )

        # Temporal / Date range consistency check if detected time window exists
        if (
            clar.detected_time_window
            and clar.detected_time_window.start
            and clar.detected_time_window.end
        ):
            start_str = clar.detected_time_window.start
            end_str = clar.detected_time_window.end
            if start_str > end_str:
                has_date_ambiguity = any(
                    a.code in ("INVALID_DATE_RANGE", "CONTRADICTORY_DATE_RANGE")
                    for a in ambiguities
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

        # Clarification branch MUST have at least one BLOCKING ambiguity
        has_blocking = any(a.blocking for a in validated_ambiguities)
        if not has_blocking:
            raise CompilerValidationError(
                "Candidate clarification branch requires at least one BLOCKING ambiguity."
            )

        # Clarification questions validation
        if not clar.clarification_questions:
            raise CompilerValidationError(
                "Candidate clarification branch requires at least one clarification question."
            )

        if len(clar.clarification_questions) > 3:
            raise CompilerValidationError("At most three decision-critical questions are allowed.")
        validated_questions: list[ClarificationQuestion] = []
        for cq in clar.clarification_questions:
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

        metadata = CompilerMetadata(
            compiler_version="1.0.0",
            prompt_version=REQUIREMENT_COMPILER_PROMPT_VERSION,
            provider_name=provider_metadata.provider_name,
            model_name=provider_metadata.model_name,
            scenario=provider_metadata.scenario,
            reference_date=ref_str,
        )
        partial_context = ClarificationContext(
            raw_prompt=raw_prompt,
            detected_entity_type=clar.detected_entity_type,
            detected_geography=clar.detected_geography,
            detected_time_window=clar.detected_time_window,
            candidate_fields=clar.candidate_fields,
        )
        return CompilerClarificationResult(
            status="NEEDS_CLARIFICATION",
            ambiguities=validated_ambiguities,
            assumptions=list(clar.assumptions),
            clarification_questions=validated_questions,
            requires_confirmation=True,
            metadata=metadata,
            partial_context=partial_context,
        )

    # -------------------------------------------------------------------------
    # 5. Branch B: COMPILED
    # -------------------------------------------------------------------------
    comp = envelope.compiled
    assert comp is not None
    _check_sentinel_injections(comp, "compiled draft")

    # Goal validation
    goal = comp.goal.strip() if comp.goal else ""
    if len(goal) < 3:
        raise CompilerValidationError("Candidate goal must be at least 3 characters.")

    # Ambiguity & Clarification Questions validation
    ambiguities = list(comp.ambiguities)
    if comp.time_window and comp.time_window.start and comp.time_window.end:
        start_str = comp.time_window.start
        end_str = comp.time_window.end
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

    validated_ambiguities = []
    ambiguity_map = {}
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

    # In COMPILED branch, no unresolved BLOCKING ambiguities may remain
    if any(a.blocking for a in validated_ambiguities):
        raise CompilerValidationError(
            "Candidate proposal cannot be COMPILED with unresolved BLOCKING ambiguities. "
            "Use outcome_type 'NEEDS_CLARIFICATION'."
        )

    validated_questions = []
    for cq in comp.clarification_questions:
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

    if len(validated_questions) > 3:
        raise CompilerValidationError("At most three decision-critical questions are allowed.")
    explicit_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", raw_prompt)
    if (
        len(explicit_dates) == 2
        and "between" in raw_prompt.lower()
        and (
            not comp.time_window
            or comp.time_window.start != explicit_dates[0]
            or comp.time_window.end != explicit_dates[1]
        )
    ):
        raise CompilerValidationError("Explicit date boundaries must be preserved exactly.")
    relative = re.search(r"last (\d+) months", raw_prompt, re.I)
    if relative and not explicit_dates:
        months = int(relative[1])
        year, month_index = divmod(ref_dt.year * 12 + ref_dt.month - 1 - months, 12)
        if not 1 <= year <= 9999:
            raise CompilerValidationError(
                "Relative date range is outside supported calendar bounds."
            )
        day = min(ref_dt.day, calendar.monthrange(year, month_index + 1)[1])
        start = f"{year:04d}-{month_index + 1:02d}-{day:02d}"
        if (
            not comp.time_window
            or comp.time_window.start != start
            or comp.time_window.end != ref_str
        ):
            raise CompilerValidationError("Relative dates must use the supplied reference date.")

    # Entity type validation
    entity_type = comp.entity_type.strip() if comp.entity_type else ""
    if not entity_type:
        raise CompilerValidationError(
            "Candidate draft contains empty entity_type without user clarification ambiguity. "
            "For unknown or ambiguous entity types, use outcome_type 'NEEDS_CLARIFICATION'."
        )

    # FieldSpec & Schema validation
    if not comp.fields:
        raise CompilerValidationError(
            "Dataset schema proposal must contain at least one field specification."
        )

    validated_fields: list[FieldSpec] = []
    seen_keys: set[str] = set()

    for cand_field in comp.fields:
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

    # Filters & Cross-Object semantic consistency
    validated_filters: list[FilterSpec] = []
    for cand_filter in comp.filters:
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

    # TrustContract Proposal Validation
    tp = comp.trust_preferences
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

    # RequirementSpec Construction
    try:
        requirement_spec = RequirementSpec(
            entity_type=entity_type,
            goal=goal,
            fields=validated_fields,
            filters=validated_filters,
            geography=comp.geography,
            time_window=comp.time_window,
            source_hints=comp.source_hints,
            limit=comp.limit,
            refresh=comp.refresh,
        )
    except ValidationError as exc:
        raise CompilerValidationError(
            f"RequirementSpec validation failed: {exc.errors()[0]['msg']}"
        ) from exc

    # CompilerMetadata & Final CompilerResult
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
        assumptions=list(comp.assumptions),
        clarification_questions=validated_questions,
        requires_confirmation=True,  # ALWAYS True
        metadata=metadata,
    )
