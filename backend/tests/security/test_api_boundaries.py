import json
import logging
import sys

import httpx
import pytest
from pydantic import SecretStr

from app.api import routes
from app.core.config import Settings
from app.core.logging import StructuredJsonFormatter
from app.main import app


def test_logging_redacts_credentials_and_does_not_render_exception_body() -> None:
    try:
        raise RuntimeError("private raw body sk-secret-value")
    except RuntimeError:
        record = logging.LogRecord(
            "safe",
            logging.ERROR,
            __file__,
            1,
            "failed postgresql://user:secret@host/db?token=private Bearer abc",
            (),
            sys.exc_info(),
        )
    record.authorization = "Bearer hidden"
    record.cookie = "session=private"
    record.api_key = "my-secret"
    text = StructuredJsonFormatter("test").format(record)
    for secret in ["sk-secret-value", "private", "my-secret", "hidden", "user:secret", "abc"]:
        assert secret not in text
    assert json.loads(text)["exception_type"] == "RuntimeError"


async def test_http_auth_and_input_errors_never_echo_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(AUTH_ENABLED=True, API_AUTH_TOKEN=SecretStr("expected"))
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/datasets", headers={"Authorization": "Bearer not-the-key"})
        assert response.status_code == 401
        assert response.json()["error"]["correlation_id"] == response.headers["x-correlation-id"]
        response = await client.get(
            "/v1/runs/private-sensitive-not-a-uuid", headers={"Authorization": "Bearer expected"}
        )
        assert response.status_code == 422
        assert "private-sensitive" not in response.text
        settings.API_AUTH_TOKEN = SecretStr("")
        response = await client.get("/v1/datasets", headers={"Authorization": "Bearer "})
        assert response.status_code == 401


def test_openapi_exposes_core_versioned_journey() -> None:
    paths = app.openapi()["paths"]
    for path in [
        "/v1/requirements/compile",
        "/v1/runs/{run_id}/events",
        "/v1/datasets/{dataset_id}",
        "/v1/workflows/{workflow_id}/versions/{version_id}",
        "/v1/exports/{export_id}/download",
    ]:
        assert path in paths


async def test_provider_configuration_is_actionable_and_sanitized() -> None:
    from starlette.requests import Request

    from app.ai.exceptions import AIProviderAuthenticationError
    from app.main import ai_provider_error

    response = await ai_provider_error(
        Request({"type": "http"}), AIProviderAuthenticationError("private raw provider secret")
    )
    assert response.status_code == 503
    body = json.loads(bytes(response.body))
    assert body["error"]["code"] == "PROVIDER_AUTHENTICATION"
    assert body["error"]["retryable"] is False
    assert "private" not in bytes(response.body).decode()
