"""Provider factory for structured generation providers.

Instantiates either FixtureProvider or GeminiProvider based on configuration settings.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from app.ai.exceptions import AIProviderConfigurationError
from app.ai.fixture_provider import FixtureProvider
from app.ai.gemini_provider import GeminiProvider
from app.ai.groq_provider import GroqProvider
from app.ai.provider import StructuredGenerationProvider

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger("proofgrid.ai.factory")


def create_structured_generation_provider(settings: Settings) -> StructuredGenerationProvider:
    """Create a StructuredGenerationProvider based on application settings.

    Rules:
    - AI_PROVIDER='fixture' -> Returns FixtureProvider (deterministic offline testing, no key required).
    - AI_PROVIDER='gemini' -> Returns GeminiProvider (live generation, requires GEMINI_API_KEY).
    - AI_PROVIDER='groq' -> Returns GroqProvider (live generation, requires GROQ_API_KEY).
    - Unknown AI_PROVIDER -> Raises sanitized AIProviderConfigurationError.
    """
    provider_type = settings.AI_PROVIDER.lower().strip()

    if provider_type == "fixture":
        logger.info("Initializing FixtureProvider for offline deterministic compilation")
        return FixtureProvider()

    if provider_type == "gemini":
        key = settings.gemini_api_key_unmasked
        if not key:
            raise AIProviderConfigurationError(
                "AI_PROVIDER is set to 'gemini' but GEMINI_API_KEY is not configured. "
                "Provide a valid GEMINI_API_KEY in backend/.env or set AI_PROVIDER=fixture."
            )

        logger.info("Initializing GeminiProvider with model '%s'", settings.GEMINI_MODEL)
        return GeminiProvider(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            timeout_ms=settings.GEMINI_TIMEOUT_MS,
        )

    if provider_type == "groq":
        key = settings.groq_api_key_unmasked
        if not key:
            raise AIProviderConfigurationError(
                "AI_PROVIDER is set to 'groq' but GROQ_API_KEY is not configured. "
                "Provide a valid GROQ_API_KEY in backend/.env or set AI_PROVIDER=fixture."
            )

        logger.info("Initializing GroqProvider with model '%s'", settings.GROQ_MODEL)
        return GroqProvider(
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
            timeout_ms=settings.GROQ_TIMEOUT_MS,
            max_completion_tokens=settings.GROQ_MAX_COMPLETION_TOKENS,
        )

    raise AIProviderConfigurationError(
        f"Unsupported AI_PROVIDER '{settings.AI_PROVIDER}'. Supported providers: 'fixture', 'gemini', 'groq'."
    )


@asynccontextmanager
async def structured_provider(settings: Settings) -> AsyncIterator[StructuredGenerationProvider]:
    provider = create_structured_generation_provider(settings)
    try:
        yield provider
    finally:
        close = getattr(provider, "aclose", None)
        if close is not None:
            await close()
