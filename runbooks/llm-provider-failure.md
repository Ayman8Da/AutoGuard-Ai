# Runbook — LLM Narrative Provider Failure

| Field | Value |
| ----- | ----- |
| Runbook ID | `llm_provider_failure` |
| Incident | `LLM_PROVIDER_FAILURE` |
| Severity | medium |
| Owner | Platform Engineering |
| Applies to | A report containing the `LLM_NARRATIVE_UNAVAILABLE` warning |

## Trigger

The Diagnostic Agent could not obtain a valid narrative after the configured attempts. The
report is still returned (`200`) with `status = "completed_degraded"` and
`analysis_mode = "degraded_deterministic"`. Findings, deterministic risk and the
maintenance plan are unaffected.

## Immediate actions

1. **Confirm the degradation scope.** Check `analysis_mode`, `warnings[]` and
   `diagnostic.llm_error`. No safety decision depends on the narrative.
2. **Check provider health.** Verify API key validity, quota, model name and provider
   status. For Ollama, confirm the endpoint and model are reachable from the service.
3. **Decide whether to switch provider.** Keep the deterministic fallback, switch to a
   configured Ollama instance, or rotate the Groq key. Never put secrets in logs or
   tickets.
4. **Re-run narration** with a fresh frame and confirm `analysis_mode` returns to
   `llm_assisted`. Do not edit historical reports.

## Triage queries

```powershell
Invoke-RestMethod "https://<host>/api/v1/incidents?severity=medium&status=open"
$report = Invoke-RestMethod "https://<host>/api/v1/diagnostics/<diagnostic_id>"
$report.status
$report.analysis_mode
$report.warnings
$report.diagnostic.llm_error
$report.diagnostic.llm_attempts
(Invoke-RestMethod "https://<host>/api/v1/monitoring").workflows_degraded
```

Log filter: `llm_narrative_failed`, `agent_attempt_failed` with `agent = DiagnosticAgent`.

## Do not

- Do not change risk or maintenance output because narration failed.
- Do not log or paste the API key while debugging.
- Do not treat the incident as a safety incident; the deterministic path is intact.

## Escalation

- Provider outage beyond 30 minutes: Platform Engineering decides whether to keep the
  fallback or switch providers.
- Invalid JSON from a new model version: pin the previous model and open a prompt/schema
  change request.

## Verification / closure

A new report shows `analysis_mode = "llm_assisted"`, no `LLM_NARRATIVE_UNAVAILABLE`
warning, and a provider response within `AUTOGUARD_LLM_TIMEOUT_SECONDS`. The degraded
incident remains as historical evidence (the demo has no status transitions).
