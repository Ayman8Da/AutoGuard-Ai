"""Unit tests for narrative providers and strict response parsing."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from app.agents.llm import (
    GroqNarrativeClient,
    InvalidLLMResponseError,
    LLMUnavailableError,
    MockNarrativeClient,
    NarrativeRequest,
    OllamaNarrativeClient,
    _parse_narrative,
    build_narrative_client,
)
from app.core.config import Environment, LLMProvider, Settings
from pydantic import ValidationError


def _request() -> NarrativeRequest:
    return NarrativeRequest(
        vehicle_id="VH-001",
        findings=[],
        dtc_interpretations=[],
        suspected_faults=[],
        unavailable_sensors=[],
    )


class _FakeCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self._content = content
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


def _fake_groq(content: str | None = None, error: Exception | None = None):
    completions = _FakeCompletions(content, error)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


@pytest.mark.asyncio
async def test_mock_client_summarises_findings_and_clean_frames() -> None:
    client = MockNarrativeClient()

    clean = await client.summarise(_request())
    assert "No abnormal sensor readings" in clean

    request = _request().model_copy(
        update={
            "findings": [
                {
                    "code": "ENGINE_TEMPERATURE_HIGH",
                    "title": "High",
                    "detail": "Hot",
                    "severity": "high",
                }
            ],
            "suspected_faults": ["Cooling system fault"],
        }
    )
    summary = await client.summarise(request)
    assert "1 abnormal reading(s)" in summary
    assert "Cooling system fault" in summary


def test_parse_narrative_accepts_json_object() -> None:
    assert _parse_narrative('{"summary": "Engine is overheating."}') == (
        "Engine is overheating."
    )


def test_parse_narrative_strips_markdown_fence() -> None:
    content = '```json\n{"summary": "Battery voltage is low."}\n```'

    assert _parse_narrative(content) == "Battery voltage is low."


@pytest.mark.parametrize(
    "content",
    [
        "not json at all",
        '{"summary": ""}',
        '{"summary": "ok", "risk_level": "low"}',
        '["not", "an", "object"]',
    ],
)
def test_parse_narrative_rejects_invalid_responses(content: str) -> None:
    with pytest.raises(InvalidLLMResponseError):
        _parse_narrative(content)


@pytest.mark.asyncio
async def test_groq_client_returns_validated_summary() -> None:
    fake_client, completions = _fake_groq('{"summary": "Cooling system fault suspected."}')
    client = GroqNarrativeClient(
        api_key="test-key", model="test-model", timeout_seconds=5, client=fake_client
    )

    summary = await client.summarise(_request())

    assert summary == "Cooling system fault suspected."
    call = completions.calls[0]
    assert call["model"] == "test-model"
    assert call["response_format"] == {"type": "json_object"}
    assert call["temperature"] == 0
    assert call["messages"][0]["role"] == "system"


@pytest.mark.asyncio
async def test_groq_client_wraps_transport_failures() -> None:
    fake_client, _ = _fake_groq(error=RuntimeError("connection refused"))
    client = GroqNarrativeClient(
        api_key="test-key", model="test-model", timeout_seconds=5, client=fake_client
    )

    with pytest.raises(LLMUnavailableError, match="connection refused"):
        await client.summarise(_request())


@pytest.mark.asyncio
async def test_groq_client_rejects_invalid_json() -> None:
    fake_client, _ = _fake_groq("not-json")
    client = GroqNarrativeClient(
        api_key="test-key", model="test-model", timeout_seconds=5, client=fake_client
    )

    with pytest.raises(InvalidLLMResponseError):
        await client.summarise(_request())


@pytest.mark.asyncio
async def test_ollama_client_returns_validated_summary() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200, json={"message": {"content": '{"summary": "Inspect ignition system."}'}}
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaNarrativeClient(
            base_url="http://ollama:11434/",
            model="llama3",
            timeout_seconds=5,
            http_client=http_client,
        )
        summary = await client.summarise(_request())

    assert summary == "Inspect ignition system."
    assert captured["url"] == "http://ollama:11434/api/chat"
    assert captured["payload"]["format"] == "json"
    assert captured["payload"]["model"] == "llama3"


@pytest.mark.asyncio
async def test_ollama_client_wraps_http_errors() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503, text="down"))
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaNarrativeClient(
            base_url="http://ollama:11434",
            model="llama3",
            timeout_seconds=5,
            http_client=http_client,
        )
        with pytest.raises(LLMUnavailableError, match="Ollama request failed"):
            await client.summarise(_request())


def _settings(provider: LLMProvider, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "environment": Environment.TEST,
        "llm_provider": provider,
    }
    values.update(overrides)
    return Settings(**values)


def test_build_narrative_client_selects_provider() -> None:
    assert isinstance(build_narrative_client(_settings(LLMProvider.MOCK)), MockNarrativeClient)
    assert isinstance(
        build_narrative_client(_settings(LLMProvider.OLLAMA)), OllamaNarrativeClient
    )
    assert isinstance(
        build_narrative_client(_settings(LLMProvider.GROQ, groq_api_key="secret")),
        GroqNarrativeClient,
    )


def test_groq_provider_requires_an_api_key() -> None:
    with pytest.raises(ValidationError, match="AUTOGUARD_GROQ_API_KEY"):
        _settings(LLMProvider.GROQ)
