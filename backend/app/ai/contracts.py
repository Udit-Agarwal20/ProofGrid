"""Contracts for AI and structured generation providers.

Contains vendor-independent request, response, and metadata models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StructuredGenerationRequest(BaseModel):
    """Vendor-neutral request to a structured generation provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    system_prompt: str = Field(min_length=1, description="System instructions for the provider")
    user_prompt: str = Field(min_length=1, description="Untrusted user input text")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive request context and scenario identifiers",
    )


class ProviderMetadata(BaseModel):
    """Metadata regarding provider execution for auditability and reproducibility."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_name: str = Field(description="Identifier of provider (e.g. 'fixture', 'gemini')")
    model_name: str = Field(description="Provider model or simulation identifier")
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0.0)
    raw_finish_reason: str | None = None
    scenario: str | None = Field(default=None, description="Active test scenario in fixture mode")
