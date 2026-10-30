"""Unit tests for the bounded diagnostic report repository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.agents.diagnostic import DiagnosticAgent
from app.agents.llm import MockNarrativeClient
from app.agents.maintenance import MaintenanceAgent
from app.agents.reporting import ReportingAgent
from app.agents.risk import RiskAssessmentAgent
from app.models.telemetry import TelemetryRecord
from app.services.diagnostics_repository import InMemoryDiagnosticRepository
from app.utils.ids import generate_id
from simulator.scenarios import Scenario
from simulator.vehicle_simulator import build_scenario_telemetry


async def _report(scenario: Scenario, created_at: datetime):
    record = TelemetryRecord(
        telemetry_id=generate_id("TEL", created_at),
        correlation_id="CORR-20261030-REPOSITORY1",
        received_at=created_at,
        telemetry=build_scenario_telemetry(scenario, "VH-001", created_at),
    )
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(record.telemetry)
    risk = RiskAssessmentAgent().assess(record.telemetry, diagnostic)
    maintenance = MaintenanceAgent().recommend(diagnostic, risk)
    report = ReportingAgent().build(
        telemetry_record=record,
        workflow_id=generate_id("WF", created_at),
        diagnostic=diagnostic,
        risk=risk,
        maintenance=maintenance,
        executions=[],
        warnings=[],
    )
    return report


@pytest.mark.asyncio
async def test_add_and_get_round_trip() -> None:
    repository = InMemoryDiagnosticRepository()
    report = await _report(Scenario.NORMAL, datetime(2025, 1, 15, 8, 0, tzinfo=UTC))

    repository.add(report)

    assert repository.get(report.diagnostic_id) == report
    assert repository.get("DIAG-UNKNOWN") is None
    assert repository.count() == 1


@pytest.mark.asyncio
async def test_list_recent_is_newest_first_and_limited() -> None:
    repository = InMemoryDiagnosticRepository()
    base = datetime(2025, 1, 15, 8, 0, tzinfo=UTC)
    first = await _report(Scenario.NORMAL, base)
    second = await _report(Scenario.WARNING, base)
    third = await _report(Scenario.CRITICAL, base)
    for report in (first, second, third):
        repository.add(report)

    assert repository.list_recent() == [third, second, first]
    assert repository.list_recent(limit=2) == [third, second]

    with pytest.raises(ValueError, match="limit"):
        repository.list_recent(limit=0)


@pytest.mark.asyncio
async def test_capacity_evicts_oldest_reports() -> None:
    repository = InMemoryDiagnosticRepository(max_entries=2)
    base = datetime(2025, 1, 15, 8, 0, tzinfo=UTC)
    first = await _report(Scenario.NORMAL, base)
    second = await _report(Scenario.WARNING, base)
    third = await _report(Scenario.CRITICAL, base)

    for report in (first, second, third):
        repository.add(report)

    assert repository.count() == 2
    assert repository.get(first.diagnostic_id) is None
    assert repository.get(second.diagnostic_id) == second
    assert repository.get(third.diagnostic_id) == third


def test_invalid_capacity_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        InMemoryDiagnosticRepository(max_entries=0)
