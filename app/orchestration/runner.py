"""Agent execution wrapper with bounded retries and an execution ledger.

Every agent call goes through :class:`AgentRunner`. It records one
``AgentExecution`` per attempt (successful or failed), retries transient
failures a configurable number of times and raises ``AgentExecutionError`` once
the budget is exhausted. The ledger is kept on the runner rather than in graph
state so it also contains attempts from a node that ultimately failed.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TypeVar

from app.core.correlation import get_correlation_id
from app.core.errors import AgentExecutionError
from app.core.logging import get_logger
from app.models.diagnostics import AgentExecution, ExecutionStatus
from app.utils.time import utc_now

logger = get_logger("orchestration.runner")

T = TypeVar("T")

#: Maximum number of characters of an upstream error kept in the execution
#: ledger. Full tracebacks stay in the logs.
_MAX_ERROR_MESSAGE = 500


class AgentRunner:
    """Runs one agent operation with retries and records every attempt."""

    def __init__(self, max_retries: int = 1) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self._max_retries = max_retries
        self._executions: list[AgentExecution] = []

    @property
    def executions(self) -> list[AgentExecution]:
        """Snapshot of every attempt recorded so far, in completion order."""
        return list(self._executions)

    async def run(
        self,
        *,
        agent_name: str,
        workflow_id: str,
        operation: Callable[[], Awaitable[T] | T],
    ) -> T:
        """Execute ``operation``, retrying on failure up to ``max_retries`` times."""
        correlation_id = get_correlation_id()
        attempts_allowed = self._max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts_allowed + 1):
            started_at = utc_now()
            started = time.perf_counter()
            try:
                outcome = operation()
                if inspect.isawaitable(outcome):
                    outcome = await outcome
            except Exception as exc:
                last_error = exc
                self._record(
                    agent_name=agent_name,
                    correlation_id=correlation_id,
                    workflow_id=workflow_id,
                    attempt=attempt,
                    started_at=started_at,
                    started=started,
                    status=ExecutionStatus.FAILED,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:_MAX_ERROR_MESSAGE],
                )
                logger.warning(
                    "agent_attempt_failed",
                    extra={
                        "agent": agent_name,
                        "workflow_id": workflow_id,
                        "attempt": attempt,
                        "max_attempts": attempts_allowed,
                        "error_type": type(exc).__name__,
                    },
                )
                continue

            execution = self._record(
                agent_name=agent_name,
                correlation_id=correlation_id,
                workflow_id=workflow_id,
                attempt=attempt,
                started_at=started_at,
                started=started,
                status=ExecutionStatus.SUCCESS,
            )
            logger.info(
                "agent_completed",
                extra={
                    "agent": agent_name,
                    "workflow_id": workflow_id,
                    "attempt": attempt,
                    "duration_ms": execution.execution_time_ms,
                },
            )
            return outcome

        raise AgentExecutionError(
            f"{agent_name} failed after {attempts_allowed} attempt(s).",
            details={
                "agent_name": agent_name,
                "workflow_id": workflow_id,
                "attempts": attempts_allowed,
                "error_type": type(last_error).__name__ if last_error else "UnknownError",
            },
        ) from last_error

    def _record(
        self,
        *,
        agent_name: str,
        correlation_id: str,
        workflow_id: str,
        attempt: int,
        started_at: datetime,
        started: float,
        status: ExecutionStatus,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> AgentExecution:
        ended_at = utc_now()
        execution = AgentExecution(
            agent_name=agent_name,
            correlation_id=correlation_id,
            workflow_id=workflow_id,
            status=status,
            attempt=attempt,
            started_at=started_at,
            ended_at=ended_at,
            execution_time_ms=round((time.perf_counter() - started) * 1000, 3),
            error_type=error_type,
            error_message=error_message,
        )
        self._executions.append(execution)
        return execution
