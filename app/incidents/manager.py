"""Incident management.

Incidents are derived from workflow outcomes:

* ``CRITICAL_VEHICLE_RISK``   — a CRITICAL deterministic risk classification;
* ``LLM_PROVIDER_FAILURE``    — the report was degraded because narration failed;
* ``AGENT_EXECUTION_FAILED``  — an agent exhausted its retry budget.

Every incident is linked to the correlation ID and, where available, the
diagnostic/workflow IDs and a runbook.
"""

from __future__ import annotations

from collections import deque
from threading import Lock

from app.core.errors import AgentExecutionError
from app.core.logging import get_logger
from app.incidents.models import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
)
from app.incidents.runbooks import get_runbook
from app.models.diagnostics import DiagnosticReport, RiskLevel
from app.utils.ids import generate_id
from app.utils.time import utc_now

logger = get_logger("incidents.manager")

LLM_NARRATIVE_WARNING = "LLM_NARRATIVE_UNAVAILABLE"


class IncidentManager:
    """Creates, stores and filters bounded, in-memory incidents."""

    def __init__(self, max_entries: int = 500) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_entries = max_entries
        self._incidents: deque[Incident] = deque()
        self._by_id: dict[str, Incident] = {}
        self._lock = Lock()

    # ------------------------------------------------------------------ #
    # Creation
    # ------------------------------------------------------------------ #

    def process_report(self, report: DiagnosticReport) -> list[Incident]:
        """Create incidents implied by a completed report."""
        created: list[Incident] = []

        if report.risk.level is RiskLevel.CRITICAL:
            created.append(
                self._create(
                    code="CRITICAL_VEHICLE_RISK",
                    title=f"Critical vehicle risk on {report.vehicle_id}",
                    description=(
                        f"Deterministic risk assessment returned CRITICAL (score "
                        f"{report.risk.score}). Hard safety override: "
                        f"{'yes' if report.risk.hard_override else 'no'}. "
                        "The vehicle requires inspection before further use."
                    ),
                    severity=IncidentSeverity.CRITICAL,
                    runbook_id="high_risk_vehicle",
                    correlation_id=report.correlation_id,
                    vehicle_id=report.vehicle_id,
                    diagnostic_id=report.diagnostic_id,
                    workflow_id=report.workflow_id,
                    metadata={
                        "risk_score": report.risk.score,
                        "hard_override": report.risk.hard_override,
                        "finding_codes": [finding.code for finding in report.diagnostic.findings],
                        "dtc_codes": [item.code for item in report.diagnostic.dtc_interpretations],
                    },
                )
            )

        if any(warning.code == LLM_NARRATIVE_WARNING for warning in report.warnings):
            created.append(
                self._create(
                    code="LLM_PROVIDER_FAILURE",
                    title="Narrative provider unavailable",
                    description=(
                        "The report was produced in degraded deterministic mode because the "
                        "LLM narrative provider failed. Findings and risk are unaffected; "
                        "the summary is a deterministic fallback."
                    ),
                    severity=IncidentSeverity.MEDIUM,
                    runbook_id="llm_provider_failure",
                    correlation_id=report.correlation_id,
                    vehicle_id=report.vehicle_id,
                    diagnostic_id=report.diagnostic_id,
                    workflow_id=report.workflow_id,
                    metadata={
                        "analysis_mode": report.analysis_mode.value,
                        "llm_attempts": report.diagnostic.llm_attempts,
                        "llm_error": report.diagnostic.llm_error,
                    },
                )
            )

        return created

    def record_agent_failure(
        self, error: AgentExecutionError, correlation_id: str
    ) -> Incident:
        """Create an incident for a workflow that aborted after retries."""
        details = error.details if isinstance(error.details, dict) else {}
        agent_name = str(details.get("agent_name", "unknown agent"))
        workflow_id = details.get("workflow_id")
        attempts = details.get("attempts")
        error_type = details.get("error_type", "UnknownError")

        return self._create(
            code="AGENT_EXECUTION_FAILED",
            title=f"{agent_name} failed",
            description=(
                f"{agent_name} exhausted its retry budget after {attempts} attempt(s) "
                f"({error_type}). No diagnostic report was produced for this telemetry "
                "frame."
            ),
            severity=IncidentSeverity.HIGH,
            runbook_id="agent_failure",
            correlation_id=correlation_id,
            workflow_id=str(workflow_id) if workflow_id else None,
            metadata={
                "agent_name": agent_name,
                "attempts": attempts,
                "error_type": error_type,
                "error_message": error.message,
            },
        )

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def list_incidents(
        self,
        *,
        limit: int = 50,
        status: IncidentStatus | None = None,
        severity: IncidentSeverity | None = None,
        vehicle_id: str | None = None,
    ) -> list[Incident]:
        """Return newest incidents first, optionally filtered."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        with self._lock:
            matches = [
                incident
                for incident in reversed(self._incidents)
                if (status is None or incident.status is status)
                and (severity is None or incident.severity is severity)
                and (vehicle_id is None or incident.vehicle_id == vehicle_id)
            ][:limit]
        return matches

    def get_incident(self, incident_id: str) -> Incident | None:
        """Return one incident, or ``None`` when it does not exist."""
        with self._lock:
            return self._by_id.get(incident_id)

    def count(self) -> int:
        with self._lock:
            return len(self._incidents)

    def active_count(self) -> int:
        """Incidents that are not resolved."""
        with self._lock:
            return sum(
                1 for incident in self._incidents if incident.status is not IncidentStatus.RESOLVED
            )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _create(
        self,
        *,
        code: str,
        title: str,
        description: str,
        severity: IncidentSeverity,
        runbook_id: str,
        correlation_id: str,
        vehicle_id: str | None = None,
        diagnostic_id: str | None = None,
        workflow_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Incident:
        runbook = get_runbook(runbook_id)
        now = utc_now()
        incident = Incident(
            incident_id=generate_id("INC", now),
            code=code,
            title=title,
            description=description,
            severity=severity,
            status=IncidentStatus.OPEN,
            runbook_id=runbook.runbook_id,
            runbook_title=runbook.title,
            vehicle_id=vehicle_id,
            diagnostic_id=diagnostic_id,
            workflow_id=workflow_id,
            correlation_id=correlation_id,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        with self._lock:
            while len(self._incidents) >= self._max_entries:
                evicted = self._incidents.popleft()
                self._by_id.pop(evicted.incident_id, None)
            self._incidents.append(incident)
            self._by_id[incident.incident_id] = incident

        logger.warning(
            "incident_created",
            extra={
                "incident_id": incident.incident_id,
                "incident_code": incident.code,
                "severity": incident.severity.value,
                "runbook_id": incident.runbook_id,
                "vehicle_id": incident.vehicle_id,
                "diagnostic_id": incident.diagnostic_id,
                "workflow_id": incident.workflow_id,
            },
        )
        return incident
