"""Domain models and candidate schemas for the Requirement Compiler."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
        default_factory=lambda: datetime.now(UTC),
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
    ambiguity_code: str = Field(min_length=1, description="Associated Ambiguity code")
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


class CandidateCompilationDraft(BaseModel):
    """Raw structured candidate emitted by AI provider before deterministic validation."""

    model_config = ConfigDict(extra="allow")

    entity_type: str = "company"
    goal: str
    fields: list[CandidateFieldSpec] = Field(default_factory=list)
    filters: list[CandidateFilterSpec] = Field(default_factory=list)
    geography: list[str] = Field(default_factory=list)
    time_window: DateRange | None = None
    source_hints: list[str] = Field(default_factory=list)
    limit: int = 50
    refresh: RefreshPolicy | None = None
    trust_preferences: CandidateTrustPreferences = Field(default_factory=CandidateTrustPreferences)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)

    # Sentinel fields for checking illicit PlanDAG / workflow operator injections
    plan_dag: Any | None = None
    nodes: Any | None = None
    operators: Any | None = None


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
    compiled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
