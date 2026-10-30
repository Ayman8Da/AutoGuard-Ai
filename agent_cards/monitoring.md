# Agent Card — Monitoring Agent

| Field | Value |
| ----- | ----- |
| Agent ID | `monitoring` |
| Class | `MonitoringAgent` (`app/monitoring/agent.py`) |
| Owner | Platform Engineering / SRE |
| Autonomy | **Passive observer** |
| Determinism | Fully deterministic aggregation |
| LLM use | None |
| Status | Implemented (Phase 4) |

## Purpose

Observes every agent attempt and workflow outcome, keeps a bounded execution ledger and
exposes aggregated statistics through `GET /api/v1/monitoring`. It is not part of the
vehicle diagnosis chain and cannot alter findings, risk or maintenance advice.

## Inputs

- Every `AgentExecution` emitted by `AgentRunner` (successful and failed attempts).
- Workflow start, completion (normal or degraded) and failure events.
- Point-in-time counts supplied by the API: uptime, stored diagnostics, incidents.

## Outputs

`MonitoringSnapshot`:

- Workflow counters: started, completed, degraded, failed, success rate, average duration.
- Agent counters: total executions, failures, retries, success rate.
- Per-agent statistics: executions, successes, failures, retries, success rate, average
  duration, last execution time.
- Process context: uptime, LLM provider, diagnostics stored, incidents total/active.

## Bounded state

The execution ledger is a bounded FIFO (default 5 000 entries,
`AUTOGUARD_MONITORING_BUFFER_SIZE`). Evicting old observations only reduces the reporting
window; it never affects diagnostics. Counters are process-local and reset on restart.

## Failure handling

Recording is defensive: an observer exception is caught inside `AgentRunner` and logged as
`agent_execution_observer_failed`. A monitoring bug therefore cannot fail a diagnosis.
The Monitoring Agent itself never raises into the workflow.

## Safety constraints

- Read-only with respect to diagnostic artifacts.
- Must not block, retry or reorder agent execution.
- Must not log telemetry payloads or secrets.
- Statistics are operational signals, not safety decisions.

## Verification

- `tests/unit/test_monitoring.py`
- `tests/api/test_observability_api.py`
- `tests/integration/test_workflow.py`
