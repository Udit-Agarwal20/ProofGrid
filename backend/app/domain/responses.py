"""Serializable public resource projections, independent of infrastructure."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ResourceResponse(BaseModel):
    id: UUID
    data: dict[str, Any]


class PageResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class ProofResponse(BaseModel):
    dataset_version_id: UUID
    entity_id: UUID
    field_key: str
    canonical_value: Any
    trust_status: str
    resolution: dict[str, Any]
    claims: list[dict[str, Any]]
    conflict: dict[str, Any] | None = None
