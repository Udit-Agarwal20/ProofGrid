"""Domain models and candidate schemas for the Requirement Compiler."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.clock import utc_now
from app.domain.contracts import (
    DatasetSchema,
    DateRange,
    RefreshPolicy,
    RequirementSpec,
    TrustContract,
)


class CompilationContext(BaseModel):
    """Contextual and temporal parameters for requirement compilation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_date: datetime = Field(
        default_factory=utc_now,
        description="Temporal anchor date for evaluating relative expressions (e.g. 'last 18 months')",
    )


class AmbiguitySeverity(StrEnum):
    """Severity classification for requirement ambiguities."""

    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class Ambiguity(BaseModel):
    """Explicit typed finding of requirement underspecification or contradiction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1, description="Machine-readable code identifying ambiguity type")
    field_path: str | None = Field(default=None, description="Affected field or domain concept")
    message: str = Field(min_length=1, description="Clear description of the ambiguity")
    severity: AmbiguitySeverity = Field(description="Impact level of ambiguity")
    blocking: bool = Field(description="Whether this ambiguity blocks automated execution")
    possible_interpretations: list[str] = Field(
        default_factory=list,
        description="Candidate interpretations considered",
    )


class Assumption(BaseModel):
    """Explicit assumption adopted when requirement is under-specified but non-blocking."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1, description="Identifier for assumption rule")
    description: str = Field(
        min_length=1, description="Explicit statement of the adopted assumption"
    )
    affected_field: str | None = Field(default=None, description="Affected field or parameter")
    reversible: bool = Field(
        default=True, description="Whether human confirmation can easily override"
    )


class ClarificationQuestion(BaseModel):
    """Targeted question presented to the user to resolve a material ambiguity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str = Field(min_length=1, description="Unique question identifier")
    ambiguity_code: str = Field(
        min_length=1,
        description="Associated Ambiguity code. Must refer to a BLOCKING or WARNING ambiguity code, never an INFO ambiguity.",
    )
    question: str = Field(min_length=1, description="Specific, concise question text")
    options: list[str] = Field(default_factory=list, description="Structured choices if applicable")
    impact_summary: str = Field(min_length=1, description="Summary of how choice affects dataset")


class ClarificationContext(BaseModel):
    """Structured partial context extracted when compilation requires human clarification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_prompt: str
    detected_entity_type: str | None = None
    detected_geography: list[str] = Field(default_factory=list)
    detected_time_window: DateRange | None = None
    candidate_fields: list[str] = Field(default_factory=list)


class CandidateFieldSpec(BaseModel):
    """Candidate field specification proposed by AI provider prior to validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    label: str
    data_type: str
    required: bool = False
    origin: str = "user"
    description: str | None = None


class CandidateFilterSpec(BaseModel):
    """Candidate filter expression proposed by AI provider prior to validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field_key: str
    operator: str
    value: Any


class CandidateTrustPreferences(BaseModel):
    """Candidate trust and budget preferences proposed by provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    require_evidence_anchor: bool = True
    minimum_independent_sources: int = 1
    prefer_first_party: bool = True
    allow_secondary_sources: bool = True
    allow_single_source_output: bool = True
    preserve_conflicts: bool = True
    strict_required_fields: bool = False
    max_source_age_days: int | None = None
    max_pages: int = 60
    max_browser_pages: int = 5
    max_llm_calls: int = 80
    max_run_seconds: int = 180
    max_estimated_cost_usd: Decimal = Decimal("3.00")


class CandidateCompiledDraft(BaseModel):
    """Structured candidate proposed when requirement can be compiled into a valid dataset proposal."""

    model_config = ConfigDict(extra="allow")

    goal: str = Field(description="Normalized summary of user data requirement")
    entity_type: str = Field(default="company", description="Target entity type to extract")
    fields: list[CandidateFieldSpec] = Field(
        default_factory=list, description="Proposed schema fields"
    )
    filters: list[CandidateFilterSpec] = Field(
        default_factory=list, description="Semantic filters to apply"
    )
    geography: list[str] = Field(default_factory=list, description="Target geographic constraints")
    time_window: DateRange | None = Field(
        default=None, description="Explicit or relative date range, or null if no temporal bounds"
    )
    source_hints: list[str] = Field(default_factory=list, description="Suggested source categories")
    limit: int = Field(default=50, ge=1, le=1000, description="Max entities to acquire")
    refresh: RefreshPolicy | None = Field(
        default=None,
        description="Optional refresh policy. Emit null if no recurring refresh is requested.",
    )
    trust_preferences: CandidateTrustPreferences = Field(
        default_factory=CandidateTrustPreferences,
        description="Trust, corroboration, and execution budget preferences",
    )
    ambiguities: list[Ambiguity] = Field(
        default_factory=list, description="Documented non-blocking ambiguities"
    )
    assumptions: list[Assumption] = Field(
        default_factory=list, description="Explicit modeling assumptions"
    )
    clarification_questions: list[ClarificationQuestion] = Field(
        default_factory=list, description="Questions for WARNING ambiguities if applicable"
    )


class CandidateClarificationDraft(BaseModel):
    """Small structured candidate proposed when a BLOCKING ambiguity prevents compilation."""

    model_config = ConfigDict(extra="allow")

    ambiguities: list[Ambiguity] = Field(
        default_factory=list, description="Surfaced ambiguities, at least one must be BLOCKING"
    )
    assumptions: list[Assumption] = Field(
        default_factory=list, description="Explicit assumptions adopted"
    )
    clarification_questions: list[ClarificationQuestion] = Field(
        default_factory=list,
        description="Targeted questions to resolve material BLOCKING ambiguities. Never ask questions for INFO ambiguities.",
    )
    detected_entity_type: str | None = Field(
        default=None, description="Tentative entity type if detected"
    )
    detected_geography: list[str] = Field(
        default_factory=list, description="Detected geographic references"
    )
    detected_time_window: DateRange | None = Field(
        default=None, description="Detected temporal bounds if identifiable"
    )
    candidate_fields: list[str] = Field(
        default_factory=list, description="Keywords or fields identifiable from user prompt"
    )


class CandidateCompilerEnvelope(BaseModel):
    """Branch-specific provider candidate envelope.

    Aligns provider generation with ProofGrid's two-outcome architecture:
    - COMPILED: candidate proposal with schema and trust preferences.
    - NEEDS_CLARIFICATION: lightweight clarification questions for blocking ambiguities.

    Enforces the XOR invariant: exactly one of compiled or clarification is non-null.
    """

    model_config = ConfigDict(extra="allow")

    outcome_type: Literal["COMPILED", "NEEDS_CLARIFICATION"] = Field(
        description="Indicates whether requirement can be compiled or requires user clarification"
    )
    requires_confirmation: Literal[True] = Field(
        default=True,
        description="Always True. Confirmation boundary is mandatory.",
    )
    compiled: CandidateCompiledDraft | None = Field(
        default=None,
        description="Populate when outcome_type is COMPILED. Must be null when NEEDS_CLARIFICATION.",
    )
    clarification: CandidateClarificationDraft | None = Field(
        default=None,
        description="Populate when outcome_type is NEEDS_CLARIFICATION. Must be null when COMPILED.",
    )


# Backward-compatible alias for existing code
CandidateCompilationDraft = CandidateCompiledDraft


class CompilerMetadata(BaseModel):
    """Audit and reproducibility metadata for requirement compilation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    compiler_version: str = "1.0.0"
    prompt_version: str = "requirement-compiler-v1"
    provider_name: str
    model_name: str
    scenario: str | None = None
    reference_date: str = Field(
        description="ISO-8601 temporal anchor date used for evaluating relative expressions"
    )
    compiled_at: datetime = Field(default_factory=utc_now)


class CompilerResult(BaseModel):
    """Complete, validated outcome of the Requirement Compiler."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["COMPILED"] = "COMPILED"
    requirement_spec: RequirementSpec
    dataset_schema_proposal: DatasetSchema
    trust_contract_proposal: TrustContract
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    requires_confirmation: bool = Field(
        default=True,
        description="Always True. Output must be confirmed by user before execution.",
    )
    metadata: CompilerMetadata

    @property
    def has_blocking_ambiguity(self) -> bool:
        """Indicates whether any ambiguity blocks execution."""
        return any(a.blocking for a in self.ambiguities)


class CompilerClarificationResult(BaseModel):
    """Outcome when genuine user ambiguity blocks construction of a valid RequirementSpec."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["NEEDS_CLARIFICATION"] = "NEEDS_CLARIFICATION"
    ambiguities: list[Ambiguity] = Field(min_length=1)
    assumptions: list[Assumption] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(min_length=1)
    requires_confirmation: bool = Field(
        default=True,
        description="Always True. Clarification must be provided before schema proposal can proceed.",
    )
    metadata: CompilerMetadata
    partial_context: ClarificationContext | None = None

    @property
    def has_blocking_ambiguity(self) -> bool:
        """Indicates whether any ambiguity blocks execution."""
        return any(a.blocking for a in self.ambiguities)


CompilationOutcome = CompilerResult | CompilerClarificationResult
