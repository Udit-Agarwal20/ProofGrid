"""Domain contracts for ProofGrid.

Frozen/immutable Pydantic v2 models modeling the core data invariants:
RequirementSpec, TrustContract, PlanDAG, Claim, Entity, DatasetSchema.
"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.clock import utc_now
from app.domain.enums import (
    EvidenceStatus,
    EvidenceType,
    FieldDataType,
    FieldOrigin,
    OperatorType,
    TrustStatus,
)

# Regular expression enforcing snake_case field identifiers
_FIELD_KEY_REGEX = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

# Disallowed parameter keys in PlanNode to forbid arbitrary code execution
_FORBIDDEN_PLAN_PARAM_KEYS = {
    "code",
    "python",
    "script",
    "command",
    "cmd",
    "exec",
    "eval",
    "import_path",
    "function",
    "module",
    "lambda",
}


class DomainBaseModel(BaseModel):
    """Base immutable domain model with strict validation."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        use_enum_values=True,
    )


class FieldSpec(DomainBaseModel):
    """Specification of a field/column within a dataset schema."""

    key: str = Field(description="Normalized unique identifier for the field")
    label: str = Field(description="Human-readable label for grid display")
    data_type: FieldDataType = Field(description="Strong data type")
    required: bool = Field(default=False, description="Whether field is mandatory")
    origin: FieldOrigin = Field(
        default=FieldOrigin.USER, description="User-specified vs AI-inferred"
    )
    description: str | None = Field(default=None, description="Semantic description")

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not _FIELD_KEY_REGEX.match(value):
            raise ValueError(
                f"Field key '{value}' is invalid. Must be lowercase snake_case (e.g. 'company_name')."
            )
        return value


class FilterSpec(DomainBaseModel):
    """Filter expression declared in RequirementSpec."""

    field_key: str
    operator: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "contains"]
    value: Any


class DateRange(DomainBaseModel):
    """Explicit calendar bounds for time-scoped requirements."""

    start: str | None = None  # ISO 8601 YYYY-MM-DD
    end: str | None = None  # ISO 8601 YYYY-MM-DD


class RefreshPolicy(DomainBaseModel):
    """Configuration for living dataset refresh."""

    frequency: Literal["daily", "weekly", "monthly", "manual"] = "manual"
    enabled: bool = False


class RequirementSpec(DomainBaseModel):
    """Compiled, machine-readable requirement for a dataset."""

    version: Literal["1.0"] = "1.0"
    entity_type: str = Field(default="company", min_length=1)
    goal: str = Field(min_length=3, description="High-level business objective")
    fields: list[FieldSpec] = Field(min_length=1)
    filters: list[FilterSpec] = Field(default_factory=list)
    geography: list[str] = Field(default_factory=list)
    time_window: DateRange | None = None
    source_hints: list[str] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=500)
    refresh: RefreshPolicy | None = None


class TrustContract(DomainBaseModel):
    """User-visible quality, policy, and budget constraints."""

    version: Literal["1.0"] = "1.0"
    require_evidence_anchor: bool = Field(
        default=True, description="Claims must possess verified anchors"
    )
    minimum_independent_sources: int = Field(
        default=1, ge=1, le=5, description="Independent source clusters"
    )
    prefer_first_party: bool = Field(default=True, description="Prefer direct corporate sources")
    allow_secondary_sources: bool = Field(default=True)
    allow_single_source_output: bool = Field(default=True)
    preserve_conflicts: bool = Field(
        default=True, description="Never discard competing valid claims"
    )
    strict_required_fields: bool = Field(default=False)
    max_source_age_days: int | None = Field(default=None, ge=1)
    max_search_queries: int = Field(default=5, ge=1, le=20)
    max_pages: int = Field(default=60, ge=1, le=500)
    max_browser_pages: int = Field(default=5, ge=0, le=50)
    max_llm_calls: int = Field(default=80, ge=1, le=500)
    max_run_seconds: int = Field(default=180, ge=10, le=600)
    max_estimated_cost_usd: Decimal = Field(default=Decimal("3.00"), ge=Decimal("0.00"))


class ExecutionConstraints(DomainBaseModel):
    """Execution bounds for a specific PlanNode."""

    timeout_seconds: int = Field(default=60, ge=1, le=600)
    max_retries: int = Field(default=2, ge=0, le=5)


class PlanNode(DomainBaseModel):
    """Declarative node within a PlanDAG. Arbitrary executable code is strictly forbidden."""

    id: str = Field(min_length=1, max_length=64, description="Unique node ID in graph")
    operator: OperatorType = Field(description="Must match fixed OperatorType registry")
    depends_on: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    critical: bool = Field(default=True)
    constraints: ExecutionConstraints = Field(default_factory=ExecutionConstraints)

    @field_validator("params")
    @classmethod
    def validate_params(cls, params: dict[str, Any]) -> dict[str, Any]:
        # Disallow arbitrary code execution fields
        for key in params:
            if key.lower() in _FORBIDDEN_PLAN_PARAM_KEYS:
                raise ValueError(
                    f"Forbidden parameter '{key}' in PlanNode. Arbitrary code is not permitted."
                )
        return params


class PlanDAG(DomainBaseModel):
    """Immutable declarative execution graph."""

    version: Literal["1.0"] = "1.0"
    nodes: list[PlanNode] = Field(min_length=1)
    rationale: list[str] = Field(default_factory=list)
    expected_pages: int = Field(default=0, ge=0)
    expected_browser_pages: int = Field(default=0, ge=0)
    expected_llm_calls: int = Field(default=0, ge=0)


class EvidenceAnchor(DomainBaseModel):
    """Deterministic anchor linking a claim to its stored RawDocument representation."""

    anchor_type: EvidenceType
    status: EvidenceStatus = EvidenceStatus.EXACT
    quote: str | None = Field(default=None, description="Extracted text span")
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    json_pointer: str | None = Field(default=None, description="RFC 6901 pointer for JSON")
    dom_selector: str | None = Field(default=None, description="CSS/XPath selector for DOM")
    field_path: str | None = Field(default=None, description="Structured key path")
    verified: bool = Field(default=False)

    @field_validator("char_end")
    @classmethod
    def validate_span(cls, char_end: int | None, info: Any) -> int | None:
        char_start = info.data.get("char_start")
        if char_start is not None and char_end is not None and char_end < char_start:
            raise ValueError("char_end cannot be less than char_start")
        return char_end


class Claim(DomainBaseModel):
    """Immutable, append-only assertion by a source about an entity field."""

    id: UUID = Field(default_factory=uuid4)
    entity_candidate_key: str = Field(min_length=1)
    field_key: str = Field(min_length=1)
    raw_value: Any = Field(description="Unprocessed value as observed in source")
    normalized_value: Any | None = Field(
        default=None, description="Typed value after FieldPolicy normalization"
    )
    source_id: UUID = Field(default_factory=uuid4)
    raw_document_id: UUID = Field(default_factory=uuid4)
    evidence: EvidenceAnchor
    extraction_method: str = "deterministic"
    validation_flags: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=utc_now)


class Entity(DomainBaseModel):
    """Canonical representation of a resolved real-world entity."""

    id: UUID = Field(default_factory=uuid4)
    dataset_id: UUID = Field(default_factory=uuid4)
    entity_type: str = "company"
    canonical_data: dict[str, Any] = Field(default_factory=dict)
    current_status: TrustStatus = TrustStatus.SUPPORTED
    created_at: datetime = Field(default_factory=utc_now)


class DatasetSchema(DomainBaseModel):
    """Versioned schema contract for a dataset."""

    id: UUID = Field(default_factory=uuid4)
    version: Literal["1.0"] = "1.0"
    entity_type: str
    fields: list[FieldSpec]
    schema_hash: str = Field(min_length=8, description="Deterministic hash of field definitions")
