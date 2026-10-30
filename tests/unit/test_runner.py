"""Unit tests for the agent retry/execution ledger."""

from __future__ import annotations

import pytest
from app.core.errors import AgentExecutionError
from app.models.diagnostics import ExecutionStatus
from app.orchestration.runner import AgentRunner


@pytest.mark.asyncio
async def test_successful_operation_records_one_execution() -> None:
    runner = AgentRunner(max_retries=2)

    result = await runner.run(
        agent_name="TestAgent",
        workflow_id="WF-20261030-TEST",
        operation=lambda: "ok",
    )

    assert result == "ok"
    assert len(runner.executions) == 1
    execution = runner.executions[0]
    assert execution.agent_name == "TestAgent"
    assert execution.workflow_id == "WF-20261030-TEST"
    assert execution.status is ExecutionStatus.SUCCESS
    assert execution.attempt == 1
    assert execution.execution_time_ms >= 0
    assert execution.ended_at >= execution.started_at


@pytest.mark.asyncio
async def test_transient_failure_is_retried_and_succeeds() -> None:
    runner = AgentRunner(max_retries=2)
    calls = {"count": 0}

    def operation() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("temporary glitch")
        return "recovered"

    result = await runner.run(
        agent_name="FlakyAgent", workflow_id="WF-1", operation=operation
    )

    assert result == "recovered"
    assert [item.attempt for item in runner.executions] == [1, 2, 3]
    assert [item.status for item in runner.executions] == [
        ExecutionStatus.FAILED,
        ExecutionStatus.FAILED,
        ExecutionStatus.SUCCESS,
    ]
    assert runner.executions[0].error_type == "RuntimeError"
    assert runner.executions[-1].error_type is None


@pytest.mark.asyncio
async def test_exhausted_retries_raise_agent_execution_error() -> None:
    runner = AgentRunner(max_retries=1)

    async def always_fails() -> None:
        raise ValueError("broken agent")

    with pytest.raises(AgentExecutionError) as excinfo:
        await runner.run(
            agent_name="BrokenAgent", workflow_id="WF-2", operation=always_fails
        )

    error = excinfo.value
    assert error.status_code == 500
    assert error.code == "AGENT_EXECUTION_FAILED"
    assert error.details == {
        "agent_name": "BrokenAgent",
        "workflow_id": "WF-2",
        "attempts": 2,
        "error_type": "ValueError",
    }
    assert len(runner.executions) == 2
    assert all(item.status is ExecutionStatus.FAILED for item in runner.executions)


def test_negative_retry_budget_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        AgentRunner(max_retries=-1)


def test_executions_property_returns_a_copy() -> None:
    runner = AgentRunner()
    snapshot = runner.executions
    snapshot.append(object())  # type: ignore[arg-type]

    assert runner.executions == []
