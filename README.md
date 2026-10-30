# AutoGuard AI

**Agentic Predictive Maintenance & Intelligent Vehicle Fault Diagnosis**

AutoGuard AI ingests simulated vehicle telemetry, detects abnormal conditions, runs a
supervised multi-agent diagnostic workflow, classifies risk with deterministic rules,
recommends maintenance actions, produces traceable diagnostic reports and raises
operational incidents with runbooks — all linked by one correlation ID.

> **Data disclaimer:** all telemetry is synthetic. AutoGuard AI is an engineering
> demonstration of agentic AI, observability and CI/CD — it is **not** a validated
> real-world automotive diagnostic or safety system.

---

## Project status

| Phase | Scope | Status |
| ----- | ----- | ------ |
| 1 | Foundation: config, structured logging, correlation IDs, error contract, health API | **Complete — verified** |
| 2 | Vehicle simulator, telemetry validation, in-memory repository, fleet/telemetry API | **Complete — verified** |
| 3 | Multi-agent architecture (LangGraph) + LLM provider abstraction | **Complete — verified** |
| 4 | Monitoring, incidents, runbooks | **Complete — verified** |
| 5 | Agent Cards & governance documentation | **Complete** |
| 6 | Full automated test suite (≥80% core coverage) | Pending |
| 7 | GitHub Actions CI | Pending |
| 8 | Docker & local container validation | Pending |
| 9 | Render deployment | Pending |
| 10 | Documentation & final demonstration | Pending |

Phase 1–4 verification (actual, local): **258 tests passing, 97% branch coverage
(app + simulator), `ruff` clean**.

---

## Quickstart (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env          # mock LLM by default: no API key needed
uvicorn app.main:app --reload --port 8000
```

| URL | Purpose |
| --- | ------- |
| http://localhost:8000/health | Health probe |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/openapi.json | OpenAPI schema |

```powershell
# Smoke test
Invoke-RestMethod http://localhost:8000/health
```

No external API key is required. `AUTOGUARD_LLM_PROVIDER=mock` is the default so the
application, agents and test suite run fully offline.

---

## Vehicle simulator

The `simulator` package produces the synthetic telemetry the API consumes.

```powershell
# One frame with seeded jitter
python -m simulator.vehicle_simulator --scenario warning --vehicle VH-002 --seed 42 --pretty

# All four scenarios, exact fixture values
python -m simulator.vehicle_simulator --all --no-jitter --pretty
```

| Scenario | Status | Temperature | Battery | Vibration | Trouble codes |
| -------- | ------ | ----------- | ------- | --------- | ------------- |
| `normal` | driving | 89.5 °C | 13.9 V | 2.2 mm/s | — |
| `warning` | driving | 104.2 °C | 12.6 V | 5.8 mm/s | P0128 |
| `critical` | driving | 121.8 °C | 11.2 V | 9.4 mm/s | P0217, P0301 |
| `sensor_failure` | fault | `null` | 13.1 V | `null` | U0100 |

Feed a generated frame into the API:

```powershell
python -m simulator.vehicle_simulator --scenario critical --vehicle VH-003 --pretty > payload.json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/vehicles/telemetry `
  -ContentType "application/json" -InFile payload.json
```

Fixtures are exact and reproducible; `--seed` makes the optional jitter reproducible too.
Values are plausible for a demo but are **not** validated automotive measurements.

---

## API

### Implemented

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/` | Service metadata (not shown in Swagger) |
| `GET` | `/health` | Health probe with uptime, version, configuration checks |
| `POST` | `/api/v1/vehicles/telemetry` | Validate + store telemetry, run the agent workflow, return the report (200) |
| `GET` | `/api/v1/vehicles` | List the simulated fleet with latest state |
| `GET` | `/api/v1/vehicles/{vehicle_id}` | One vehicle + its latest telemetry record |
| `GET` | `/api/v1/diagnostics` | Recent diagnostic report summaries, newest first (`?limit=1..200`) |
| `GET` | `/api/v1/diagnostics/{diagnostic_id}` | Full report: findings, risk, maintenance plan, agent ledger |
| `GET` | `/api/v1/monitoring` | Workflow/agent counters, per-agent statistics, incident totals |
| `GET` | `/api/v1/incidents` | Operational incidents (`?limit`, `?status`, `?severity`, `?vehicle_id`) |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/openapi.json` | OpenAPI 3 schema |

### Monitoring and incidents

`GET /api/v1/monitoring` aggregates every recorded agent attempt and workflow outcome for
the current process:

```json
{
  "llm_provider": "mock",
  "workflows_started": 4,
  "workflows_completed": 2,
  "workflows_degraded": 1,
  "workflows_failed": 1,
  "workflow_success_rate_percent": 75.0,
  "agent_executions_total": 19,
  "agent_failures_total": 2,
  "agents": [{ "agent_name": "DiagnosticAgent", "executions": 4, "successes": 3 }],
  "diagnostics_stored": 3,
  "incidents_total": 3,
  "incidents_active": 3
}
```

`GET /api/v1/incidents` returns the incidents implied by workflow outcomes, newest first:

| Incident code | Trigger | Severity | Runbook |
| ------------- | ------- | -------- | ------- |
| `CRITICAL_VEHICLE_RISK` | Deterministic risk level `critical` | critical | `high_risk_vehicle` |
| `LLM_PROVIDER_FAILURE` | `LLM_NARRATIVE_UNAVAILABLE` warning (degraded report) | medium | `llm_provider_failure` |
| `AGENT_EXECUTION_FAILED` | Agent exhausted its retry budget | high | `agent_failure` |

Each incident carries the correlation ID, vehicle, diagnostic/workflow IDs, the owner
and the ordered runbook steps. Invalid telemetry stays a `422` boundary error: it never
reaches the workflow and never creates an incident.

A single ingestion call returns the complete diagnosis:

```json
{
  "diagnostic_id": "DIAG-20261030-8A1F...",
  "workflow_id": "WF-20261030-4C2B...",
  "telemetry_id": "TEL-20261030-9F1C...",
  "correlation_id": "CORR-20261030-9F1C...",
  "vehicle_id": "VH-003",
  "status": "completed",
  "analysis_mode": "deterministic",
  "risk": { "level": "critical", "score": 26, "hard_override": true, "reasons": [] },
  "maintenance": { "priority": "immediate", "actions": [], "repair_performed": false },
  "agent_executions": [
    { "agent_name": "OrchestratorAgent", "status": "success", "attempt": 1 },
    { "agent_name": "DiagnosticAgent", "status": "success", "attempt": 1 }
  ],
  "warnings": [],
  "disclaimer": "Simulated telemetry only. ..."
}
```

(Abridged — the real payload includes full findings, DTC interpretations and per-agent
timings.) `risk.level` is always computed by deterministic rules; the LLM may only
rephrase the summary.

Every response carries an `X-Correlation-ID` header. Errors use one envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request payload validation failed.",
    "details": [{ "loc": ["body", "vehicle_id"], "msg": "Field required", "type": "missing" }],
    "correlation_id": "CORR-20261030-9F1C2A7B44DE"
  }
}
```

---

## Configuration

All variables use the `AUTOGUARD_` prefix and can be set in `.env`.

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `AUTOGUARD_ENVIRONMENT` | `local` | `local`/`test`/`development`/`staging`/`production` |
| `AUTOGUARD_DEBUG` | `false` | Debug mode (keeps tracebacks; do not use in production) |
| `AUTOGUARD_LOG_LEVEL` | `INFO` | Standard Python log levels |
| `AUTOGUARD_LOG_FORMAT` | `json` | `json` or `console` |
| `AUTOGUARD_CORS_ORIGINS` | *(empty)* | Comma-separated allowed origins |
| `AUTOGUARD_TELEMETRY_BUFFER_SIZE` | `1000` | Telemetry records kept in memory per process |
| `AUTOGUARD_DIAGNOSTICS_BUFFER_SIZE` | `500` | Diagnostic reports kept in memory per process |
| `AUTOGUARD_INCIDENT_BUFFER_SIZE` | `500` | Incidents kept in memory per process |
| `AUTOGUARD_MONITORING_BUFFER_SIZE` | `5000` | Agent execution observations kept in memory |
| `AUTOGUARD_LLM_PROVIDER` | `mock` | `mock`, `groq` or `ollama` |
| `AUTOGUARD_LLM_MODEL` | `llama-3.3-70b-versatile` | Model name for the active provider |
| `AUTOGUARD_GROQ_API_KEY` | *(empty)* | Required only for `groq`; stored as `SecretStr` |
| `AUTOGUARD_OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `AUTOGUARD_AGENT_MAX_RETRIES` | `1` | Safe retry budget per agent |

Startup fails fast if `AUTOGUARD_LLM_PROVIDER=groq` is set without an API key. Secrets are
never logged or returned by the API.

**Storage:** telemetry, diagnostic reports, incidents and monitoring observations live in
bounded in-process stores. Restarting the service clears them. The repository contracts
allow a MongoDB Atlas implementation later without touching the API or agents.

---

## Testing & quality

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest --cov=app --cov=simulator --cov-report=term-missing
```

---

## Project layout (Phase 3)

```text
AutoGuard-AI/
├── app/
│   ├── main.py                 # App factory, lifespan, middleware/service wiring
│   ├── api/
│   │   ├── system.py           # / and /health
│   │   ├── deps.py             # Dependency providers
│   │   ├── exception_handlers.py
│   │   └── v1/
│   │       ├── router.py
│   │       └── endpoints/
│   │           ├── vehicles.py         # Telemetry ingestion + fleet routes
│   │           ├── diagnostics.py      # Report list/detail routes
│   │           ├── monitoring.py       # Aggregated monitoring snapshot
│   │           └── incidents.py        # Incident list/filter route
│   ├── core/
│   │   ├── config.py           # Pydantic settings (typed, validated)
│   │   ├── correlation.py      # Correlation ID generation/sanitisation
│   │   ├── errors.py           # Domain error hierarchy
│   │   ├── logging.py          # JSON logging + context filter
│   │   └── middleware.py       # Request tracing
│   ├── models/
│   │   ├── common.py           # Error/health schemas
│   │   ├── diagnostics.py      # Findings, risk, maintenance, report models
│   │   ├── enums.py            # Vehicle status, fuel type
│   │   ├── telemetry.py        # Strict telemetry contracts
│   │   └── vehicle.py          # Fleet read models
│   ├── agents/
│   │   ├── diagnostic.py       # Findings + DTC interpretation + narrative
│   │   ├── llm.py              # Mock/Groq/Ollama clients, strict JSON parsing
│   │   ├── maintenance.py      # Prioritised advisory actions
│   │   ├── reporting.py        # Report assembly, disclaimer, status
│   │   ├── risk.py             # Deterministic risk classification
│   │   └── rules.py            # Sensor bands, DTC catalogue, risk bands
│   ├── orchestration/
│   │   ├── runner.py           # Retries + AgentExecution ledger
│   │   ├── state.py            # Graph state
│   │   └── workflow.py         # LangGraph graph + Orchestrator ledger entry
│   ├── services/
│   │   ├── diagnostics_repository.py
│   │   ├── diagnostics_service.py
│   │   ├── fleet.py            # 5 simulated vehicles
│   │   ├── repositories.py     # TelemetryRepository + in-memory store
│   │   └── telemetry_service.py
│   ├── monitoring/
│   │   ├── agent.py            # Monitoring Agent: execution ledger + statistics
│   │   └── metrics.py          # MonitoringSnapshot / AgentStatistics contracts
│   ├── incidents/
│   │   ├── manager.py          # Incident creation, filtering, bounded store
│   │   ├── models.py           # Incident + Runbook contracts
│   │   └── runbooks.py         # Three operational runbooks
│   └── utils/
├── simulator/
│   ├── scenarios.py            # Four deterministic scenarios
│   └── vehicle_simulator.py    # Seeded jitter + CLI
├── tests/
│   ├── api/
│   ├── integration/
│   └── unit/
├── agent_cards/                # One card per agent (purpose, I/O, safety, ownership)
├── docs/
│   ├── ARCHITECTURE.md
│   └── GOVERNANCE.md           # Change control, prompt/data/incident policy
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── .env.example
└── README.md
```

Planned additions: `runbooks/` markdown copies, `tests/failure/`,
`.github/workflows/`, `Dockerfile`, `docker-compose.yml`, `DEPLOYMENT.md`.

---

## Engineering decisions (Phases 1–4)

- **Modular monolith, not microservices.** One FastAPI process keeps the multi-agent
  workflow debuggable while preserving clean package boundaries.
- **Correlation IDs live in a `ContextVar`.** This propagates automatically through async
  agent calls without threading an extra argument through every function.
- **Client-supplied correlation IDs are allow-listed.** Prevents log injection while
  still supporting distributed tracing from a frontend or gateway.
- **One error envelope.** Validation errors, 404s, domain errors and unexpected
  exceptions all return the same shape plus the correlation ID.
- **Structured JSON logs by default.** Log line fields (`correlation_id`, `agent`,
  `duration_ms`, `status`) map directly to the monitoring model.
- **LLM provider is pluggable and `mock`-first.** The full stack is testable without an
  API key; Groq is opt-in via environment configuration.
- **Configuration is validated at startup.** Invalid log levels, API prefixes or a
  missing Groq key fail fast rather than at the first request.
- **`null` means "sensor unavailable", not "field missing".** A sensor-failure payload is
  accepted and stored so the Diagnostic Agent can identify it; only structurally invalid
  or physically impossible values are rejected with 422.
- **Telemetry ingestion is fleet-scoped.** Unknown vehicles return `404
  VEHICLE_NOT_FOUND` instead of silently polluting the store.
- **Bounded in-memory repository.** Prevents unbounded growth during demos and keeps the
  storage contract swappable.
- **Risk is deterministic, never LLM-assigned.** Sensor bands, DTC weights and hard
  safety overrides live in `app/agents/rules.py`; identical telemetry always produces the
  same score and level. An LLM failure cannot change the classification.
- **The LLM only writes prose.** It receives already-computed findings, must answer with
  `{"summary": "..."}`, and cannot claim a repair happened. Invalid JSON or provider
  outages degrade to a deterministic summary and a `LLM_NARRATIVE_UNAVAILABLE` warning.
- **Agents retry within a bounded budget.** `AgentRunner` records every attempt and raises
  `AGENT_EXECUTION_FAILED` only after exhausting the budget, so partial failures are never
  silently reported as success.
- **The Orchestrator is observed, not magical.** The workflow records its own execution
  alongside the four diagnostic agents, making end-to-end timing visible in the report.
- **Monitoring is passive and cannot fail a diagnosis.** The Monitoring Agent is fed every
  `AgentExecution` through an observer; observer exceptions are logged and swallowed.
  Telemetry is stored before the workflow so a failure still leaves an audit trail.
- **Incidents are derived, not invented.** Only three deterministic outcomes create
  incidents (critical risk, degraded narration, exhausted agent retries). Each one is
  linked to a runbook and to the correlation/workflow/diagnostic IDs.
- **Invalid telemetry is a boundary error, not an incident.** A `422` never enters the
  workflow, so operators are not paged for malformed client input.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full target architecture.
