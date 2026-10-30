# Runbook — High-Risk Vehicle

| Field | Value |
| ----- | ----- |
| Runbook ID | `high_risk_vehicle` |
| Incident | `CRITICAL_VEHICLE_RISK` |
| Severity | critical |
| Owner | Fleet Operations |
| Applies to | A completed report whose deterministic risk level is `critical` |

## Trigger

The Risk Assessment Agent returned `risk.level = "critical"` (score ≥ 9 or a hard safety
override) for a telemetry frame. The incident metadata contains `risk_score`,
`hard_override`, `finding_codes` and `dtc_codes`.

## Immediate actions

1. **Acknowledge the incident.** Confirm the vehicle ID, risk score and triggering findings
   in `GET /api/v1/diagnostics/{diagnostic_id}` and `GET /api/v1/incidents`.
2. **Restrict vehicle use.** If the vehicle is in service, instruct the driver to stop
   safely and arrange recovery. Do not clear trouble codes to keep driving.
3. **Inspect the reported systems** in the order listed by the maintenance plan (cooling,
   electrical, mechanical). Verify sensor values with an independent diagnostic tool.
4. **Record the resolution** from the workshop. AutoGuard AI performs no repair and its
   report remains advisory evidence only.

## Triage queries

```powershell
Invoke-RestMethod "https://<host>/api/v1/incidents?severity=critical&status=open"
$report = Invoke-RestMethod "https://<host>/api/v1/diagnostics/<diagnostic_id>"
$report.risk
$report.maintenance.actions | Format-Table priority, title
$report.agent_executions | Format-Table agent_name, status, attempt
```

Structured logs: filter by the incident's `correlation_id`, then by `workflow_id`.

## Do not

- Do not edit the report or incident to lower the severity.
- Do not treat a later clean frame as proof of repair without a physical inspection.
- Do not ask an LLM or re-run narration to change the risk level — it is deterministic.

## Escalation

- Persistent critical readings across multiple frames: escalate to Fleet Operations and
  the Safety Reviewer.
- Suspected sensor fault: cross-check against the Diagnostic Agent's
  `SENSOR_UNAVAILABLE` findings and the maintenance plan's sensor-circuit action.

## Verification / closure

A subsequent telemetry frame must return **LOW or MEDIUM with no hard override** before
the vehicle is released. Record the confirming frame's `diagnostic_id` and workshop
findings. The demo does not implement incident status transitions; closure is recorded
outside the service.
