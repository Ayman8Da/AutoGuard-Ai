# Agent Card — Orchestrator Agent

| Field | Value |
| ----- | ----- |
| Agent ID | `orchestrator` |
| Class | `DiagnosticWorkflow` (`app/orchestration/workflow.py`) |
| Owner | Platform Engineering |
| Autonomy | **Supervised** — executes a fixed LangGraph topology |
| Determinism | Fully deterministic control flow |
| LLM use | None |
| Status | Implemented (Phase 3), observed by Monitoring (Phase 4) |

## Purpose

Coordinates one diagnostic run for a single telemetry frame. It sequences the Diagnostic,
Risk Assessment, Maintenance and Reporting agents, enforces the retry budget, owns the
execution ledger and records its own end-to-end `AgentExecution`.

## Inputs

- `TelemetryRecord` — a validated frame already persisted by the Telemetry Service.
- Optional `workflow_id` (tests/replays); otherwise generated.
- Current correlation ID from the request `ContextVar`.

## Outputs

- One `DiagnosticReport` with a `workflow_id`, five `AgentExecution` entries
  (Orchestrator + four downstream agents) and a correlation ID.
- Structured logs: `workflow_started`, `agent_completed`, `agent_attempt_failed`,
  `workflow_completed`, `workflow_failed`.

## Graph

```text
START → diagnostic → risk → maintenance → reporting → END
```

The graph is compiled per invocation, so no state or execution ledger can leak between
requests.

## Failure handling

| Condition | Behaviour |
| --------- | --------- |
| Transient agent exception | Retried up to `AUTOGUARD_AGENT_MAX_RETRIES` (default 1) |
| Retry budget exhausted | Raises `AgentExecutionError` (`AGENT_EXECUTION_FAILED`, HTTP 500) |
| LLM narrative outage | Not an orchestrator failure; report degrades deterministically |
| Monitoring observer raises | Logged and swallowed; the workflow continues |

No report is fabricated after a failed node. Telemetry is already stored, so the failed
frame remains auditable.

## Observability

- Emits one `AgentExecution` for itself covering the whole run.
- Notifies the Monitoring Agent on workflow start, completion and failure.
- Correlation ID and workflow ID appear on every child execution and incident.

## Safety constraints

- Must not skip the Risk Assessment or Maintenance agent.
- Must not convert an agent failure into a success report.
- Must not call an LLM directly.

## Verification

- `tests/integration/test_workflow.py`
- `tests/api/test_observability_api.py`
- `tests/unit/test_runner.py`

## Change control

Any topology, retry or failure-handling change requires review by Platform Engineering and
the Safety Reviewer (see [GOVERNANCE.md](../docs/GOVERNANCE.md)).
