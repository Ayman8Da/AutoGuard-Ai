"""Diagnostic workflow use cases exposed to the API layer."""

from __future__ import annotations

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.diagnostics import DiagnosticReport, DiagnosticSummary
from app.models.telemetry import TelemetryRecord
from app.orchestration.workflow import DiagnosticWorkflow
from app.services.diagnostics_repository import DiagnosticRepository

logger = get_logger("services.diagnostics")


class DiagnosticsService:
    """Runs the workflow, stores reports and serves read models."""

    def __init__(
        self,
        repository: DiagnosticRepository,
        workflow: DiagnosticWorkflow,
    ) -> None:
        self._repository = repository
        self._workflow = workflow

    async def analyze(self, telemetry_record: TelemetryRecord) -> DiagnosticReport:
        """Run the multi-agent workflow for a stored telemetry frame."""
        report = await self._workflow.run(telemetry_record)
        self._repository.add(report)
        return report

    def list_reports(self, limit: int = 50) -> list[DiagnosticSummary]:
        """Return the newest reports first as compact summaries."""
        return [
            DiagnosticSummary(
                diagnostic_id=report.diagnostic_id,
                workflow_id=report.workflow_id,
                vehicle_id=report.vehicle_id,
                created_at=report.created_at,
                status=report.status,
                analysis_mode=report.analysis_mode,
                risk_level=report.risk.level,
                correlation_id=report.correlation_id,
            )
            for report in self._repository.list_recent(limit=limit)
        ]

    def get_report(self, diagnostic_id: str) -> DiagnosticReport:
        """Return one full report or raise ``DIAGNOSTIC_NOT_FOUND``."""
        report = self._repository.get(diagnostic_id)
        if report is None:
            raise NotFoundError(
                f"Diagnostic report '{diagnostic_id}' was not found.",
                code="DIAGNOSTIC_NOT_FOUND",
                details={"diagnostic_id": diagnostic_id},
            )
        return report
