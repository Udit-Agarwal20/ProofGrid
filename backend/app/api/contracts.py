"""Public Pydantic contracts. ORM instances never cross the API boundary."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.requirement_compiler.models import CompilationOutcome
from app.domain.contracts import RequirementSpec, TrustContract
from app.domain.responses import PageResponse as PageResponse
from app.domain.responses import ProofResponse as ProofResponse
from app.domain.responses import ResourceResponse as ResourceResponse


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompileRequest(RequestModel):
    prompt: str = Field(min_length=3, max_length=12000)
    reference_date: datetime | None = None


class CompileResponse(BaseModel):
    requirement_id: UUID | None
    outcome: CompilationOutcome


class RequirementEdit(RequestModel):
    expected_version: int = Field(ge=1)
    requirement_spec: RequirementSpec


class TrustEdit(RequestModel):
    expected_version: int = Field(ge=1)
    trust_contract: TrustContract


class ConfirmRequest(RequestModel):
    expected_version: int = Field(ge=1)


class RunRequest(RequestModel):
    workflow_version_id: UUID
    idempotency_key: UUID


class ExportRequest(RequestModel):
    dataset_version_id: UUID
    format: Literal["csv", "json"] = "csv"


class ReviewRequest(RequestModel):
    decision: Literal["HUMAN_MERGE", "HUMAN_SEPARATE", "DEFER", "SELECT_DISPLAY"]
    selected_claim_id: UUID | None = None
    note: str = Field(default="", max_length=1000)
