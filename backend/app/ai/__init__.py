"""AI provider abstraction and deterministic test fixtures for ProofGrid."""

from app.ai.contracts import ProviderMetadata, StructuredGenerationRequest
from app.ai.exceptions import (
    AIProviderAuthenticationError,
    AIProviderBillingError,
    AIProviderConfigurationError,
    AIProviderError,
    AIProviderMalformedOutputError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
)
from app.ai.factory import create_structured_generation_provider
from app.ai.fixture_provider import FixtureProvider
from app.ai.gemini_provider import GeminiProvider, sanitize_schema_for_gemini
from app.ai.groq_provider import GroqProvider, transform_schema_for_groq_strict
from app.ai.provider import StructuredGenerationProvider

__all__ = [
    "AIProviderAuthenticationError",
    "AIProviderBillingError",
    "AIProviderConfigurationError",
    "AIProviderError",
    "AIProviderMalformedOutputError",
    "AIProviderRateLimitError",
    "AIProviderTimeoutError",
    "FixtureProvider",
    "GeminiProvider",
    "GroqProvider",
    "ProviderMetadata",
    "StructuredGenerationProvider",
    "StructuredGenerationRequest",
    "create_structured_generation_provider",
    "sanitize_schema_for_gemini",
    "transform_schema_for_groq_strict",
]
