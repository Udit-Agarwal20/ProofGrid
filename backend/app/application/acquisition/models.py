"""Bounded source snapshots, independent of database models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AcquiredDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    url: str
    content: str = Field(max_length=5_000_000)
    content_type: str
    retrieved_at: datetime
    acquisition_method: Literal["HTTP", "API", "FIXTURE", "BROWSER"]
    http_status: int = 200
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchHit(BaseModel):
    url: str
    title: str = ""
