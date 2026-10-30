"""Unit tests for the in-memory telemetry repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.telemetry import TelemetryRecord
from app.services.repositories import InMemoryTelemetryRepository
from app.utils.ids import generate_id
from simulator.scenarios import Scenario
from simulator.vehicle_simulator import build_scenario_telemetry


def _record(
    vehicle_id: str = "VH-001",
    timestamp: datetime | None = None,
    scenario: Scenario = Scenario.NORMAL,
) -> TelemetryRecord:
    moment = timestamp or datetime(2025, 1, 15, 8, 0, tzinfo=UTC)
    return TelemetryRecord(
        telemetry_id=generate_id("TEL", moment),
        correlation_id="CORR-20261030-REPOSITORY01",
        received_at=moment,
        telemetry=build_scenario_telemetry(scenario, vehicle_id, moment),
    )


def test_add_and_get_round_trip() -> None:
    repository = InMemoryTelemetryRepository()
    record = _record()

    repository.add(record)

    assert repository.get(record.telemetry_id) == record
    assert repository.count() == 1


def test_latest_for_vehicle_returns_newest_frame() -> None:
    repository = InMemoryTelemetryRepository()
    base = datetime(2025, 1, 15, 8, 0, tzinfo=UTC)
    older = _record(timestamp=base)
    newer = _record(timestamp=base + timedelta(minutes=5), scenario=Scenario.CRITICAL)
    repository.add(older)
    repository.add(newer)

    assert repository.latest_for_vehicle("VH-001") == newer
    assert repository.latest_for_vehicle("VH-002") is None


def test_list_for_vehicle_is_newest_first_and_filtered() -> None:
    repository = InMemoryTelemetryRepository()
    base = datetime(2025, 1, 15, 8, 0, tzinfo=UTC)
    first = _record("VH-001", base)
    second = _record("VH-002", base + timedelta(minutes=1))
    third = _record("VH-001", base + timedelta(minutes=2))
    for record in (first, second, third):
        repository.add(record)

    assert repository.list_for_vehicle("VH-001") == [third, first]
    assert repository.list_for_vehicle("VH-001", limit=1) == [third]
    assert repository.list_for_vehicle("VH-003") == []


def test_capacity_evicts_oldest_records() -> None:
    repository = InMemoryTelemetryRepository(max_entries=2)
    base = datetime(2025, 1, 15, 8, 0, tzinfo=UTC)
    records = [_record(timestamp=base + timedelta(minutes=index)) for index in range(3)]

    for record in records:
        repository.add(record)

    assert repository.count() == 2
    assert repository.get(records[0].telemetry_id) is None
    assert repository.get(records[1].telemetry_id) == records[1]
    assert repository.get(records[2].telemetry_id) == records[2]


def test_store_instances_are_isolated() -> None:
    first = InMemoryTelemetryRepository()
    second = InMemoryTelemetryRepository()
    first.add(_record())

    assert first.count() == 1
    assert second.count() == 0


def test_invalid_capacity_and_limit_are_rejected() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        InMemoryTelemetryRepository(max_entries=0)

    repository = InMemoryTelemetryRepository()
    with pytest.raises(ValueError, match="limit"):
        repository.list_for_vehicle("VH-001", limit=0)
