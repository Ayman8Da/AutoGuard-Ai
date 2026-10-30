"""Persistence for completed diagnostic reports.

Mirrors the telemetry repository contract: a bounded in-memory implementation
behind a protocol, so a database-backed store can be substituted without
changing the API or workflow layers.
"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Protocol

from app.models.diagnostics import DiagnosticReport


class DiagnosticRepository(Protocol):
    """Storage contract for completed diagnostic reports."""

    def add(self, report: DiagnosticReport) -> None: ...

    def get(self, diagnostic_id: str) -> DiagnosticReport | None: ...

    def list_recent(self, limit: int = 50) -> list[DiagnosticReport]: ...

    def count(self) -> int: ...


class InMemoryDiagnosticRepository:
    """Thread-safe, bounded, newest-first in-memory report store."""

    def __init__(self, max_entries: int = 500) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_entries = max_entries
        self._reports: deque[DiagnosticReport] = deque()
        self._by_id: dict[str, DiagnosticReport] = {}
        self._lock = Lock()

    def add(self, report: DiagnosticReport) -> None:
        with self._lock:
            while len(self._reports) >= self._max_entries:
                evicted = self._reports.popleft()
                self._by_id.pop(evicted.diagnostic_id, None)
            self._reports.append(report)
            self._by_id[report.diagnostic_id] = report

    def get(self, diagnostic_id: str) -> DiagnosticReport | None:
        with self._lock:
            return self._by_id.get(diagnostic_id)

    def list_recent(self, limit: int = 50) -> list[DiagnosticReport]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        with self._lock:
            return list(reversed(self._reports))[:limit]

    def count(self) -> int:
        with self._lock:
            return len(self._reports)
