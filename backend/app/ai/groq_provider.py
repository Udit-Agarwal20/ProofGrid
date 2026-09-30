"""Groq Cloud structured generation provider for ProofGrid Requirement Compiler.

Implements StructuredGenerationProvider using the official AsyncGroq Python SDK
with mandatory strict JSON Schema decoding (strict=True) and strict tool isolation.
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
    AIProviderConfigurationError,
    AIProviderError,
    AIProviderMalformedOutputError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
)
from app.ai.provider import StructuredGenerationProvider

logger = logging.getLogger(__name__)

T = TypeVar("T")

try:
    import groq
    from groq import (
        APIConnectionError,
        APIError,
        APIStatusError,
        APITimeoutError,
        AsyncGroq,
        AuthenticationError,
        InternalServerError,
        PermissionDeniedError,
        RateLimitError,
    )
except ImportError:
    groq = None  # type: ignore[assignment]
    AsyncGroq = None  # type: ignore[assignment,misc]
    APIError = None  # type: ignore[assignment,misc]
    APIStatusError = None  # type: ignore[assignment,misc]
    APITimeoutError = None  # type: ignore[assignment,misc]
    AuthenticationError = None  # type: ignore[assignment,misc]
    InternalServerError = None  # type: ignore[assignment,misc]
    PermissionDeniedError = None  # type: ignore[assignment,misc]
    RateLimitError = None  # type: ignore[assignment,misc]


def transform_schema_for_groq_strict(raw_schema: dict[str, Any]) -> dict[str, Any]:
    """Transform standard Pydantic JSON Schema into Groq strict mode schema.

    Groq/OpenAI strict mode requires:
    1. additionalProperties: false on every object schema.
    2. Every property in 'properties' must be listed in 'required'.
    3. No complex regex features (such as lookarounds in 'pattern').
    4. Explicit types on all fields (no bare untyped dicts).
    5. No empty schemas in anyOf/oneOf/allOf.

    Does NOT weaken or alter canonical ProofGrid domain models.
    """
    schema = copy.deepcopy(raw_schema)

    def _transform_node(node: Any) -> None:
        if not isinstance(node, dict):
            return

        # 1. Object schemas: enforce additionalProperties: false and all properties in required
        if node.get("type") == "object" or "properties" in node:
            node["type"] = "object"
            node["additionalProperties"] = False
            props = node.get("properties", {})
            reqs = set(node.get("required", []))
            for prop_name, prop_schema in props.items():
                reqs.add(prop_name)
                _transform_node(prop_schema)
            node["required"] = sorted(list(reqs))

        # 2. Composite schemas: anyOf, oneOf, allOf
        for key in ("anyOf", "oneOf", "allOf"):
            if key in node and isinstance(node[key], list):
                new_list = []
                for item in node[key]:
                    if item == {}:
                        # Empty schema in anyOf -> skip empty untyped branch
                        continue
                    _transform_node(item)
                    new_list.append(item)
                if not new_list:
                    new_list = [{"type": "null"}]
                node[key] = new_list

        # 3. Array items
        if "items" in node:
            if isinstance(node["items"], dict):
                _transform_node(node["items"])
            elif isinstance(node["items"], list):
                for item in node["items"]:
                    if isinstance(item, dict):
                        _transform_node(item)

        # 4. Definitions ($defs)
        if "$defs" in node and isinstance(node["$defs"], dict):
            for def_schema in node["$defs"].values():
                _transform_node(def_schema)

        # 5. Strip pattern with unsupported regex lookarounds (e.g. Decimal fields)
        if "pattern" in node:
            del node["pattern"]

        # 6. Ensure untyped leaf nodes have explicit types (e.g. Any fields)
        if (
            "type" not in node
            and "$ref" not in node
            and "anyOf" not in node
            and "oneOf" not in node
            and "allOf" not in node
        ):
            node["anyOf"] = [
                {"type": "string"},
                {"type": "number"},
                {"type": "boolean"},
                {"type": "array", "items": {"type": "string"}},
                {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["start", "end"],
                    "additionalProperties": False,
                },
                {"type": "null"},
            ]

    _transform_node(schema)
    return schema


class GroqProvider(StructuredGenerationProvider):
    """Production Groq Cloud structured generation provider.

    Adheres strictly to the StructuredGenerationProvider protocol:
    1. Schema-enforced decoding with strict JSON Schema (strict=True).
    2. Strict tool isolation: zero tools, zero web search, zero code execution.
    3. Independent Pydantic deserialization + metadata attribution.
    4. Sanitized error boundaries preserving secret isolation.
    """

    def __init__(
        self,
        api_key: SecretStr | None = None,
        model: str = "openai/gpt-oss-120b",
        timeout_ms: int = 45000,
        max_completion_tokens: int = 4096,
        client: AsyncGroq | None = None,
    ) -> None:
        self._model = model
        self._timeout_ms = timeout_ms
        self._timeout_seconds = max(1.0, timeout_ms / 1000.0)
        self._max_completion_tokens = max_completion_tokens
        self._owns_client = client is None

        if client is not None:
            self._client = client
        else:
            if groq is None or AsyncGroq is None:
                raise AIProviderConfigurationError(
                    "The 'groq' package is not installed. Please install groq>=1.7.0,<2.0.0."
                )
            if api_key is None or not api_key.get_secret_value().strip():
                raise AIProviderConfigurationError(
                    "GROQ_API_KEY must be provided to initialize GroqProvider"
                )
            self._client = AsyncGroq(
                api_key=api_key.get_secret_value(),
                timeout=self._timeout_seconds,
            )

    @property
    def name(self) -> str:
        """Return provider identifier."""
        return "groq"

    @property
    def model(self) -> str:
        """Return configured model identifier."""
        return self._model

    async def aclose(self) -> None:
        """Release underlying HTTP client resources."""
        if self._owns_client and self._client is not None:
            try:
                await self._client.close()
            except Exception as exc:
                logger.debug("Error closing Groq client transport: %s", type(exc).__name__)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        output_schema: type[T],
    ) -> tuple[T, ProviderMetadata]:
        """Execute schema-enforced structured generation via Groq strict JSON Schema."""
        # 1. Build strict JSON schema
        json_schema_fn = getattr(output_schema, "model_json_schema", None)
        if json_schema_fn is None:
            raise AIProviderConfigurationError(
                f"Output schema {output_schema} must be a Pydantic model supporting model_json_schema()"
            )
        raw_schema = json_schema_fn()
        strict_schema = transform_schema_for_groq_strict(raw_schema)

        # 2. Configure temperature and reasoning settings
        temp = request.temperature if request.temperature is not None else 0.1

        # 3. Assemble chat completion payload
        messages = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]

        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": output_schema.__name__,
                "strict": True,
                "schema": strict_schema,
            },
        }

        call_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "response_format": response_format,
            "temperature": temp,
            "max_completion_tokens": self._max_completion_tokens,
            "tools": None,  # STRICT: Zero tools, zero web search, zero code execution
        }

        # Use reasoning_effort="low" if supported for reasoning models
        if "gpt-oss" in self._model or "deepseek" in self._model:
            call_kwargs["reasoning_effort"] = "low"

        start_time = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.chat.completions.create(**call_kwargs)
        except TimeoutError as exc:
            raise AIProviderTimeoutError(
                f"Groq API request timed out after {self._timeout_ms}ms"
            ) from exc
        except Exception as exc:
            self._translate_api_error(exc)

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # 4. Extract and validate response payload
        choices = getattr(response, "choices", None)
        if not choices or len(choices) == 0:
            raise AIProviderMalformedOutputError(
                "Groq returned empty choices in completion response"
            )

        choice = choices[0]
        message = getattr(choice, "message", None)
        raw_text = getattr(message, "content", None) if message else None

        if not raw_text or not raw_text.strip():
            finish_reason = getattr(choice, "finish_reason", "unknown")
            raise AIProviderMalformedOutputError(
                f"Groq returned empty content. Finish reason: {finish_reason}"
            )

        # 5. Deserialize and validate via Pydantic model
        validate_fn = getattr(output_schema, "model_validate_json", None)
        if validate_fn is None:
            raise AIProviderConfigurationError(
                f"Output schema {output_schema} must support model_validate_json()"
            )

        try:
            parsed_object: T = validate_fn(raw_text)
        except Exception as exc:
            raise AIProviderMalformedOutputError(
                f"Groq response could not be parsed into {output_schema.__name__}."
            ) from exc

        # 6. Extract usage and audit metadata
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        usage = getattr(response, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)

        raw_finish_reason = getattr(choice, "finish_reason", None)

        metadata = ProviderMetadata(
            provider_name="groq",
            model_name=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=round(latency_ms, 2),
            raw_finish_reason=str(raw_finish_reason) if raw_finish_reason is not None else None,
            scenario=None,
        )

        return parsed_object, metadata

    def _translate_api_error(self, exc: Exception) -> None:
        """Map Groq SDK errors into sanitized ProofGrid provider exceptions without leaking secrets."""
        if APITimeoutError is not None and isinstance(exc, APITimeoutError):
            raise AIProviderTimeoutError(
                f"Groq API request timed out after {self._timeout_ms}ms"
            ) from exc

        if APIConnectionError is not None and isinstance(exc, APIConnectionError):
            raise AIProviderError(
                "Groq API connection failed. Check network reachability."
            ) from exc

        if AuthenticationError is not None and isinstance(
            exc, (AuthenticationError, PermissionDeniedError)
        ):
            code = getattr(exc, "status_code", 401)
            raise AIProviderAuthenticationError(
                f"Groq authentication failed (HTTP {code}). Verify your GROQ_API_KEY configuration."
            ) from exc

        if RateLimitError is not None and isinstance(exc, RateLimitError):
            raise AIProviderRateLimitError("Groq rate or quota limit reached (HTTP 429).") from exc

        if InternalServerError is not None and isinstance(exc, InternalServerError):
            code = getattr(exc, "status_code", 500)
            raise AIProviderError(
                f"Groq service unavailable (HTTP {code}). Please retry later."
            ) from exc

        if APIError is not None and isinstance(exc, APIError):
            code = getattr(exc, "status_code", None)
            msg = getattr(exc, "message", "") or str(exc)
            sanitized_msg = msg.split("?")[0]  # Strip any URL query parameters if present

            if (
                code in (401, 403)
                or "unauthorized" in sanitized_msg.lower()
                or "unauthenticated" in sanitized_msg.lower()
            ):
                raise AIProviderAuthenticationError(
                    f"Groq authentication failed (HTTP {code}). Verify your GROQ_API_KEY configuration."
                ) from exc

            if code == 429 or "rate limit" in sanitized_msg.lower():
                raise AIProviderRateLimitError(
                    "Groq rate or quota limit reached (HTTP 429)."
                ) from exc

            if code is not None and code >= 500:
                raise AIProviderError(
                    f"Groq service unavailable (HTTP {code}). Please retry later."
                ) from exc

            raise AIProviderError(f"Groq API error (HTTP {code}): {sanitized_msg}") from exc

        err_type = type(exc).__name__
        err_msg = str(exc)
        if "timeout" in err_type.lower() or "timeout" in err_msg.lower():
            raise AIProviderTimeoutError(f"Groq API request timed out: {err_type}") from exc

        raise AIProviderError(
            f"Groq invocation failed: {err_type}: {err_msg.split('?')[0]}"
        ) from exc

    def __repr__(self) -> str:
        """Safe representation masking credentials."""
        return (
            f"GroqProvider(model='{self._model}', timeout_ms={self._timeout_ms}, "
            f"max_completion_tokens={self._max_completion_tokens}, api_key='<redacted>')"
        )
