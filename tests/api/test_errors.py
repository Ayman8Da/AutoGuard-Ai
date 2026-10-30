"""API tests for the uniform error envelope and failure handling."""

from __future__ import annotations

from app.core.correlation import CORRELATION_HEADER, CORRELATION_ID_PATTERN
from app.core.errors import NotFoundError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel


def test_unknown_route_returns_structured_404(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert CORRELATION_ID_PATTERN.fullmatch(body["error"]["correlation_id"])
    assert response.headers[CORRELATION_HEADER] == body["error"]["correlation_id"]


def test_method_not_allowed_uses_error_envelope(client: TestClient) -> None:
    response = client.post("/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


class _Payload(BaseModel):
    value: int


def test_validation_error_uses_error_envelope(client: TestClient, app: FastAPI) -> None:
    @app.post("/__test__/validate")
    async def _validate(payload: _Payload) -> _Payload:
        return payload

    response = client.post("/__test__/validate", json={"value": "not-a-number"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Request payload validation failed."
    assert isinstance(body["error"]["details"], list)
    assert body["error"]["details"][0]["loc"] == ["body", "value"]
    assert response.headers[CORRELATION_HEADER] == body["error"]["correlation_id"]


def test_domain_error_uses_its_status_and_details(client: TestClient, app: FastAPI) -> None:
    @app.get("/__test__/diagnostic-missing")
    async def _missing_diagnostic() -> None:
        raise NotFoundError(
            "Diagnostic report not found.",
            details={"diagnostic_id": "diag-404"},
        )

    response = client.get("/__test__/diagnostic-missing")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Diagnostic report not found."
    assert body["error"]["details"] == {"diagnostic_id": "diag-404"}
    assert response.headers[CORRELATION_HEADER] == body["error"]["correlation_id"]


def test_unhandled_exception_returns_safe_envelope(client: TestClient, app: FastAPI) -> None:
    @app.get("/__test__/boom")
    async def _boom() -> None:
        raise RuntimeError("secret internal details")

    response = client.get("/__test__/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "secret internal details" not in response.text
    assert CORRELATION_ID_PATTERN.fullmatch(body["error"]["correlation_id"])
    assert response.headers[CORRELATION_HEADER] == body["error"]["correlation_id"]


def test_unhandled_exception_reuses_supplied_correlation_id(
    client: TestClient, app: FastAPI
) -> None:
    @app.get("/__test__/boom-with-id")
    async def _boom_with_id() -> None:
        raise ValueError("boom")

    correlation_id = "CORR-20261030-FAILURE0001"
    response = client.get(
        "/__test__/boom-with-id", headers={CORRELATION_HEADER: correlation_id}
    )

    assert response.status_code == 500
    assert response.headers[CORRELATION_HEADER] == correlation_id
    assert response.json()["error"]["correlation_id"] == correlation_id
