"""Unit tests for service health check endpoints."""

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)
settings = get_settings()


def test_health_live() -> None:
    """Verify /health/live returns process status ok and service identity."""
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == settings.APP_NAME
    assert data["version"] == settings.APP_VERSION


def test_health_ready() -> None:
    """Verify /health/ready confirms configuration readiness."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == settings.APP_NAME
    assert data["version"] == settings.APP_VERSION
    assert data["ready"] is True
    assert data["environment"] == settings.APP_ENV
