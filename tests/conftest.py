"""Shared pytest fixtures. No external services or API keys are required."""

from __future__ import annotations

import pytest
from app.core.config import Environment, LLMProvider, LogFormat, Settings
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def settings() -> Settings:
    """Deterministic settings for tests: no .env, mock LLM, quiet logs."""
    return Settings(
        _env_file=None,
        environment=Environment.TEST,
        debug=False,
        log_level="WARNING",
        log_format=LogFormat.JSON,
        llm_provider=LLMProvider.MOCK,
        groq_api_key=None,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """Fresh application instance per test (isolated in-memory state)."""
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """TestClient with lifespan events executed."""
    with TestClient(app) as test_client:
        yield test_client
