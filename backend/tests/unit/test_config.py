"""Unit tests for configuration loading and validation."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_settings_default_values() -> None:
    """Verify default configuration values."""
    settings = Settings()
    assert settings.APP_ENV == "local"
    assert settings.APP_NAME == "proofgrid-api"
    assert settings.APP_VERSION == "0.1.0"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.API_PORT == 8000
    assert settings.API_HOST == "0.0.0.0"
    assert settings.PUBLIC_APP_URL == "http://localhost:3000"
    assert settings.DATABASE_URL is None  # Optional in Phase 1


def test_settings_env_override() -> None:
    """Verify environment variables properly override defaults."""
    env_vars = {
        "APP_ENV": "staging",
        "APP_NAME": "proofgrid-staging-api",
        "API_PORT": "9000",
        "LOG_LEVEL": "DEBUG",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        settings = Settings()
        assert settings.APP_ENV == "staging"
        assert settings.APP_NAME == "proofgrid-staging-api"
        assert settings.API_PORT == 9000
        assert settings.LOG_LEVEL == "DEBUG"


def test_settings_invalid_port_rejection() -> None:
    """Verify validation error when API_PORT is outside valid bounds."""
    with patch.dict(os.environ, {"API_PORT": "70000"}), pytest.raises(ValidationError):
        Settings()

    with patch.dict(os.environ, {"API_PORT": "-1"}), pytest.raises(ValidationError):
        Settings()


def test_settings_invalid_env_rejection() -> None:
    """Verify validation error when APP_ENV is invalid."""
    with (
        patch.dict(os.environ, {"APP_ENV": "invalid_environment"}),
        pytest.raises(ValidationError),
    ):
        Settings()


def test_get_settings_cached() -> None:
    """Verify get_settings returns the singleton cached instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
