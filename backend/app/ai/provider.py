"""Provider protocol for structured generation."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from app.ai.contracts import ProviderMetadata, StructuredGenerationRequest

T = TypeVar("T")


@runtime_checkable
class StructuredGenerationProvider(Protocol):
    """Abstract interface for structured generation providers.

    All implementations must return candidate structured output conforming to
    output_schema along with non-sensitive execution metadata.
    """

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        output_schema: type[T],
    ) -> tuple[T, ProviderMetadata]:
        """Generate a candidate structured output object matching output_schema."""
        ...
