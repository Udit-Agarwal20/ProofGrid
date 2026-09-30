"""The extractor can propose claims only, with no executable capabilities."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.contracts import EvidenceAnchor


class ClaimDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_key: str = Field(min_length=1, max_length=255)
    field_key: str = Field(min_length=1, max_length=64)
    raw_value: Any
    evidence: EvidenceAnchor
    extraction_method: str = "deterministic"
    raw_document_id: str = ""
    source_id: str = ""
    normalized_value: Any = None
    validation_flags: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[ClaimDraft] = Field(default_factory=list, max_length=5000)
