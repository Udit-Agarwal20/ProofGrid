"""Gemini structured generation provider using official Google GenAI Python SDK.

Translates vendor-neutral structured generation requests into Gemini Developer API calls
with schema-enforced structured outputs and non-sensitive audit metadata.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from typing import Any, TypeVar

from pydantic import SecretStr

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
from app.ai.provider import StructuredGenerationProvider

try:
    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover
    genai = None  # type: ignore[assignment]
    genai_errors = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]

T = TypeVar("T")
logger = logging.getLogger("proofgrid.ai.gemini")


def sanitize_schema_for_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively clean a JSON Schema dictionary for Gemini Developer API compatibility.

    Removes unsupported keywords (e.g. additionalProperties, title, $schema) that cause
    Gemini Developer API structured output validation errors, while strictly preserving
    all required fields, property definitions, types, enums, and nested structures.
    """
    clean = copy.deepcopy(schema)

    def _clean_node(node: Any) -> None:
        if not isinstance(node, dict):
            return

        # Keywords rejected by Gemini Developer API mode
        node.pop("additionalProperties", None)
        node.pop("title", None)
        node.pop("$schema", None)

        for _, value in list(node.items()):
            if isinstance(value, dict):
                _clean_node(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        _clean_node(item)

    _clean_node(clean)
    return clean


class GeminiProvider(StructuredGenerationProvider):
    """Google Gemini live provider implementing StructuredGenerationProvider.

    Features:
    - Official Google GenAI Python SDK (google-genai)
    - Asynchronous lifecycle via client.aio
    - Schema-enforced structured outputs (response_mime_type="application/json")
    - Pydantic post-validation
    - Strict tool isolation (zero web search grounding, zero code execution)
    - Sanitized error translation (no secrets, URLs, or raw tokens leaked)
    - Full reproducibility metadata and token usage attribution
    """

    def __init__(
        self,
        api_key: str | SecretStr | None = None,
        model: str = "gemini-3.8-flash",
        timeout_ms: int = 45000,
        client: Any | None = None,
    ) -> None:
        if genai is None:  # pragma: no cover
            raise AIProviderConfigurationError(
                "google-genai package is not installed. Install via: pip install 'google-genai>=2.25.0,<3.0.0'"
            )

        self._model = model
        self._timeout_ms = timeout_ms
        self._timeout_seconds = timeout_ms / 1000.0

        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            raw_key: str | None = None
            if isinstance(api_key, SecretStr):
                raw_key = api_key.get_secret_value()
            elif isinstance(api_key, str) and api_key.strip():
                raw_key = api_key.strip()

            if not raw_key:
                raise AIProviderConfigurationError(
                    "GEMINI_API_KEY is required to initialize GeminiProvider. "
                    "Provide a valid key or set AI_PROVIDER=fixture for offline development."
                )

            http_options = genai_types.HttpOptions(timeout=self._timeout_ms)
            self._client = genai.Client(api_key=raw_key, http_options=http_options)
            self._owns_client = True

    @property
    def model(self) -> str:
        """Configured Gemini model name."""
        return self._model

    @property
    def timeout_ms(self) -> int:
        """Configured total timeout in milliseconds."""
        return self._timeout_ms

    async def aclose(self) -> None:
        """Gracefully release client resources."""
        if (
            self._owns_client
            and hasattr(self._client, "aio")
            and hasattr(self._client.aio, "aclose")
        ):
            await self._client.aio.aclose()

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        output_schema: type[T],
    ) -> tuple[T, ProviderMetadata]:
        """Execute a live structured generation request against the Gemini API.

        Strictly enforces:
        1. Cleaned JSON Schema via response_json_schema
        2. Candidate count = 1
        3. Zero external tools or search grounding
        4. Independent Pydantic deserialization and validation
        5. Sanitized error boundaries
        """
        # 1. Clean JSON schema for Gemini Developer API compatibility
        json_schema_fn = getattr(output_schema, "model_json_schema", None)
        if json_schema_fn is None:
            raise AIProviderConfigurationError(
                f"Output schema {output_schema} must be a Pydantic model supporting model_json_schema()"
            )

        raw_json_schema = json_schema_fn()
        gemini_schema = sanitize_schema_for_gemini(raw_json_schema)

        # 2. Assemble generation configuration
        # Conservative temperature: use 0.1 for deterministic compilation unless overridden
        temp = request.temperature if request.temperature > 0.0 else 0.1
        config = genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=gemini_schema,
            system_instruction=request.system_prompt,
            temperature=temp,
            candidate_count=1,
            max_output_tokens=request.max_tokens,
            tools=None,  # STRICT: Zero tools, zero Google search grounding, zero code execution
        )

        start_time = time.perf_counter()
        try:
            # 3. Safe bounded async execution
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=request.user_prompt,
                    config=config,
                )
        except TimeoutError as exc:
            raise AIProviderTimeoutError(
                f"Gemini API request timed out after {self._timeout_ms}ms"
            ) from exc
        except Exception as exc:
            self._translate_api_error(exc)

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # 4. Validate response payload
        raw_text = getattr(response, "text", None)
        if not raw_text or not raw_text.strip():
            # Check for safety / finish reason if available
            finish_reason = None
            if getattr(response, "candidates", None) and len(response.candidates) > 0:
                finish_reason = getattr(response.candidates[0], "finish_reason", None)
            raise AIProviderMalformedOutputError(
                f"Gemini returned empty or blocked response. Finish reason: {finish_reason or 'unknown'}"
            )

        # 5. Deserialize and validate via Pydantic model
        validate_fn = getattr(output_schema, "model_validate_json", None)
        if validate_fn is None:
            raise AIProviderConfigurationError(
                f"Output schema {output_schema} must be a Pydantic model supporting model_validate_json()"
            )

        try:
            parsed_object: T = validate_fn(raw_text)
        except Exception as exc:
            raise AIProviderMalformedOutputError(
                f"Gemini response could not be parsed into {output_schema.__name__}."
            ) from exc

        # 6. Extract usage metadata
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_token_count", None)
            completion_tokens = getattr(usage, "candidates_token_count", None)

        raw_finish_reason: str | None = None
        if getattr(response, "candidates", None) and len(response.candidates) > 0:
            finish_val = getattr(response.candidates[0], "finish_reason", None)
            raw_finish_reason = str(finish_val) if finish_val is not None else None

        metadata = ProviderMetadata(
            provider_name="gemini",
            model_name=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=round(latency_ms, 2),
            raw_finish_reason=raw_finish_reason,
            scenario=None,
        )

        return parsed_object, metadata

    def _translate_api_error(self, exc: Exception) -> None:
        """Map SDK errors into sanitized ProofGrid provider exceptions without leaking secrets."""
        # Check for Google GenAI APIError
        if genai_errors is not None and isinstance(exc, genai_errors.APIError):
            code = getattr(exc, "code", None)
            msg = getattr(exc, "message", "") or str(exc)
            sanitized_msg = msg.split("?")[0]  # Strip any URL query parameters if present

            if (
                code in (401, 403)
                or "PERMISSION_DENIED" in sanitized_msg
                or "UNAUTHENTICATED" in sanitized_msg
            ):
                raise AIProviderAuthenticationError(
                    f"Gemini authentication failed (HTTP {code}). Verify your GEMINI_API_KEY configuration."
                ) from exc

            if (
                code == 402
                or "prepayment credits are depleted" in sanitized_msg.lower()
                or "prepayment" in sanitized_msg.lower()
            ):
                raise AIProviderBillingError(
                    "Gemini billing or prepaid credits are unavailable (HTTP 402). "
                    "Check the Gemini API project's billing/credit status."
                ) from exc

            if code == 429 or "RESOURCE_EXHAUSTED" in sanitized_msg:
                raise AIProviderRateLimitError(
                    "Gemini rate or quota limit reached (HTTP 429)."
                ) from exc

            if code is not None and code >= 500:
                raise AIProviderError(
                    f"Gemini service unavailable (HTTP {code}). Please retry later."
                ) from exc

            raise AIProviderError(f"Gemini API error (HTTP {code}).") from exc

        err_type = type(exc).__name__
        err_msg = str(exc)
        if "timeout" in err_msg.lower():
            raise AIProviderTimeoutError(f"Gemini invocation timed out: {err_type}") from exc

        raise AIProviderError(f"Gemini invocation failed: {err_type}") from exc

    def __repr__(self) -> str:
        """Safe representation without leaking credentials."""
        return (
            f"GeminiProvider("
            f"model='{self._model}', "
            f"timeout_ms={self._timeout_ms}, "
            f"api_key='<redacted>'"
            f")"
        )
