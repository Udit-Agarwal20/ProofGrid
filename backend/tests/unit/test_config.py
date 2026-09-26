"""Unit tests for configuration loading and validation."""

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, get_settings


def test_settings_default_values() -> None:
    """Verify default configuration values."""
    settings = Settings(
        DATABASE_URL=None,
        DATABASE_DIRECT_URL=None,
        DATABASE_URL_UNPOOLED=None,
    )
    assert settings.APP_ENV == "local"
    assert settings.APP_NAME == "proofgrid-api"
    assert settings.APP_VERSION == "0.1.0"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.API_PORT == 8000
    assert settings.API_HOST == "0.0.0.0"
    assert settings.PUBLIC_APP_URL == "http://localhost:3000"
    assert settings.DATABASE_URL is None
    assert settings.DATABASE_DIRECT_URL is None
    assert settings.DATABASE_URL_UNPOOLED is None
    assert settings.database_url_unmasked is None
    assert settings.database_direct_url_unmasked is None
    assert settings.database_url_redacted == "<none>"
    assert settings.database_direct_url_redacted == "<none>"


def test_database_url_redaction_safety() -> None:
    """Verify credentials are never exposed in logs, strings, or repr."""
    raw_url = "postgresql://secretuser:supersecretpass@ep-pooler.neon.tech/neondb?sslmode=require"
    settings = Settings(DATABASE_URL=SecretStr(raw_url))

    # 1. repr must never contain password
    settings_repr = repr(settings)
    assert "supersecretpass" not in settings_repr
    assert "SecretStr" in settings_repr

    # 2. redacted string must mask password
    redacted = settings.database_url_redacted
    assert "supersecretpass" not in redacted
    assert "secretuser" in redacted
    assert "ep-pooler.neon.tech" in redacted
    assert "sslmode=require" in redacted

    # 3. Direct unpooled alias support
    alias_settings = Settings(
        DATABASE_DIRECT_URL=None,
        DATABASE_URL_UNPOOLED=SecretStr("postgresql://admin:directpass@ep-direct.neon.tech/neondb"),
    )
    assert alias_settings.database_direct_url_unmasked is not None
    assert "postgresql+psycopg://" in alias_settings.database_direct_url_unmasked
    assert "directpass" not in alias_settings.database_direct_url_redacted
    assert "admin:***@" in alias_settings.database_direct_url_redacted


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
