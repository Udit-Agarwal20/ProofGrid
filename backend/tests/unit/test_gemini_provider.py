"""Offline unit tests for GeminiProvider and AI provider factory.

These tests use mocked Gemini SDK clients and MUST perform ZERO network calls.
Covers:
1. Model passing and configuration
2. Structured output schema configuration (with sanitizer)
3. application/json response mode
4. candidate_count = 1
5. Zero tools enabled (no search grounding, no code execution)
6. System instruction and user prompt separation
7. Valid Gemini JSON deserialization into typed CandidateCompilationDraft
8. Malformed JSON handling -> AIProviderMalformedOutputError
9. Empty response handling -> AIProviderMalformedOutputError
10. Timeout translation -> AIProviderTimeoutError
11. 402 translation -> AIProviderBillingError, 429 translation -> AIProviderRateLimitError
12. 401/403 translation -> AIProviderAuthenticationError
13. 5xx translation -> AIProviderError
14. Key masking in repr/log/errors
15. ProviderMetadata content (provider, model, latency)
16. Token usage metadata attribution
17. No silent fallback to FixtureProvider on Gemini failure
18. Provider factory selects FixtureProvider for AI_PROVIDER=fixture
19. Provider factory selects GeminiProvider for AI_PROVIDER=gemini
20. Provider factory fails clearly when GEMINI_API_KEY is missing in gemini mode
21. Fixture mode works with no key
22. Security test: fake secret never appears in exception strings, reprs, or metadata
23. Settings repr masks GEMINI_API_KEY
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import errors as genai_errors
from pydantic import BaseModel, SecretStr

from app.ai.contracts import StructuredGenerationRequest
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
from app.application.requirement_compiler.models import CandidateCompilationDraft
from app.core.config import Settings


class DummyTarget(BaseModel):
    name: str
    count: int


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.aio = MagicMock()
    client.aio.models = MagicMock()
    client.aio.aclose = AsyncMock()
    return client


@pytest.fixture
def sample_request() -> StructuredGenerationRequest:
    return StructuredGenerationRequest(
        system_prompt="You are a requirement compiler.",
        user_prompt="Find Indian AI startups that raised funding.",
        temperature=0.1,
    )


# -----------------------------------------------------------------------------
# 1. Configuration & Factory Tests
# -----------------------------------------------------------------------------
def test_provider_factory_selects_fixture_without_key() -> None:
    """FixtureProvider is created when AI_PROVIDER=fixture even if GEMINI_API_KEY is None."""
    settings = Settings(AI_PROVIDER="fixture", GEMINI_API_KEY=None)
    provider = create_structured_generation_provider(settings)
    assert isinstance(provider, FixtureProvider)


def test_provider_factory_selects_gemini_with_key() -> None:
    """GeminiProvider is created when AI_PROVIDER=gemini and key is provided."""
    settings = Settings(
        AI_PROVIDER="gemini",
        GEMINI_API_KEY=SecretStr("fake-valid-key"),
        GEMINI_MODEL="gemini-3.8-flash",
    )
    provider = create_structured_generation_provider(settings)
    assert isinstance(provider, GeminiProvider)
    assert provider.model == "gemini-3.8-flash"


def test_provider_factory_missing_key_in_gemini_mode_raises_error() -> None:
    """Missing key in gemini mode raises sanitized AIProviderConfigurationError."""
    settings = Settings(AI_PROVIDER="gemini", GEMINI_API_KEY=None)
    with pytest.raises(AIProviderConfigurationError, match="GEMINI_API_KEY is not configured"):
        create_structured_generation_provider(settings)


def test_provider_factory_unknown_provider_raises_error() -> None:
    """Unsupported provider raises AIProviderConfigurationError."""
    settings = Settings(AI_PROVIDER="fixture")
    # Bypass Literal typing to test runtime guard
    object.__setattr__(settings, "AI_PROVIDER", "unsupported_llm")
    with pytest.raises(AIProviderConfigurationError, match="Unsupported AI_PROVIDER"):
        create_structured_generation_provider(settings)


# -----------------------------------------------------------------------------
# 2. Structured Output & Invocation Parameters
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gemini_provider_passes_parameters_and_zero_tools(
    mock_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """Verify model, temperature, candidate_count=1, system_instruction, and tools=None."""
    mock_response = MagicMock()
    mock_response.text = '{"name": "test", "count": 5}'
    mock_response.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=20)
    mock_response.candidates = [MagicMock(finish_reason="STOP")]
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    provider = GeminiProvider(
        model="gemini-3.8-flash",
        timeout_ms=30000,
        client=mock_client,
    )

    result, metadata = await provider.generate_structured(sample_request, DummyTarget)

    assert result.name == "test"
    assert result.count == 5
    assert metadata.provider_name == "gemini"
    assert metadata.model_name == "gemini-3.8-flash"
    assert metadata.prompt_tokens == 10
    assert metadata.completion_tokens == 20
    assert metadata.raw_finish_reason == "STOP"

    # Verify generate_content call arguments
    call_args = mock_client.aio.models.generate_content.call_args
    assert call_args is not None
    assert call_args.kwargs["model"] == "gemini-3.8-flash"
    assert call_args.kwargs["contents"] == sample_request.user_prompt

    config = call_args.kwargs["config"]
    assert config.candidate_count == 1
    assert config.temperature == 0.1
    assert config.system_instruction == sample_request.system_prompt
    assert config.response_mime_type == "application/json"
    assert config.tools is None  # STRICT: Zero tools enabled


def test_schema_sanitizer_removes_unsupported_gemini_keywords() -> None:
    """Schema sanitizer strips additionalProperties and title while keeping properties and required."""
    raw_schema = CandidateCompilationDraft.model_json_schema()
    assert "additionalProperties" in raw_schema or any(
        "additionalProperties" in v
        for v in raw_schema.get("$defs", {}).values()
        if isinstance(v, dict)
    )

    sanitized = sanitize_schema_for_gemini(raw_schema)

    def _assert_no_additional_properties(node: dict[str, Any]) -> None:
        assert "additionalProperties" not in node
        assert "title" not in node
        assert "$schema" not in node
        for v in node.values():
            if isinstance(v, dict):
                _assert_no_additional_properties(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        _assert_no_additional_properties(item)

    _assert_no_additional_properties(sanitized)
    # Check that required properties are preserved
    assert "properties" in sanitized
    assert "entity_type" in sanitized["properties"]
    assert "required" in sanitized


# -----------------------------------------------------------------------------
# 3. Response Validation & Error Handling
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_malformed_json_raises_malformed_output_error(
    mock_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """Malformed non-JSON output raises AIProviderMalformedOutputError."""
    mock_response = MagicMock()
    mock_response.text = "This is not valid json at all"
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    provider = GeminiProvider(client=mock_client)
    with pytest.raises(AIProviderMalformedOutputError, match="could not be parsed into"):
        await provider.generate_structured(sample_request, DummyTarget)


@pytest.mark.asyncio
async def test_empty_or_blocked_response_raises_malformed_output_error(
    mock_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """Empty text / blocked response raises AIProviderMalformedOutputError."""
    mock_response = MagicMock()
    mock_response.text = ""
    mock_response.candidates = [MagicMock(finish_reason="SAFETY")]
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    provider = GeminiProvider(client=mock_client)
    with pytest.raises(AIProviderMalformedOutputError, match="empty or blocked response"):
        await provider.generate_structured(sample_request, DummyTarget)


@pytest.mark.asyncio
async def test_timeout_translates_to_ai_provider_timeout_error(
    mock_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """Timeout error raises AIProviderTimeoutError."""
    mock_client.aio.models.generate_content = AsyncMock(side_effect=TimeoutError("Timed out"))

    provider = GeminiProvider(timeout_ms=1000, client=mock_client)
    with pytest.raises(AIProviderTimeoutError, match="timed out"):
        await provider.generate_structured(sample_request, DummyTarget)


@pytest.mark.asyncio
async def test_402_billing_error_translation(
    mock_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """HTTP 402 (or prepayment depleted) translates to AIProviderBillingError and NOT RateLimitError."""
    err_402 = genai_errors.APIError(
        402,
        {
            "error": {
                "message": "Your prepayment credits are depleted. Please manage your project and billing."
            }
        },
    )
    mock_client.aio.models.generate_content = AsyncMock(side_effect=err_402)

    provider = GeminiProvider(client=mock_client)
    with pytest.raises(AIProviderBillingError) as exc_info:
        await provider.generate_structured(sample_request, DummyTarget)

    assert "billing or prepaid credits are unavailable (HTTP 402)" in str(exc_info.value)
    # Explicitly verify it is NOT classified as a rate limit error
    assert not isinstance(exc_info.value, AIProviderRateLimitError)
    assert "retry later" not in str(exc_info.value).lower()
    assert "rate limit" not in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_429_rate_limit_translation(
    mock_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """HTTP 429 RESOURCE_EXHAUSTED translates to AIProviderRateLimitError."""
    err_429 = genai_errors.APIError(
        429, {"error": {"message": "RESOURCE_EXHAUSTED: Quota exceeded"}}
    )
    mock_client.aio.models.generate_content = AsyncMock(side_effect=err_429)

    provider = GeminiProvider(client=mock_client)
    with pytest.raises(AIProviderRateLimitError) as exc_info:
        await provider.generate_structured(sample_request, DummyTarget)

    assert "rate or quota limit reached (HTTP 429)" in str(exc_info.value)


@pytest.mark.asyncio
async def test_401_or_403_auth_failure_translation(
    mock_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """HTTP 401 or 403 PERMISSION_DENIED translates to AIProviderAuthenticationError."""
    err_403 = genai_errors.APIError(403, {"error": {"message": "Permission denied"}})
    mock_client.aio.models.generate_content = AsyncMock(side_effect=err_403)

    provider = GeminiProvider(client=mock_client)
    with pytest.raises(AIProviderAuthenticationError, match="authentication failed"):
        await provider.generate_structured(sample_request, DummyTarget)


@pytest.mark.asyncio
async def test_500_server_error_translation(
    mock_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """HTTP 500 server error translates to AIProviderError."""
    err_500 = genai_errors.APIError(500, {"error": {"message": "Internal error"}})
    mock_client.aio.models.generate_content = AsyncMock(side_effect=err_500)

    provider = GeminiProvider(client=mock_client)
    with pytest.raises(AIProviderError, match="service unavailable"):
        await provider.generate_structured(sample_request, DummyTarget)


@pytest.mark.asyncio
async def test_gemini_failure_does_not_fall_back_to_fixture(
    mock_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """When GeminiProvider fails, it MUST raise an error and NEVER return fixture data."""
    err_429 = genai_errors.APIError(429, {"error": {"message": "Rate limited"}})
    mock_client.aio.models.generate_content = AsyncMock(side_effect=err_429)

    provider = GeminiProvider(client=mock_client)
    with pytest.raises(AIProviderRateLimitError):
        await provider.generate_structured(sample_request, CandidateCompilationDraft)


# -----------------------------------------------------------------------------
# 4. Security & Secret Leakage Prevention Tests
# -----------------------------------------------------------------------------
def test_settings_repr_masks_gemini_api_key() -> None:
    """Verify repr(settings) never reveals GEMINI_API_KEY value."""
    secret_val = "AIza_VERY_SECRET_KEY_12345"
    settings = Settings(GEMINI_API_KEY=SecretStr(secret_val))
    repr_str = repr(settings)
    assert secret_val not in repr_str
    assert "**********" in repr_str or "SecretStr('**********')" in repr_str


def test_gemini_provider_repr_masks_api_key() -> None:
    """Verify repr(GeminiProvider) never displays the raw API key."""
    secret_val = "AIza_VERY_SECRET_KEY_67890"
    mock_c = MagicMock()
    provider = GeminiProvider(api_key=SecretStr(secret_val), client=mock_c)
    repr_str = repr(provider)
    assert secret_val not in repr_str
    assert "<redacted>" in repr_str


@pytest.mark.asyncio
async def test_fake_secret_never_leaks_in_exceptions_or_metadata(
    mock_client: MagicMock,
    sample_request: StructuredGenerationRequest,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify planted fake secret never appears in exceptions, reprs, or test logs."""
    fake_secret = "AIza_FAKE_PROOFGRID_TEST_SECRET"
    err = genai_errors.APIError(403, {"error": {"message": f"Key {fake_secret} invalid"}})
    mock_client.aio.models.generate_content = AsyncMock(side_effect=err)

    provider = GeminiProvider(api_key=SecretStr(fake_secret), client=mock_client)

    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(AIProviderAuthenticationError) as exc_info,
    ):
        await provider.generate_structured(sample_request, DummyTarget)

    exc_str = str(exc_info.value)
    exc_repr = repr(exc_info.value)
    captured_logs = caplog.text

    assert fake_secret not in exc_str
    assert fake_secret not in exc_repr
    assert fake_secret not in captured_logs
    assert fake_secret not in repr(provider)
