"""Unit tests for typed configuration loading and validation."""

from __future__ import annotations

import pytest
from app.core.config import Environment, LLMProvider, LogFormat, Settings
from pydantic import ValidationError


def test_defaults_are_safe_for_local_development() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "AutoGuard AI"
    assert settings.environment is Environment.LOCAL
    assert settings.llm_provider is LLMProvider.MOCK
    assert settings.log_format is LogFormat.JSON
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.is_production is False
    assert settings.groq_api_key is None


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOGUARD_ENVIRONMENT", "production")
    monkeypatch.setenv("AUTOGUARD_LOG_LEVEL", "debug")
    monkeypatch.setenv("AUTOGUARD_CORS_ORIGINS", "https://a.example, https://b.example")

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.PRODUCTION
    assert settings.is_production is True
    assert settings.log_level == "DEBUG"
    assert settings.cors_origin_list == ["https://a.example", "https://b.example"]


def test_groq_provider_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="AUTOGUARD_GROQ_API_KEY"):
        Settings(_env_file=None, llm_provider="groq")


def test_groq_key_is_stored_as_secret() -> None:
    settings = Settings(_env_file=None, llm_provider="groq", groq_api_key="gsk_unit_test")

    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == "gsk_unit_test"
    assert "gsk_unit_test" not in repr(settings)


def test_blank_groq_key_is_treated_as_missing() -> None:
    settings = Settings(_env_file=None, llm_provider="mock", groq_api_key="   ")

    assert settings.groq_api_key is None


@pytest.mark.parametrize("prefix", ["api/v1", "/api/v1/", "/api v1", ""])
def test_invalid_api_prefix_rejected(prefix: str) -> None:
    with pytest.raises(ValidationError, match="api_v1_prefix"):
        Settings(_env_file=None, api_v1_prefix=prefix)


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ValidationError, match="log_level"):
        Settings(_env_file=None, log_level="VERBOSE")


@pytest.mark.parametrize("value", [-1.0, 0.0, 301.0])
def test_llm_timeout_must_be_bounded(value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_timeout_seconds=value)


def test_cors_origin_list_ignores_blanks() -> None:
    settings = Settings(_env_file=None, cors_origins=" , https://app.example , ")

    assert settings.cors_origin_list == ["https://app.example"]
