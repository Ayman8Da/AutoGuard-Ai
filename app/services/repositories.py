"""Telemetry persistence behind a small repository interface.

The in-memory implementation keeps the newest ``max_entries`` records and is
process-local: data is lost on restart. A MongoDB-backed implementation can be
added later without changing the API or agent layers, because both depend on
the ``TelemetryRepository`` protocol only.
"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Protocol

from app.models.telemetry import TelemetryRecord


class TelemetryRepository(Protocol):
    """Storage contract for ingested telemetry."""

    def add(self, record: TelemetryRecord) -> None: ...

    def get(self, telemetry_id: str) -> TelemetryRecord | None: ...

    def latest_for_vehicle(self, vehicle_id: str) -> TelemetryRecord | None: ...

    def list_for_vehicle(self, vehicle_id: str, limit: int = 50) -> list[TelemetryRecord]: ...

    def count(self) -> int: ...


class InMemoryTelemetryRepository:
    """Thread-safe, bounded in-memory telemetry store."""

    def __init__(self, max_entries: int = 1000) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_entries = max_entries
        self._records: deque[TelemetryRecord] = deque()
        self._by_id: dict[str, TelemetryRecord] = {}
        self._lock = Lock()

    def add(self, record: TelemetryRecord) -> None:
        with self._lock:
            while len(self._records) >= self._max_entries:
                evicted = self._records.popleft()
                self._by_id.pop(evicted.telemetry_id, None)
            self._records.append(record)
            self._by_id[record.telemetry_id] = record

    def get(self, telemetry_id: str) -> TelemetryRecord | None:
        with self._lock:
            return self._by_id.get(telemetry_id)

    def latest_for_vehicle(self, vehicle_id: str) -> TelemetryRecord | None:
        with self._lock:
            for record in reversed(self._records):
                if record.telemetry.vehicle_id == vehicle_id:
                    return record
        return None

    def list_for_vehicle(self, vehicle_id: str, limit: int = 50) -> list[TelemetryRecord]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        with self._lock:
            matches = [
                record
                for record in reversed(self._records)
                if record.telemetry.vehicle_id == vehicle_id
            ][:limit]
        return matches

    def count(self) -> int:
        with self._lock:
            return len(self._records)
