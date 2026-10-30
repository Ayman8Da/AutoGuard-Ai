# AutoGuard AI

**Agentic Predictive Maintenance & Intelligent Vehicle Fault Diagnosis**

AutoGuard AI ingests simulated vehicle telemetry, detects abnormal conditions, runs a
supervised multi-agent diagnostic workflow, classifies risk with deterministic rules,
recommends maintenance actions and produces traceable diagnostic reports.

> **Data disclaimer:** all telemetry is synthetic. AutoGuard AI is an engineering
> demonstration of agentic AI, observability and CI/CD — it is **not** a validated
> real-world automotive diagnostic or safety system.

---

## Project status

| Phase | Scope | Status |
| ----- | ----- | ------ |
| 1 | Foundation: config, structured logging, correlation IDs, error contract, health API | **Complete — verified** |
| 2 | Vehicle simulator, telemetry validation, in-memory repository, fleet/telemetry API | **Complete — verified** |
| 3 | Multi-agent architecture (LangGraph) + LLM provider abstraction | Pending approval |
| 4 | Monitoring, incidents, runbooks | Pending |
| 5 | Agent Cards & governance documentation | Pending |
| 6 | Full automated test suite (≥80% core coverage) | Pending |
| 7 | GitHub Actions CI | Pending |
| 8 | Docker & local container validation | Pending |
| 9 | Render deployment | Pending |
| 10 | Documentation & final demonstration | Pending |

Phase 1–2 verification (actual, local): **124 tests passing, 96% branch coverage
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
| `POST` | `/api/v1/vehicles/telemetry` | Validate + store a telemetry frame (201) |
| `GET` | `/api/v1/vehicles` | List the simulated fleet with latest state |
| `GET` | `/api/v1/vehicles/{vehicle_id}` | One vehicle + its latest telemetry record |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/openapi.json` | OpenAPI 3 schema |

### Planned (subsequent phases)

| Method | Path | Phase |
| ------ | ---- | ----- |
| `GET` | `/api/v1/diagnostics` | 3 |
| `GET` | `/api/v1/diagnostics/{diagnostic_id}` | 3 |
| `GET` | `/api/v1/monitoring` | 4 |
| `GET` | `/api/v1/incidents` | 4 |

`POST /api/v1/vehicles/telemetry` currently returns the persisted telemetry record
(`201`). Phase 3 attaches the multi-agent diagnostic report to the response — it is
deliberately not faked in the meantime.

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
| `AUTOGUARD_LLM_PROVIDER` | `mock` | `mock`, `groq` or `ollama` |
| `AUTOGUARD_LLM_MODEL` | `llama-3.3-70b-versatile` | Model name for the active provider |
| `AUTOGUARD_GROQ_API_KEY` | *(empty)* | Required only for `groq`; stored as `SecretStr` |
| `AUTOGUARD_OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `AUTOGUARD_AGENT_MAX_RETRIES` | `1` | Safe retry budget per agent |

Startup fails fast if `AUTOGUARD_LLM_PROVIDER=groq` is set without an API key. Secrets are
never logged or returned by the API.

**Storage:** telemetry lives in a bounded in-process repository. Restarting the service
clears it. The `TelemetryRepository` interface allows a MongoDB Atlas implementation later
without touching the API or agents.

---

## Testing & quality

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest --cov=app --cov=simulator --cov-report=term-missing
```

---

## Project layout (Phase 2)

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
│   │       └── endpoints/vehicles.py   # Telemetry + fleet routes
│   ├── core/
│   │   ├── config.py           # Pydantic settings (typed, validated)
│   │   ├── correlation.py      # Correlation ID generation/sanitisation
│   │   ├── errors.py           # Domain error hierarchy
│   │   ├── logging.py          # JSON logging + context filter
│   │   └── middleware.py       # Request tracing
│   ├── models/
│   │   ├── common.py           # Error/health schemas
│   │   ├── enums.py            # Vehicle status, fuel type
│   │   ├── telemetry.py        # Strict telemetry contracts
│   │   └── vehicle.py          # Fleet read models
│   ├── services/
│   │   ├── fleet.py            # 5 simulated vehicles
│   │   ├── repositories.py     # TelemetryRepository + in-memory store
│   │   └── telemetry_service.py
│   ├── agents/                 # Phase 3
│   ├── orchestration/          # Phase 3
│   ├── monitoring/             # Phase 4
│   ├── incidents/              # Phase 4
│   └── utils/
├── simulator/
│   ├── scenarios.py            # Four deterministic scenarios
│   └── vehicle_simulator.py    # Seeded jitter + CLI
├── tests/
│   ├── unit/
│   └── api/
├── docs/ARCHITECTURE.md
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── .env.example
└── README.md
```

Planned additions: `agent_cards/`, `runbooks/`, `tests/integration/`, `tests/failure/`,
`.github/workflows/`, `Dockerfile`, `docker-compose.yml`, `DEPLOYMENT.md`.

---

## Engineering decisions (Phases 1–2)

- **Modular monolith, not microservices.** One FastAPI process keeps the multi-agent
  workflow debuggable while preserving clean package boundaries.
- **Correlation IDs live in a `ContextVar`.** This propagates automatically through async
  agent calls without threading an extra argument through every function.
- **Client-supplied correlation IDs are allow-listed.** Prevents log injection while
  still supporting distributed tracing from a frontend or gateway.
- **One error envelope.** Validation errors, 404s, domain errors and unexpected
  exceptions all return the same shape plus the correlation ID.
- **Structured JSON logs by default.** Log line fields (`correlation_id`, `agent`,
  `duration_ms`, `status`) map directly to the Phase 4 monitoring model.
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

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full target architecture.
