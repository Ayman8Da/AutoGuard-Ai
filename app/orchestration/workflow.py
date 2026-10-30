"""LangGraph diagnostic workflow.

Graph topology::

    START -> diagnostic -> risk -> maintenance -> reporting -> END

Each node is wrapped by :class:`AgentRunner`, which records an
``AgentExecution`` for every attempt and retries transient failures. The graph
is built per invocation so a workflow can never leak state or an execution
ledger into another request.
"""

from __future__ import annotations

import time

from langgraph.graph import END, START, StateGraph

from app.agents.diagnostic import DiagnosticAgent
from app.agents.maintenance import MaintenanceAgent
from app.agents.reporting import ReportingAgent
from app.agents.risk import RiskAssessmentAgent
from app.core.correlation import get_correlation_id
from app.core.logging import get_logger
from app.models.diagnostics import (
    AgentExecution,
    DiagnosticReport,
    ExecutionStatus,
    ReportWarning,
)
from app.models.telemetry import TelemetryRecord
from app.monitoring.agent import MonitoringAgent
from app.orchestration.runner import AgentRunner
from app.orchestration.state import WorkflowState
from app.utils.ids import generate_id
from app.utils.time import utc_now

logger = get_logger("orchestration.workflow")

LLM_NARRATIVE_WARNING = "LLM_NARRATIVE_UNAVAILABLE"
ORCHESTRATOR_AGENT_NAME = "OrchestratorAgent"


class DiagnosticWorkflow:
    """Coordinates the diagnostic agents for one telemetry frame."""

    def __init__(
        self,
        diagnostic_agent: DiagnosticAgent,
        risk_agent: RiskAssessmentAgent,
        maintenance_agent: MaintenanceAgent,
        reporting_agent: ReportingAgent,
        max_retries: int = 1,
        monitoring: MonitoringAgent | None = None,
    ) -> None:
        self._diagnostic_agent = diagnostic_agent
        self._risk_agent = risk_agent
        self._maintenance_agent = maintenance_agent
        self._reporting_agent = reporting_agent
        self._max_retries = max_retries
        self._monitoring = monitoring

    async def run(
        self,
        telemetry_record: TelemetryRecord,
        workflow_id: str | None = None,
    ) -> DiagnosticReport:
        """Execute the graph and return the completed, traceable report."""
        run_id = workflow_id or generate_id("WF")
        if self._monitoring is not None:
            self._notify(self._monitoring.record_workflow_started)
        runner = AgentRunner(
            max_retries=self._max_retries,
            observer=self._monitoring.record_execution if self._monitoring else None,
        )
        started_at = utc_now()
        perf_started = time.perf_counter()

        logger.info(
            "workflow_started",
            extra={
                "workflow_id": run_id,
                "telemetry_id": telemetry_record.telemetry_id,
                "vehicle_id": telemetry_record.telemetry.vehicle_id,
            },
        )

        graph = self._build_graph(runner)
        try:
            state: WorkflowState = await graph.ainvoke(
                {
                    "telemetry_record": telemetry_record,
                    "workflow_id": run_id,
                }
            )
        except Exception as exc:
            if self._monitoring is not None:
                self._notify(
                    self._monitoring.record_workflow_failed,
                    type(exc).__name__,
                    self._elapsed_ms(perf_started),
                )
            raise
        report = state["report"]

        # The Orchestrator and Reporting Agent executions are recorded *after*
        # their work succeeds, so attach the complete ledger to the report.
        finished_at = utc_now()
        orchestrator_execution = AgentExecution(
            agent_name=ORCHESTRATOR_AGENT_NAME,
            correlation_id=get_correlation_id(),
            workflow_id=run_id,
            status=ExecutionStatus.SUCCESS,
            attempt=1,
            started_at=started_at,
            ended_at=finished_at,
            execution_time_ms=self._elapsed_ms(perf_started),
        )
        report = report.model_copy(
            update={
                "agent_executions": [orchestrator_execution, *runner.executions]
            }
        )

        if self._monitoring is not None:
            self._notify(self._monitoring.record_execution, orchestrator_execution)
            self._notify(
                self._monitoring.record_workflow_completed,
                report,
                self._elapsed_ms(perf_started),
            )

        logger.info(
            "workflow_completed",
            extra={
                "workflow_id": run_id,
                "diagnostic_id": report.diagnostic_id,
                "risk_level": report.risk.level.value,
                "status": report.status.value,
                "analysis_mode": report.analysis_mode.value,
                "agent_count": len(report.agent_executions),
                "duration_ms": round((utc_now() - started_at).total_seconds() * 1000, 2),
            },
        )
        return report

    @staticmethod
    def _elapsed_ms(perf_started: float) -> float:
        return round((time.perf_counter() - perf_started) * 1000, 3)

    def _notify(self, callback, *args: object) -> None:  # noqa: ANN001 - internal hook
        """Call a monitoring hook without ever failing the diagnosis."""
        if self._monitoring is None:
            return
        try:
            callback(*args)
        except Exception:  # monitoring must never break the workflow
            logger.exception("monitoring_hook_failed")

    def _build_graph(self, runner: AgentRunner):  # noqa: ANN202 - builder returns compiled graph
        """Compile a fresh graph bound to this invocation's execution ledger."""

        async def diagnostic_node(state: WorkflowState) -> WorkflowState:
            record = state["telemetry_record"]
            diagnostic = await runner.run(
                agent_name=self._diagnostic_agent.name,
                workflow_id=state["workflow_id"],
                operation=lambda: self._diagnostic_agent.analyze(record.telemetry),
            )
            return {"diagnostic": diagnostic}

        async def risk_node(state: WorkflowState) -> WorkflowState:
            risk = await runner.run(
                agent_name=self._risk_agent.name,
                workflow_id=state["workflow_id"],
                operation=lambda: self._risk_agent.assess(
                    state["telemetry_record"].telemetry, state["diagnostic"]
                ),
            )
            return {"risk": risk}

        async def maintenance_node(state: WorkflowState) -> WorkflowState:
            maintenance = await runner.run(
                agent_name=self._maintenance_agent.name,
                workflow_id=state["workflow_id"],
                operation=lambda: self._maintenance_agent.recommend(
                    state["diagnostic"], state["risk"]
                ),
            )
            return {"maintenance": maintenance}

        async def reporting_node(state: WorkflowState) -> WorkflowState:
            diagnostic = state["diagnostic"]
            warnings: list[ReportWarning] = []
            if diagnostic.narrative_source == "fallback":
                warnings.append(
                    ReportWarning(
                        code=LLM_NARRATIVE_WARNING,
                        message=(
                            "The LLM narrative provider was unavailable; the summary "
                            "is a deterministic fallback. Findings and risk are unaffected."
                        ),
                    )
                )

            report = await runner.run(
                agent_name=self._reporting_agent.name,
                workflow_id=state["workflow_id"],
                operation=lambda: self._reporting_agent.build(
                    telemetry_record=state["telemetry_record"],
                    workflow_id=state["workflow_id"],
                    diagnostic=diagnostic,
                    risk=state["risk"],
                    maintenance=state["maintenance"],
                    executions=runner.executions,
                    warnings=warnings,
                ),
            )
            return {"report": report}

        graph = StateGraph(WorkflowState)
        graph.add_node("diagnostic", diagnostic_node)
        graph.add_node("risk", risk_node)
        graph.add_node("maintenance", maintenance_node)
        graph.add_node("reporting", reporting_node)

        graph.add_edge(START, "diagnostic")
        graph.add_edge("diagnostic", "risk")
        graph.add_edge("risk", "maintenance")
        graph.add_edge("maintenance", "reporting")
        graph.add_edge("reporting", END)
        return graph.compile()
