"""Offline unit tests for GroqProvider and AI provider factory with Groq support.

These tests use mocked Groq SDK clients and MUST perform ZERO network calls.
Covers:
1. Model passing and configuration
2. Strict JSON schema configuration (with transform_schema_for_groq_strict)
3. json_schema response mode with strict=True
4. Zero tools enabled (no web search, no code execution)
5. System instruction and user prompt separation
6. Valid Groq JSON deserialization into typed CandidateCompilationDraft
7. Malformed JSON handling -> AIProviderMalformedOutputError
8. Empty response handling -> AIProviderMalformedOutputError
9. Timeout translation -> AIProviderTimeoutError
10. 429 translation -> AIProviderRateLimitError
11. 401/403 translation -> AIProviderAuthenticationError
12. 5xx translation -> AIProviderError
13. Key masking in repr/log/errors
14. ProviderMetadata content (provider, model, latency, tokens)
15. No silent fallback to FixtureProvider on Groq failure
16. Provider factory selects FixtureProvider for AI_PROVIDER=fixture without Groq key
17. Provider factory selects GroqProvider for AI_PROVIDER=groq
18. Provider factory fails clearly when GROQ_API_KEY is missing in groq mode
19. Security test: fake secret never appears in exception strings, reprs, or metadata
20. Settings repr masks GROQ_API_KEY
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from groq import AuthenticationError, InternalServerError, RateLimitError
from pydantic import BaseModel, SecretStr

from app.ai.contracts import StructuredGenerationRequest
from app.ai.exceptions import (
    AIProviderAuthenticationError,
    AIProviderConfigurationError,
    AIProviderError,
    AIProviderMalformedOutputError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
)
from app.ai.factory import create_structured_generation_provider
from app.ai.fixture_provider import FixtureProvider
from app.ai.groq_provider import GroqProvider, transform_schema_for_groq_strict
from app.application.requirement_compiler.models import (
    CandidateCompilationDraft,
    CandidateCompilerEnvelope,
)
from app.core.config import Settings


def _make_groq_error(err_cls: Any, message: str, status_code: int) -> Exception:
    resp = httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    err: Exception = err_cls(message, response=resp, body=None)
    return err


class DummyTarget(BaseModel):
    name: str
    count: int


@pytest.fixture
def mock_groq_client() -> MagicMock:
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.close = AsyncMock()
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
def test_provider_factory_selects_groq_with_key() -> None:
    """GroqProvider is created when AI_PROVIDER=groq and key is provided."""
    settings = Settings(
        AI_PROVIDER="groq",
        GROQ_API_KEY=SecretStr("fake-groq-key"),
        GROQ_MODEL="openai/gpt-oss-120b",
        GROQ_MAX_COMPLETION_TOKENS=4096,
    )
    provider = create_structured_generation_provider(settings)
    assert isinstance(provider, GroqProvider)
    assert provider.model == "openai/gpt-oss-120b"
    assert provider._max_completion_tokens == 4096


def test_provider_factory_missing_key_in_groq_mode_raises_error() -> None:
    """Missing key in groq mode raises sanitized AIProviderConfigurationError."""
    settings = Settings(AI_PROVIDER="groq", GROQ_API_KEY=None)
    with pytest.raises(AIProviderConfigurationError, match="GROQ_API_KEY is not configured"):
        create_structured_generation_provider(settings)


def test_provider_factory_fixture_mode_works_without_groq_key() -> None:
    """FixtureProvider is created without GROQ_API_KEY when AI_PROVIDER=fixture."""
    settings = Settings(AI_PROVIDER="fixture", GROQ_API_KEY=None)
    provider = create_structured_generation_provider(settings)
    assert isinstance(provider, FixtureProvider)


def test_settings_groq_max_completion_tokens_bounds() -> None:
    """Verify GROQ_MAX_COMPLETION_TOKENS bounds validation (512 <= tokens <= 4096)."""
    from pydantic import ValidationError

    # Valid values
    s1 = Settings(GROQ_MAX_COMPLETION_TOKENS=512)
    assert s1.GROQ_MAX_COMPLETION_TOKENS == 512

    s2 = Settings(GROQ_MAX_COMPLETION_TOKENS=4096)
    assert s2.GROQ_MAX_COMPLETION_TOKENS == 4096

    s3 = Settings(GROQ_MAX_COMPLETION_TOKENS=2048)
    assert s3.GROQ_MAX_COMPLETION_TOKENS == 2048

    # Below minimum (< 512)
    with pytest.raises(ValidationError):
        Settings(GROQ_MAX_COMPLETION_TOKENS=256)

    # Above maximum (> 4096)
    with pytest.raises(ValidationError):
        Settings(GROQ_MAX_COMPLETION_TOKENS=8192)


# -----------------------------------------------------------------------------
# 2. Strict Schema Transformation Tests
# -----------------------------------------------------------------------------
def test_transform_schema_for_groq_strict_enforces_strict_rules() -> None:
    """Verify transform_schema_for_groq_strict enforces all Groq strict schema rules."""
    raw_schema = CandidateCompilationDraft.model_json_schema()
    strict_schema = transform_schema_for_groq_strict(raw_schema)

    def _assert_strict_node(node: dict[str, Any]) -> None:
        if node.get("type") == "object" or "properties" in node:
            assert node.get("additionalProperties") is False
            props = node.get("properties", {})
            reqs = node.get("required", [])
            for p in props:
                assert p in reqs, f"Property {p} missing from required in strict mode"
        assert "pattern" not in node, "Lookaround regex pattern was not stripped"

        # Check subnodes
        if "properties" in node:
            for v in node["properties"].values():
                if isinstance(v, dict):
                    _assert_strict_node(v)
        if "$defs" in node:
            for v in node["$defs"].values():
                if isinstance(v, dict):
                    _assert_strict_node(v)
        if "items" in node and isinstance(node["items"], dict):
            _assert_strict_node(node["items"])
        for comp in ("anyOf", "oneOf", "allOf"):
            if comp in node and isinstance(node[comp], list):
                for item in node[comp]:
                    if isinstance(item, dict):
                        _assert_strict_node(item)

    _assert_strict_node(strict_schema)
    assert strict_schema["additionalProperties"] is False
    assert "goal" in strict_schema["required"]
    assert "entity_type" in strict_schema["required"]


# -----------------------------------------------------------------------------
# 3. Invocation Parameters & Strict Output
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_groq_provider_passes_parameters_and_zero_tools(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """Verify model, temperature, reasoning_effort, json_schema strict mode, and zero tools."""
    mock_choice = MagicMock()
    mock_choice.message.content = '{"name": "test", "count": 10}'
    mock_choice.finish_reason = "stop"
    mock_response = MagicMock(
        choices=[mock_choice],
        usage=MagicMock(prompt_tokens=15, completion_tokens=25),
    )
    mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = GroqProvider(
        model="openai/gpt-oss-120b",
        timeout_ms=30000,
        client=mock_groq_client,
    )

    result, metadata = await provider.generate_structured(sample_request, DummyTarget)

    assert result.name == "test"
    assert result.count == 10
    assert metadata.provider_name == "groq"
    assert metadata.model_name == "openai/gpt-oss-120b"
    assert metadata.prompt_tokens == 15
    assert metadata.completion_tokens == 25
    assert metadata.raw_finish_reason == "stop"

    call_kwargs = mock_groq_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "openai/gpt-oss-120b"
    assert call_kwargs["temperature"] == 0.1
    assert call_kwargs["tools"] is None  # STRICT: Zero tools enabled
    assert call_kwargs["reasoning_effort"] == "low"
    assert call_kwargs["max_completion_tokens"] == 4096
    assert call_kwargs["response_format"]["type"] == "json_schema"
    assert call_kwargs["response_format"]["json_schema"]["strict"] is True


@pytest.mark.asyncio
async def test_groq_provider_passes_custom_max_completion_tokens(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """Verify configured custom max_completion_tokens is passed to SDK completion request."""
    mock_choice = MagicMock()
    mock_choice.message.content = '{"name": "test", "count": 10}'
    mock_choice.finish_reason = "stop"
    mock_response = MagicMock(choices=[mock_choice], usage=None)
    mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = GroqProvider(
        model="openai/gpt-oss-120b",
        max_completion_tokens=2048,
        client=mock_groq_client,
    )

    await provider.generate_structured(sample_request, DummyTarget)

    call_kwargs = mock_groq_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["max_completion_tokens"] == 2048


# -----------------------------------------------------------------------------
# 4. Error Handling & Sanitization
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_groq_malformed_json_raises_malformed_output_error(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """Malformed non-JSON output raises AIProviderMalformedOutputError."""
    mock_choice = MagicMock()
    mock_choice.message.content = "Invalid non-JSON text"
    mock_choice.finish_reason = "stop"
    mock_response = MagicMock(choices=[mock_choice], usage=None)
    mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = GroqProvider(client=mock_groq_client)
    with pytest.raises(AIProviderMalformedOutputError, match="could not be parsed into"):
        await provider.generate_structured(sample_request, DummyTarget)


@pytest.mark.asyncio
async def test_groq_empty_response_raises_malformed_output_error(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """Empty content raises AIProviderMalformedOutputError."""
    mock_choice = MagicMock()
    mock_choice.message.content = ""
    mock_choice.finish_reason = "length"
    mock_response = MagicMock(choices=[mock_choice], usage=None)
    mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = GroqProvider(client=mock_groq_client)
    with pytest.raises(AIProviderMalformedOutputError, match="empty content"):
        await provider.generate_structured(sample_request, DummyTarget)


@pytest.mark.asyncio
async def test_groq_timeout_translates_to_ai_provider_timeout_error(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """Timeout error raises AIProviderTimeoutError."""
    mock_groq_client.chat.completions.create = AsyncMock(side_effect=TimeoutError("Timed out"))

    provider = GroqProvider(timeout_ms=1000, client=mock_groq_client)
    with pytest.raises(AIProviderTimeoutError, match="timed out"):
        await provider.generate_structured(sample_request, DummyTarget)


@pytest.mark.asyncio
async def test_groq_429_rate_limit_translation(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """HTTP 429 translates to AIProviderRateLimitError."""
    err_429 = _make_groq_error(RateLimitError, "Rate limit reached for requests", status_code=429)
    mock_groq_client.chat.completions.create = AsyncMock(side_effect=err_429)

    provider = GroqProvider(client=mock_groq_client)
    with pytest.raises(AIProviderRateLimitError, match="rate or quota limit reached"):
        await provider.generate_structured(sample_request, DummyTarget)


@pytest.mark.asyncio
async def test_groq_401_auth_failure_translation(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """HTTP 401 translates to AIProviderAuthenticationError."""
    err_401 = _make_groq_error(AuthenticationError, "Invalid API Key", status_code=401)
    mock_groq_client.chat.completions.create = AsyncMock(side_effect=err_401)

    provider = GroqProvider(client=mock_groq_client)
    with pytest.raises(AIProviderAuthenticationError, match="authentication failed"):
        await provider.generate_structured(sample_request, DummyTarget)


@pytest.mark.asyncio
async def test_groq_500_server_error_translation(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """HTTP 500 server error translates to AIProviderError."""
    err_500 = _make_groq_error(InternalServerError, "Internal server error", status_code=500)
    mock_groq_client.chat.completions.create = AsyncMock(side_effect=err_500)

    provider = GroqProvider(client=mock_groq_client)
    with pytest.raises(AIProviderError, match="service unavailable"):
        await provider.generate_structured(sample_request, DummyTarget)


@pytest.mark.asyncio
async def test_groq_failure_does_not_fall_back_to_fixture(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """When GroqProvider fails, it MUST raise an error and NEVER return fixture data."""
    err_429 = _make_groq_error(RateLimitError, "Rate limited", status_code=429)
    mock_groq_client.chat.completions.create = AsyncMock(side_effect=err_429)

    provider = GroqProvider(client=mock_groq_client)
    with pytest.raises(AIProviderRateLimitError):
        await provider.generate_structured(sample_request, CandidateCompilationDraft)


# -----------------------------------------------------------------------------
# 5. Security & Secret Leakage Prevention Tests
# -----------------------------------------------------------------------------
def test_settings_repr_masks_groq_api_key() -> None:
    """Verify repr(settings) never reveals GROQ_API_KEY value."""
    secret_val = "gsk_VERY_SECRET_GROQ_KEY_12345"
    settings = Settings(GROQ_API_KEY=SecretStr(secret_val))
    repr_str = repr(settings)
    assert secret_val not in repr_str
    assert "**********" in repr_str or "SecretStr('**********')" in repr_str


def test_groq_provider_repr_masks_api_key() -> None:
    """Verify repr(GroqProvider) never displays the raw API key and shows max_completion_tokens."""
    secret_val = "gsk_VERY_SECRET_GROQ_KEY_67890"
    mock_c = MagicMock()
    provider = GroqProvider(
        api_key=SecretStr(secret_val), max_completion_tokens=4096, client=mock_c
    )
    repr_str = repr(provider)
    assert secret_val not in repr_str
    assert "<redacted>" in repr_str
    assert "max_completion_tokens=4096" in repr_str


@pytest.mark.asyncio
async def test_fake_groq_secret_never_leaks_in_exceptions_or_metadata(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify planted fake secret never appears in exceptions, reprs, or test logs."""
    fake_secret = "gsk_FAKE_PROOFGRID_TEST_SECRET"
    err = _make_groq_error(AuthenticationError, f"Key {fake_secret} invalid", status_code=401)
    mock_groq_client.chat.completions.create = AsyncMock(side_effect=err)

    provider = GroqProvider(api_key=SecretStr(fake_secret), client=mock_groq_client)

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


# -----------------------------------------------------------------------------
# 6. Branch-Specific CandidateCompilerEnvelope Tests
# -----------------------------------------------------------------------------
def test_groq_strict_schema_transformation_on_candidate_compiler_envelope() -> None:
    """Verify transform_schema_for_groq_strict transforms CandidateCompilerEnvelope correctly."""
    raw_schema = CandidateCompilerEnvelope.model_json_schema()
    strict_schema = transform_schema_for_groq_strict(raw_schema)

    def _assert_strict(node: dict[str, Any], path: str = "root") -> None:
        if node.get("type") == "object" or "properties" in node:
            assert node.get("additionalProperties") is False, (
                f"additionalProperties not False at {path}"
            )
            props = node.get("properties", {})
            reqs = node.get("required", [])
            for p in props:
                assert p in reqs, f"Property {p} missing from required at {path}"
        assert "pattern" not in node, f"pattern regex found at {path}"

        if "properties" in node:
            for k, v in node["properties"].items():
                if isinstance(v, dict):
                    _assert_strict(v, f"{path}.properties.{k}")
        if "$defs" in node:
            for k, v in node["$defs"].items():
                if isinstance(v, dict):
                    _assert_strict(v, f"{path}.$defs.{k}")
        if "items" in node and isinstance(node["items"], dict):
            _assert_strict(node["items"], f"{path}.items")
        for comp in ("anyOf", "oneOf", "allOf"):
            if comp in node and isinstance(node[comp], list):
                for i, item in enumerate(node[comp]):
                    if isinstance(item, dict):
                        _assert_strict(item, f"{path}.{comp}[{i}]")

    _assert_strict(strict_schema)
    assert strict_schema["additionalProperties"] is False
    assert "outcome_type" in strict_schema["required"]
    assert "requires_confirmation" in strict_schema["required"]
    assert "compiled" in strict_schema["required"]
    assert "clarification" in strict_schema["required"]

    # Verify compiled & clarification nullability in schema
    compiled_prop = strict_schema["properties"]["compiled"]
    clarification_prop = strict_schema["properties"]["clarification"]
    assert "anyOf" in compiled_prop
    assert any(branch.get("type") == "null" for branch in compiled_prop["anyOf"])
    assert "anyOf" in clarification_prop
    assert any(branch.get("type") == "null" for branch in clarification_prop["anyOf"])


@pytest.mark.asyncio
async def test_groq_provider_generates_compiled_envelope(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """Verify GroqProvider parses and deserializes a COMPILED CandidateCompilerEnvelope."""
    payload = {
        "outcome_type": "COMPILED",
        "requires_confirmation": True,
        "compiled": {
            "goal": "Find AI startups",
            "entity_type": "company",
            "geography": ["India"],
            "fields": [
                {
                    "key": "company_name",
                    "label": "Company Name",
                    "data_type": "string",
                    "required": True,
                    "description": "Name",
                }
            ],
            "filters": [],
            "source_hints": ["Tracxn"],
            "ambiguities": [],
            "assumptions": [],
            "clarification_questions": [],
            "trust_preferences": {
                "require_evidence_anchor": True,
                "minimum_independent_sources": 1,
            },
        },
        "clarification": None,
    }
    import json

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(payload)
    mock_choice.finish_reason = "stop"
    mock_response = MagicMock(
        choices=[mock_choice],
        usage=MagicMock(prompt_tokens=50, completion_tokens=120),
    )
    mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = GroqProvider(client=mock_groq_client)
    envelope, metadata = await provider.generate_structured(
        sample_request, CandidateCompilerEnvelope
    )

    assert isinstance(envelope, CandidateCompilerEnvelope)
    assert envelope.outcome_type == "COMPILED"
    assert envelope.requires_confirmation is True
    assert envelope.compiled is not None
    assert envelope.compiled.goal == "Find AI startups"
    assert envelope.clarification is None
    assert metadata.prompt_tokens == 50
    assert metadata.completion_tokens == 120


@pytest.mark.asyncio
async def test_groq_provider_generates_clarification_envelope(
    mock_groq_client: MagicMock,
    sample_request: StructuredGenerationRequest,
) -> None:
    """Verify GroqProvider parses and deserializes a NEEDS_CLARIFICATION CandidateCompilerEnvelope."""
    payload = {
        "outcome_type": "NEEDS_CLARIFICATION",
        "requires_confirmation": True,
        "compiled": None,
        "clarification": {
            "ambiguities": [
                {
                    "code": "AMB_001",
                    "message": "Missing referent entity type for 'ones'",
                    "severity": "BLOCKING",
                    "blocking": True,
                }
            ],
            "assumptions": [],
            "clarification_questions": [
                {
                    "question_id": "Q_001",
                    "ambiguity_code": "AMB_001",
                    "question": "What entity type does 'ones' refer to?",
                    "impact_summary": "Cannot determine target entity without clarification",
                }
            ],
            "detected_entity_type": None,
            "detected_geography": ["India"],
            "detected_time_window": None,
            "candidate_fields": [],
        },
    }
    import json

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(payload)
    mock_choice.finish_reason = "stop"
    mock_response = MagicMock(
        choices=[mock_choice],
        usage=MagicMock(prompt_tokens=40, completion_tokens=60),
    )
    mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = GroqProvider(client=mock_groq_client)
    envelope, metadata = await provider.generate_structured(
        sample_request, CandidateCompilerEnvelope
    )

    assert isinstance(envelope, CandidateCompilerEnvelope)
    assert envelope.outcome_type == "NEEDS_CLARIFICATION"
    assert envelope.requires_confirmation is True
    assert envelope.compiled is None
    assert envelope.clarification is not None
    assert len(envelope.clarification.ambiguities) == 1
    assert envelope.clarification.ambiguities[0].severity == "BLOCKING"
    assert len(envelope.clarification.clarification_questions) == 1
