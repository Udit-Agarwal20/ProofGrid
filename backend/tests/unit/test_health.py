"""Unit tests for service health check endpoints."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.health import DatabaseHealthResult
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


def test_health_live_independent_of_database() -> None:
    """Verify /health/live remains 200 even if database check fails catastrophically."""
    with patch(
        "app.main.check_database_health",
        new=AsyncMock(
            return_value=DatabaseHealthResult(status="unhealthy", error="Fatal DB Error")
        ),
    ):
        response = client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


def test_health_ready_when_db_healthy() -> None:
    """Verify /health/ready returns 200 and healthy status when DB succeeds."""
    mock_health = DatabaseHealthResult(status="healthy", latency_ms=12.5)
    with patch("app.main.check_database_health", new=AsyncMock(return_value=mock_health)):
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["ready"] is True
        assert data["database"]["status"] == "healthy"
        assert data["database"]["latency_ms"] == 12.5


def test_health_ready_when_db_unhealthy() -> None:
    """Verify /health/ready returns 503 Service Unavailable when DB check fails."""
    mock_health = DatabaseHealthResult(
        status="unhealthy",
        latency_ms=45.0,
        error="Database connection error: OperationalError",
    )
    with patch("app.main.check_database_health", new=AsyncMock(return_value=mock_health)):
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["ready"] is False
        assert data["database"]["status"] == "unhealthy"
        assert "OperationalError" in data["database"]["error"]
        # Ensure no passwords or raw credentials appear in response
        assert "password" not in str(data).lower() or "password=" not in str(data)
        assert "@" not in data["database"]["error"]


def test_health_ready_when_db_unconfigured() -> None:
    """Readiness fails closed when the authoritative database is absent."""
    with patch("app.main.settings.DATABASE_URL", None):
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "ok"
        assert data["ready"] is False
        assert data["database"]["status"] == "unconfigured"
