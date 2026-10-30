"""Typed application configuration.

Every setting is read from the process environment using the ``AUTOGUARD_``
prefix (or from a local ``.env`` file). Secrets are wrapped in ``SecretStr`` so
they can never leak through logs or ``repr()`` output.
"""

from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__

_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_API_PREFIX_PATTERN = re.compile(r"^/[A-Za-z0-9/_-]*$")


class Environment(StrEnum):
    """Deployment environment the process is running in."""

    LOCAL = "local"
    TEST = "test"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogFormat(StrEnum):
    """Log rendering format."""

    JSON = "json"
    CONSOLE = "console"


class LLMProvider(StrEnum):
    """Inference backend used by the LLM-backed agents."""

    MOCK = "mock"
    GROQ = "groq"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    """Runtime configuration for the AutoGuard AI service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AUTOGUARD_",
        case_sensitive=False,
        extra="ignore",
    )

    # Service identity
    app_name: str = "AutoGuard AI"
    app_version: str = __version__
    environment: Environment = Environment.LOCAL
    debug: bool = False

    # HTTP API
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = ""

    # Logging
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON

    # Agents / LLM inference
    llm_provider: LLMProvider = LLMProvider.MOCK
    llm_model: str = "llama-3.3-70b-versatile"
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    groq_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"
    agent_max_retries: int = Field(default=1, ge=0, le=3)

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in _LOG_LEVELS:
            allowed = ", ".join(sorted(_LOG_LEVELS))
            raise ValueError(f"log_level must be one of: {allowed}")
        return level

    @field_validator("api_v1_prefix")
    @classmethod
    def _validate_api_prefix(cls, value: str) -> str:
        prefix = value.strip()
        if not _API_PREFIX_PATTERN.fullmatch(prefix):
            raise ValueError(
                "api_v1_prefix must start with '/' and contain only URL-safe characters"
            )
        if len(prefix) > 1 and prefix.endswith("/"):
            raise ValueError("api_v1_prefix must not end with '/'")
        return prefix

    @field_validator("cors_origins")
    @classmethod
    def _strip_cors_origins(cls, value: str) -> str:
        return value.strip()

    @field_validator("groq_api_key", mode="before")
    @classmethod
    def _blank_secret_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _require_groq_credentials(self) -> Settings:
        if self.llm_provider is LLMProvider.GROQ:
            secret = self.groq_api_key.get_secret_value() if self.groq_api_key else ""
            if not secret.strip():
                raise ValueError(
                    "AUTOGUARD_GROQ_API_KEY is required when AUTOGUARD_LLM_PROVIDER=groq"
                )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins parsed from the comma-separated environment value."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
