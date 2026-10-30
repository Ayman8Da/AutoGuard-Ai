# Agent Card — Maintenance Agent

| Field | Value |
| ----- | ----- |
| Agent ID | `maintenance` |
| Class | `MaintenanceAgent` (`app/agents/maintenance.py`) |
| Owner | Fleet Maintenance |
| Autonomy | **Advisory only** |
| Determinism | **Fully deterministic** |
| LLM use | None |
| Status | Implemented (Phase 3) |

## Purpose

Turns findings, DTC interpretations and the risk level into a prioritised list of
inspection and maintenance actions with a rationale for each one.

## Inputs

- `DiagnosticResult`
- `RiskAssessment`

## Outputs

`MaintenancePlan`:

- `priority` — `immediate` / `urgent` / `scheduled` / `routine`.
- `actions[]` — title, description, category, priority, rationale, related findings.
- `notes` — explicit statement that no inspection or repair has been performed.
- `repair_performed` — always `false`.

## Behaviour

| Situation | Plan |
| --------- | ---- |
| Clean frame | Single routine-monitoring action |
| Critical risk | Immediate targeted actions (cooling, electrical, mechanical, DTCs) |
| High risk | Urgent inspection actions |
| Unavailable sensors | Sensor-circuit and ECM/PCM communication checks |
| Duplicate findings/DTCs | Actions merged, related findings combined |
| Unknown DTC | Explicit full diagnostic scan request |

Action order follows severity so an operator has a deterministic starting point.

## Failure handling

Pure and synchronous. Exceptions are retried by the Orchestrator and then surfaced as
`AGENT_EXECUTION_FAILED`. No partial plan is returned.

## Safety constraints

- Never claim a repair was performed.
- Never downgrade the plan priority below the risk level implies.
- Never omit the "no repair performed" note.
- Advice is advisory; a qualified technician makes the final decision.

## Verification

- `tests/unit/test_agents.py`
- `tests/integration/test_workflow.py`
- `tests/api/test_diagnostics_api.py`
