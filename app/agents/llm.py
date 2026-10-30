"""LLM narrative providers.

The LLM has a deliberately narrow job: turn **already computed** findings into a
short human-readable summary. It cannot assign risk levels, invent readings or
claim that a repair happened. All provider responses are validated against a
strict Pydantic schema, and failures degrade to a deterministic summary instead
of failing the safety-critical workflow.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx
from groq import AsyncGroq
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import LLMProvider, Settings
from app.models.diagnostics import DTCInterpretation, Finding

_SYSTEM_PROMPT = (
    "You are an automotive diagnostic assistant. Summarise the supplied structured "
    "findings in at most three sentences. Rules: never assign or change a risk level; "
    "never claim an inspection or repair was performed; never invent sensor values, "
    "faults or trouble codes. Respond with a single JSON object exactly like "
    '{"summary": "..."}.'
)


class LLMError(Exception):
    """Base class for narrative provider failures."""


class LLMUnavailableError(LLMError):
    """The provider could not be reached or returned an error."""


class InvalidLLMResponseError(LLMError):
    """The provider responded, but not with valid structured JSON."""


class NarrativeRequest(BaseModel):
    """Everything the LLM is allowed to see."""

    vehicle_id: str
    findings: list[Finding]
    dtc_interpretations: list[DTCInterpretation]
    suspected_faults: list[str]
    unavailable_sensors: list[str]


class NarrativeOutput(BaseModel):
    """Validated LLM response schema. Extra keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=800)


class NarrativeClient(Protocol):
    """Minimal interface implemented by mock, Groq and Ollama providers."""

    provider_name: str

    async def summarise(self, request: NarrativeRequest) -> str: ...


def _parse_narrative(content: str) -> str:
    """Parse and validate the provider's JSON response."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidLLMResponseError("LLM response was not valid JSON") from exc
    try:
        return NarrativeOutput.model_validate(payload).summary
    except ValidationError as exc:
        raise InvalidLLMResponseError("LLM response did not match the summary schema") from exc


class MockNarrativeClient:
    """Deterministic, offline narrative used by default and in tests."""

    provider_name = "mock"

    async def summarise(self, request: NarrativeRequest) -> str:
        if not request.findings and not request.dtc_interpretations:
            return (
                "No abnormal sensor readings or diagnostic trouble codes were detected "
                "in this telemetry frame."
            )
        suspects = "; ".join(request.suspected_faults[:3]) or "further inspection required"
        codes = ", ".join(item.code for item in request.dtc_interpretations) or "none"
        return (
            f"{len(request.findings)} abnormal reading(s) detected. "
            f"Suspected causes: {suspects}. Trouble codes: {codes}."
        )


class GroqNarrativeClient:
    """Groq JSON-mode inference with strict output validation."""

    provider_name = "groq"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        *,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._client = client or AsyncGroq(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )

    async def summarise(self, request: NarrativeRequest) -> str:
        prompt = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
        except Exception as exc:
            raise LLMUnavailableError(
                f"Groq request failed ({type(exc).__name__}): {str(exc)[:200]}"
            ) from exc

        content = response.choices[0].message.content or ""
        return _parse_narrative(content)


class OllamaNarrativeClient:
    """Local Ollama inference via /api/chat in JSON mode."""

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        self._http_client = http_client

    async def summarise(self, request: NarrativeRequest) -> str:
        prompt = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
        payload = {
            "model": self._model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }

        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]
        except Exception as exc:
            raise LLMUnavailableError(
                f"Ollama request failed ({type(exc).__name__}): {str(exc)[:200]}"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        return _parse_narrative(content)


def build_narrative_client(settings: Settings) -> NarrativeClient:
    """Build the configured narrative provider (mock by default)."""
    if settings.llm_provider is LLMProvider.GROQ:
        secret = settings.groq_api_key.get_secret_value() if settings.groq_api_key else ""
        return GroqNarrativeClient(
            api_key=secret,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if settings.llm_provider is LLMProvider.OLLAMA:
        return OllamaNarrativeClient(
            base_url=settings.ollama_base_url,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return MockNarrativeClient()
