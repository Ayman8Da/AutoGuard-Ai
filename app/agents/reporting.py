"""Reporting Agent: assembles the traceable diagnostic report."""

from __future__ import annotations

from app.core.logging import get_logger
from app.models.diagnostics import (
    AgentExecution,
    AnalysisMode,
    DiagnosticReport,
    DiagnosticResult,
    MaintenancePlan,
    ReportStatus,
    ReportWarning,
    RiskAssessment,
)
from app.models.telemetry import TelemetryRecord
from app.utils.ids import generate_id
from app.utils.time import utc_now

logger = get_logger("agents.reporting")

DISCLAIMER = (
    "Simulated telemetry only. This report is an engineering demonstration, not a "
    "validated automotive diagnosis. No physical inspection or repair has been performed."
)


class ReportingAgent:
    """Builds the final report and derives explicit status/analysis mode."""

    name = "ReportingAgent"

    def build(
        self,
        *,
        telemetry_record: TelemetryRecord,
        workflow_id: str,
        diagnostic: DiagnosticResult,
        risk: RiskAssessment,
        maintenance: MaintenancePlan,
        executions: list[AgentExecution],
        warnings: list[ReportWarning],
    ) -> DiagnosticReport:
        if diagnostic.narrative_source == "fallback":
            analysis_mode = AnalysisMode.DEGRADED_DETERMINISTIC
        elif diagnostic.narrative_source == "llm":
            analysis_mode = AnalysisMode.LLM_ASSISTED
        else:
            analysis_mode = AnalysisMode.DETERMINISTIC

        status = ReportStatus.COMPLETED_DEGRADED if warnings else ReportStatus.COMPLETED

        report = DiagnosticReport(
            diagnostic_id=generate_id("DIAG"),
            workflow_id=workflow_id,
            telemetry_id=telemetry_record.telemetry_id,
            correlation_id=telemetry_record.correlation_id,
            vehicle_id=telemetry_record.telemetry.vehicle_id,
            created_at=utc_now(),
            status=status,
            analysis_mode=analysis_mode,
            telemetry=telemetry_record.telemetry,
            diagnostic=diagnostic,
            risk=risk,
            maintenance=maintenance,
            agent_executions=executions,
            warnings=warnings,
            disclaimer=DISCLAIMER,
        )
        logger.info(
            "diagnostic_report_built",
            extra={
                "diagnostic_id": report.diagnostic_id,
                "workflow_id": workflow_id,
                "vehicle_id": report.vehicle_id,
                "risk_level": risk.level.value,
                "status": status.value,
                "analysis_mode": analysis_mode.value,
            },
        )
        return report
