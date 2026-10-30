"""Monitoring Agent.

The Monitoring Agent observes the workflow rather than diagnosing vehicles: it
collects every ``AgentExecution`` attempt, tracks workflow outcomes and exposes
aggregated statistics. Recording is defensive by design — an observability bug
must never fail a diagnosis.
"""

from __future__ import annotations

from collections import deque
from threading import Lock

from app.core.logging import get_logger
from app.models.diagnostics import AgentExecution, DiagnosticReport, ExecutionStatus, ReportStatus
from app.monitoring.metrics import AgentStatistics, MonitoringSnapshot
from app.utils.time import utc_now

logger = get_logger("monitoring.agent")


class MonitoringAgent:
    """In-memory execution ledger and statistics aggregator."""

    name = "MonitoringAgent"

    def __init__(self, max_executions: int = 5000) -> None:
        if max_executions < 1:
            raise ValueError("max_executions must be >= 1")
        self._max_executions = max_executions
        self._executions: deque[AgentExecution] = deque()
        self._workflows_started = 0
        self._workflows_completed = 0
        self._workflows_degraded = 0
        self._workflows_failed = 0
        self._workflow_duration_total_ms = 0.0
        self._lock = Lock()

    # ------------------------------------------------------------------ #
    # Recording
    # ------------------------------------------------------------------ #

    def record_workflow_started(self) -> None:
        with self._lock:
            self._workflows_started += 1

    def record_execution(self, execution: AgentExecution) -> None:
        """Store one attempt. Never raises into the diagnostic workflow."""
        try:
            with self._lock:
                while len(self._executions) >= self._max_executions:
                    self._executions.popleft()
                self._executions.append(execution)
        except Exception:  # pragma: no cover - defensive, should never happen
            logger.exception("monitoring_execution_record_failed")

    def record_workflow_completed(self, report: DiagnosticReport, duration_ms: float) -> None:
        with self._lock:
            self._workflow_duration_total_ms += max(duration_ms, 0.0)
            if report.status is ReportStatus.COMPLETED_DEGRADED:
                self._workflows_degraded += 1
            else:
                self._workflows_completed += 1

    def record_workflow_failed(self, error_type: str, duration_ms: float) -> None:
        with self._lock:
            self._workflows_failed += 1
            self._workflow_duration_total_ms += max(duration_ms, 0.0)
        logger.warning(
            "workflow_failed",
            extra={"error_type": error_type, "duration_ms": round(duration_ms, 2)},
        )

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def snapshot(
        self,
        *,
        uptime_seconds: float,
        diagnostics_stored: int,
        incidents_total: int,
        incidents_active: int,
        llm_provider: str,
    ) -> MonitoringSnapshot:
        """Build an immutable snapshot of the current process state."""
        with self._lock:
            executions = list(self._executions)
            started = self._workflows_started
            completed = self._workflows_completed
            degraded = self._workflows_degraded
            failed = self._workflows_failed
            duration_total = self._workflow_duration_total_ms

        finished = completed + degraded + failed
        agent_stats = self._aggregate_agents(executions)

        total_executions = sum(item.executions for item in agent_stats)
        total_failures = sum(item.failures for item in agent_stats)
        total_retries = sum(item.retries for item in agent_stats)
        successes = total_executions - total_failures

        return MonitoringSnapshot(
            generated_at=utc_now(),
            uptime_seconds=round(max(uptime_seconds, 0.0), 3),
            llm_provider=llm_provider,
            workflows_started=started,
            workflows_completed=completed,
            workflows_degraded=degraded,
            workflows_failed=failed,
            workflow_success_rate_percent=self._percentage(completed + degraded, finished),
            avg_workflow_duration_ms=round(duration_total / finished, 3) if finished else 0.0,
            agent_executions_total=total_executions,
            agent_failures_total=total_failures,
            agent_retries_total=total_retries,
            agent_success_rate_percent=self._percentage(successes, total_executions),
            agents=agent_stats,
            diagnostics_stored=diagnostics_stored,
            incidents_total=incidents_total,
            incidents_active=incidents_active,
        )

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        if denominator == 0:
            return 0.0
        return round(numerator / denominator * 100, 2)

    @staticmethod
    def _aggregate_agents(executions: list[AgentExecution]) -> list[AgentStatistics]:
        grouped: dict[str, list[AgentExecution]] = {}
        for execution in executions:
            grouped.setdefault(execution.agent_name, []).append(execution)

        statistics: list[AgentStatistics] = []
        for agent_name in sorted(grouped):
            items = grouped[agent_name]
            successes = sum(1 for item in items if item.status is ExecutionStatus.SUCCESS)
            failures = len(items) - successes
            retries = sum(1 for item in items if item.attempt > 1)
            duration_total = sum(item.execution_time_ms for item in items)
            statistics.append(
                AgentStatistics(
                    agent_name=agent_name,
                    executions=len(items),
                    successes=successes,
                    failures=failures,
                    retries=retries,
                    success_rate_percent=MonitoringAgent._percentage(successes, len(items)),
                    avg_duration_ms=round(duration_total / len(items), 3),
                    last_execution_at=max(item.ended_at for item in items),
                )
            )
        return statistics
