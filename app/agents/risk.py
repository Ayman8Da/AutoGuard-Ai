"""Risk Assessment Agent: deterministic severity classification.

No LLM is involved in this agent. Scores come from ``app.agents.rules`` and are
reproducible for identical telemetry.
"""

from __future__ import annotations

from app.agents.rules import (
    MISSING_SENSOR_SCORE,
    SENSOR_LABELS,
    THRESHOLD_VERSION,
    assess_battery_voltage,
    assess_engine_temperature,
    assess_engine_vibration,
    dtc_score,
    has_hard_override,
    score_to_level,
)
from app.core.logging import get_logger
from app.models.diagnostics import (
    DiagnosticResult,
    RiskAssessment,
    RiskLevel,
    RiskReason,
)
from app.models.telemetry import VehicleTelemetry

logger = get_logger("agents.risk")

_SENSOR_ASSESSORS = (
    ("engine_temperature_c", assess_engine_temperature),
    ("battery_voltage_v", assess_battery_voltage),
    ("engine_vibration_mm_s", assess_engine_vibration),
)


class RiskAssessmentAgent:
    """Assigns LOW/MEDIUM/HIGH/CRITICAL using deterministic scoring."""

    name = "RiskAssessmentAgent"

    def assess(self, telemetry: VehicleTelemetry, diagnostic: DiagnosticResult) -> RiskAssessment:
        score = 0
        reasons: list[RiskReason] = []

        for sensor_name, assessor in _SENSOR_ASSESSORS:
            assessment = assessor(getattr(telemetry.sensors, sensor_name))
            if assessment is None:
                continue
            score += assessment.score
            reasons.append(
                RiskReason(
                    code=assessment.code,
                    description=f"{assessment.title}: {assessment.detail}",
                    score=assessment.score,
                )
            )

        for sensor_name in diagnostic.unavailable_sensors:
            score += MISSING_SENSOR_SCORE
            reasons.append(
                RiskReason(
                    code=f"SENSOR_UNAVAILABLE_{sensor_name.upper()}",
                    description=(
                        f"{SENSOR_LABELS[sensor_name]} is unavailable, so the condition "
                        "cannot be fully assessed."
                    ),
                    score=MISSING_SENSOR_SCORE,
                )
            )

        for interpretation in diagnostic.dtc_interpretations:
            weight = dtc_score(interpretation.code)
            score += weight
            reasons.append(
                RiskReason(
                    code=f"DTC_{interpretation.code}",
                    description=f"{interpretation.code}: {interpretation.description}",
                    score=weight,
                )
            )

        sensors = telemetry.sensors
        override = has_hard_override(
            sensors.engine_temperature_c,
            sensors.battery_voltage_v,
            sensors.engine_vibration_mm_s,
        )

        if override:
            level = RiskLevel.CRITICAL
            reasons.append(
                RiskReason(
                    code="SAFETY_OVERRIDE",
                    description=(
                        "A safety-critical sensor threshold was breached; risk is forced "
                        "to CRITICAL regardless of the aggregate score."
                    ),
                    score=0,
                )
            )
        else:
            level = score_to_level(score)

        if not reasons:
            reasons.append(
                RiskReason(
                    code="NO_ANOMALIES",
                    description="All monitored values are within their configured bands.",
                    score=0,
                )
            )

        assessment = RiskAssessment(
            level=level,
            score=score,
            reasons=reasons,
            hard_override=override,
            threshold_version=THRESHOLD_VERSION,
        )
        logger.info(
            "risk_assessed",
            extra={
                "risk_level": level.value,
                "risk_score": score,
                "hard_override": override,
                "threshold_version": THRESHOLD_VERSION,
            },
        )
        return assessment
