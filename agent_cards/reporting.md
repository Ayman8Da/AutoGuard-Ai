# Agent Card — Reporting Agent

| Field | Value |
| ----- | ----- |
| Agent ID | `reporting` |
| Class | `ReportingAgent` (`app/agents/reporting.py`) |
| Owner | Compliance & Documentation |
| Autonomy | **Assembly only** |
| Determinism | Deterministic derivation |
| LLM use | None |
| Status | Implemented (Phase 3) |

## Purpose

Assembles every agent output into one traceable, versioned `DiagnosticReport`. It
derives the status and analysis mode, attaches the disclaimer and is responsible for the
report's metadata.

## Inputs

- `TelemetryRecord` (for IDs and the full telemetry snapshot)
- `workflow_id`
- `DiagnosticResult`, `RiskAssessment`, `MaintenancePlan`
- `executions[]` — the ledger collected so far (Orchestrator + downstream)
- `warnings[]` — explicit degradations (e.g. `LLM_NARRATIVE_UNAVAILABLE`)

## Outputs

`DiagnosticReport` with:

- Stable IDs: `diagnostic_id`, `workflow_id`, `telemetry_id`, `correlation_id`
- `status` (`completed` or `completed_degraded`)
- `analysis_mode` (`deterministic` / `llm_assisted` / `degraded_deterministic`)
- Full copies of telemetry, diagnostic, risk and maintenance
- `agent_executions[]`
- `warnings[]`
- `disclaimer` — always includes the simulation/data disclaimer

## Derivation rules

| Narrative source | Analysis mode | Status |
| ----------------- | ------------- | ------ |
| `mock` / no LLM used | `deterministic` | `completed` (unless warnings) |
| `llm` | `llm_assisted` | `completed` (unless warnings) |
| `fallback` | `degraded_deterministic` | `completed_degraded` if `LLM_NARRATIVE_UNAVAILABLE` present |

The Orchestrator adds the Orchestrator's own execution after this call returns so the
report contains the complete ledger.

## Failure handling

Pure assembly. Exceptions are retried by the Orchestrator and then surfaced as
`AGENT_EXECUTION_FAILED`. If an exception occurs before the report is built, no
partial report is returned.

## Safety constraints

- Never fabricate agent executions or timestamps.
- Never remove warnings.
- Always include the disclaimer.
- The report is read-only evidence; no fields imply a repair was performed.

## Verification

- `tests/unit/test_agents.py`
- `tests/integration/test_workflow.py`
- `tests/api/test_diagnostics_api.py`
