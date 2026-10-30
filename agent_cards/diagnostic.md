# Agent Card — Diagnostic Agent

| Field | Value |
| ----- | ----- |
| Agent ID | `diagnostic` |
| Class | `DiagnosticAgent` (`app/agents/diagnostic.py`) |
| Owner | Vehicle Diagnostics |
| Autonomy | **Supervised** — findings come from fixed rules |
| Determinism | Hybrid: rules deterministic, narrative optional |
| LLM use | **Narrative only** |
| Status | Implemented (Phase 3) |

## Purpose

Detects abnormal sensor readings, interprets diagnostic trouble codes (DTCs), lists
unavailable sensors and produces suspected faults plus a short natural-language summary.

## Inputs

`VehicleTelemetry` (validated): three sensors that may be `null` when unavailable, the
vehicle status and up to 20 DTCs.

## Outputs

`DiagnosticResult`:

- `findings[]` — stable code, sensor, severity, value, unit, threshold.
- `dtc_interpretations[]` — description, system, severity, `known` flag.
- `unavailable_sensors[]` — sensors reported as `null`.
- `suspected_faults[]` — derived from findings and known DTCs.
- `summary` — LLM phrasing when available, deterministic fallback otherwise.
- `narrative_source` (`mock`/`llm`/`fallback`), `llm_attempts`, `llm_error`.

## Rules

Sensor bands live in `app/agents/rules.py` and are versioned with the risk thresholds.
Examples:

| Condition | Finding | Score |
| --------- | ------- | ----- |
| Engine temperature > 118 °C | `ENGINE_TEMPERATURE_CRITICAL` | 6 |
| Battery voltage < 11.8 V | `BATTERY_VOLTAGE_CRITICAL` | 5 |
| Vibration > 8.0 mm/s | `ENGINE_VIBRATION_CRITICAL` | 5 |
| Unavailable sensor | `SENSOR_UNAVAILABLE` | 0 |

DTCs outside the local catalogue are marked `known=false` and scored 1 (verify), never
silently ignored.

## LLM contract

The provider receives only already-computed findings and must return strict JSON:

```json
{ "summary": "One or two sentences of prose." }
```

Extra keys, empty summaries and non-JSON output are rejected. The LLM cannot add findings,
change severities, assign risk or claim a repair. On failure the agent retries
`AUTOGUARD_AGENT_MAX_RETRIES + 1` times, then uses a deterministic summary and records
`LLM_NARRATIVE_UNAVAILABLE` in the report.

## Failure handling

| Condition | Behaviour |
| --------- | --------- |
| Invalid LLM JSON / provider outage | Deterministic fallback; workflow continues |
| Missing sensor (`null`) | Finding + suspect cause; not a validation error |
| Rule engine raises | Agent failure → retries → `AGENT_EXECUTION_FAILED` |

## Safety constraints

- Never invent sensor readings or DTCs.
- Never raise or lower deterministic severity through prose.
- Never state that a repair was performed.

## Verification

- `tests/unit/test_agents.py`
- `tests/unit/test_rules.py`
- `tests/unit/test_llm.py`
- `tests/integration/test_workflow.py`
