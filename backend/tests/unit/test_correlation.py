"""Unit tests for CorrelationIdMiddleware and correlation context handling."""

from fastapi.testclient import TestClient

from app.core.correlation import (
    CORRELATION_ID_HEADER,
    is_valid_correlation_id,
)
from app.main import app

client = TestClient(app)


def test_is_valid_correlation_id() -> None:
    """Test validation of correlation ID format."""
    assert is_valid_correlation_id("req_12345678") is True
    assert is_valid_correlation_id("7b822d64-e4c1-4cb3-9872-466d7e9e801b") is True
    assert is_valid_correlation_id("") is False
    assert is_valid_correlation_id(None) is False
    assert is_valid_correlation_id("short") is False  # Min 8 chars
    assert is_valid_correlation_id("bad;chars!injection#") is False


def test_correlation_id_generated_when_missing() -> None:
    """Verify middleware generates a new UUID correlation ID if none is supplied."""
    response = client.get("/health/live")
    assert response.status_code == 200
    assert CORRELATION_ID_HEADER in response.headers
    cid = response.headers[CORRELATION_ID_HEADER]
    assert is_valid_correlation_id(cid) is True


def test_correlation_id_propagated_when_valid() -> None:
    """Verify middleware propagates an existing valid correlation ID."""
    custom_cid = "test-correlation-id-12345"
    response = client.get("/health/live", headers={CORRELATION_ID_HEADER: custom_cid})
    assert response.status_code == 200
    assert response.headers.get(CORRELATION_ID_HEADER) == custom_cid


def test_correlation_id_replaced_when_invalid() -> None:
    """Verify middleware replaces an unsafe correlation ID with a newly generated UUID."""
    unsafe_cid = "bad;header"
    response = client.get("/health/live", headers={CORRELATION_ID_HEADER: unsafe_cid})
    assert response.status_code == 200
    cid = response.headers.get(CORRELATION_ID_HEADER)
    assert cid != unsafe_cid
    assert is_valid_correlation_id(cid) is True
