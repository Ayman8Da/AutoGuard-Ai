"""API tests for service metadata, health probe and documentation."""

from __future__ import annotations

import re

from app.core.correlation import CORRELATION_HEADER, CORRELATION_ID_PATTERN
from fastapi.testclient import TestClient


def test_health_returns_ok_with_checks(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "AutoGuard AI"
    assert body["version"] == "0.1.0"
    assert body["environment"] == "test"
    assert body["uptime_seconds"] >= 0
    assert body["checks"]["api"]["status"] == "ok"
    assert body["checks"]["configuration"]["status"] == "ok"
    assert CORRELATION_ID_PATTERN.fullmatch(body["correlation_id"])


def test_health_response_carries_correlation_header(client: TestClient) -> None:
    response = client.get("/health")

    header = response.headers[CORRELATION_HEADER]
    assert header == response.json()["correlation_id"]
    assert CORRELATION_ID_PATTERN.fullmatch(header)


def test_client_correlation_id_is_propagated(client: TestClient) -> None:
    correlation_id = "CORR-20261030-TESTCLIENT01"

    response = client.get("/health", headers={CORRELATION_HEADER: correlation_id})

    assert response.status_code == 200
    assert response.headers[CORRELATION_HEADER] == correlation_id
    assert response.json()["correlation_id"] == correlation_id


def test_invalid_correlation_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={CORRELATION_HEADER: "not a valid id!"})

    generated = response.headers[CORRELATION_HEADER]
    assert generated != "not a valid id!"
    assert CORRELATION_ID_PATTERN.fullmatch(generated)
    assert response.json()["correlation_id"] == generated


def test_each_request_gets_a_unique_correlation_id(client: TestClient) -> None:
    first = client.get("/health").headers[CORRELATION_HEADER]
    second = client.get("/health").headers[CORRELATION_HEADER]

    assert first != second


def test_root_returns_service_metadata(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["docs"] == "/docs"
    assert body["health"] == "/health"
    assert body["api_prefix"] == "/api/v1"


def test_openapi_schema_is_available(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "AutoGuard AI"
    assert "/health" in schema["paths"]


def test_swagger_ui_is_served(client: TestClient) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower()


def test_health_correlation_id_matches_observability_log_contract(
    client: TestClient,
) -> None:
    response = client.get("/health", headers={CORRELATION_HEADER: "CORR-20261030-LOGCONTRACT"})

    assert re.fullmatch(r"CORR-\d{8}-[A-Za-z0-9]+", response.headers[CORRELATION_HEADER])
