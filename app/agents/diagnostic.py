"""Diagnostic Agent: deterministic findings plus an optional LLM narrative."""

from __future__ import annotations

import time

from app.agents.llm import NarrativeClient, NarrativeRequest
from app.agents.rules import (
    SENSOR_LABELS,
    SENSOR_UNITS,
    assess_battery_voltage,
    assess_engine_temperature,
    assess_engine_vibration,
    interpret_dtc,
)
from app.core.logging import get_logger
from app.models.diagnostics import (
    DiagnosticResult,
    DTCInterpretation,
    Finding,
    FindingSeverity,
)
from app.models.telemetry import VehicleTelemetry

logger = get_logger("agents.diagnostic")

_SENSOR_ASSESSORS = (
    ("engine_temperature_c", assess_engine_temperature),
    ("battery_voltage_v", assess_battery_voltage),
    ("engine_vibration_mm_s", assess_engine_vibration),
)

_FAULT_BY_FINDING: dict[str, str] = {
    "ENGINE_TEMPERATURE_ELEVATED": (
        "Cooling system degradation (thermostat, coolant level or radiator)"
    ),
    "ENGINE_TEMPERATURE_HIGH": "Cooling system fault (coolant loss, thermostat or water pump)",
    "ENGINE_TEMPERATURE_CRITICAL": (
        "Severe cooling failure (coolant loss, water pump or head gasket)"
    ),
    "BATTERY_VOLTAGE_WEAK": "Charging system degradation (alternator or battery)",
    "BATTERY_VOLTAGE_LOW": "Battery or alternator fault",
    "BATTERY_VOLTAGE_CRITICAL": "Battery failure or charging system failure",
    "BATTERY_VOLTAGE_OVERCHARGE": "Voltage regulator or alternator fault",
    "ENGINE_VIBRATION_ELEVATED": "Early ignition, fuelling or engine-mount wear",
    "ENGINE_VIBRATION_HIGH": "Engine misfire or worn engine mounts",
    "ENGINE_VIBRATION_CRITICAL": "Severe mechanical fault (misfire, mounts or internal damage)",
}

_FAULT_BY_DTC: dict[str, str] = {
    "P0217": "Engine overheating condition",
    "P0301": "Cylinder 1 misfire (ignition, injector or compression)",
    "P0128": "Coolant thermostat stuck open or cooling system fault",
    "U0100": "ECM/PCM communication or wiring fault",
}


class DiagnosticAgent:
    """Turns telemetry into structured findings and DTC interpretations."""

    name = "DiagnosticAgent"

    def __init__(self, narrative_client: NarrativeClient, max_llm_retries: int = 1) -> None:
        self._narrative_client = narrative_client
        self._max_llm_retries = max_llm_retries

    async def analyze(self, telemetry: VehicleTelemetry) -> DiagnosticResult:
        findings: list[Finding] = []

        for sensor_name, assessor in _SENSOR_ASSESSORS:
            value = getattr(telemetry.sensors, sensor_name)
            assessment = assessor(value)
            if assessment is None:
                continue
            findings.append(
                Finding(
                    code=assessment.code,
                    sensor=sensor_name,
                    title=assessment.title,
                    detail=assessment.detail,
                    severity=assessment.severity,
                    value=value,
                    unit=SENSOR_UNITS[sensor_name],
                    threshold=assessment.threshold,
                )
            )

        unavailable_sensors = [
            sensor_name
            for sensor_name, _ in _SENSOR_ASSESSORS
            if getattr(telemetry.sensors, sensor_name) is None
        ]
        for sensor_name in unavailable_sensors:
            label = SENSOR_LABELS[sensor_name]
            findings.append(
                Finding(
                    code="SENSOR_UNAVAILABLE",
                    sensor=sensor_name,
                    title=f"{label} sensor unavailable",
                    detail=(
                        f"{label} did not report a value; the sensor, wiring or connector "
                        "may have failed."
                    ),
                    severity=FindingSeverity.WARNING,
                    value=None,
                    unit=SENSOR_UNITS[sensor_name],
                )
            )

        interpretations = [interpret_dtc(code) for code in telemetry.error_codes]
        suspected_faults = self._suspected_faults(findings, interpretations)

        request = NarrativeRequest(
            vehicle_id=telemetry.vehicle_id,
            findings=findings,
            dtc_interpretations=interpretations,
            suspected_faults=suspected_faults,
            unavailable_sensors=unavailable_sensors,
        )
        summary, source, attempts, error, duration = await self._narrate(
            request, findings, interpretations, suspected_faults
        )

        return DiagnosticResult(
            findings=findings,
            dtc_interpretations=interpretations,
            unavailable_sensors=unavailable_sensors,
            suspected_faults=suspected_faults,
            summary=summary,
            narrative_source=source,
            llm_attempts=attempts,
            llm_error=error,
            llm_duration_ms=duration,
        )

    async def _narrate(
        self,
        request: NarrativeRequest,
        findings: list[Finding],
        interpretations: list[DTCInterpretation],
        suspected_faults: list[str],
    ) -> tuple[str, str, int, str | None, float]:
        provider = getattr(self._narrative_client, "provider_name", "unknown")
        started = time.perf_counter()
        attempts = 0
        last_error: str | None = None

        for _ in range(self._max_llm_retries + 1):
            attempts += 1
            try:
                summary = await self._narrative_client.summarise(request)
            except Exception as exc:  # providers must never break the workflow
                last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                logger.warning(
                    "llm_narrative_attempt_failed",
                    extra={
                        "provider": provider,
                        "attempt": attempts,
                        "error_type": type(exc).__name__,
                    },
                )
                continue

            duration = round((time.perf_counter() - started) * 1000, 2)
            source = "mock" if provider == "mock" else "llm"
            logger.info(
                "llm_narrative_completed",
                extra={
                    "provider": provider,
                    "attempts": attempts,
                    "duration_ms": duration,
                    "narrative_source": source,
                },
            )
            return summary, source, attempts, None, duration

        duration = round((time.perf_counter() - started) * 1000, 2)
        logger.error(
            "llm_narrative_unavailable",
            extra={"provider": provider, "attempts": attempts, "duration_ms": duration},
        )
        return (
            self._fallback_summary(findings, interpretations, suspected_faults),
            "fallback",
            attempts,
            last_error,
            duration,
        )

    @staticmethod
    def _fallback_summary(
        findings: list[Finding],
        interpretations: list[DTCInterpretation],
        suspected_faults: list[str],
    ) -> str:
        if not findings and not interpretations:
            return (
                "No abnormal sensor readings or diagnostic trouble codes were detected "
                "in this telemetry frame."
            )
        suspects = "; ".join(suspected_faults[:3]) or "further inspection required"
        return (
            f"{len(findings)} abnormal reading(s) and {len(interpretations)} trouble "
            f"code(s) detected. Suspected causes: {suspects}."
        )

    @staticmethod
    def _suspected_faults(
        findings: list[Finding], interpretations: list[DTCInterpretation]
    ) -> list[str]:
        suspects: list[str] = []
        for finding in findings:
            if finding.code == "SENSOR_UNAVAILABLE" and finding.sensor:
                label = SENSOR_LABELS[finding.sensor]
                candidate = f"{label} sensor, wiring or connector fault"
            else:
                candidate = _FAULT_BY_FINDING.get(finding.code, "Unclassified abnormality")
            if candidate not in suspects:
                suspects.append(candidate)
        for interpretation in interpretations:
            candidate = _FAULT_BY_DTC.get(
                interpretation.code,
                f"Unrecognised trouble code {interpretation.code} requires a full scan",
            )
            if candidate not in suspects:
                suspects.append(candidate)
        return suspects
