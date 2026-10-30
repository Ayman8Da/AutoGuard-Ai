"""Deterministic automotive rules.

This module is the single source of truth for sensor bands and DTC weights. The
Diagnostic Agent uses it to describe anomalies; the Risk Assessment Agent uses it
to compute the safety classification. An LLM never sees or modifies these
values.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.diagnostics import DTCInterpretation, FindingSeverity, RiskLevel


@dataclass(frozen=True)
class SensorAssessment:
    """Deterministic assessment of one out-of-band sensor reading."""

    code: str
    severity: FindingSeverity
    score: int
    title: str
    detail: str
    threshold: str


SENSOR_UNITS: dict[str, str] = {
    "engine_temperature_c": "°C",
    "battery_voltage_v": "V",
    "engine_vibration_mm_s": "mm/s",
}

SENSOR_LABELS: dict[str, str] = {
    "engine_temperature_c": "Engine temperature",
    "battery_voltage_v": "Battery voltage",
    "engine_vibration_mm_s": "Engine vibration",
}

#: Score added when a sensor cannot be read at all.
MISSING_SENSOR_SCORE = 2

#: Risk score → level. Hard safety overrides are applied separately.
RISK_BANDS: tuple[tuple[int, RiskLevel], ...] = (
    (1, RiskLevel.LOW),
    (5, RiskLevel.MEDIUM),
    (8, RiskLevel.HIGH),
)

THRESHOLD_VERSION = "1.0"


def assess_engine_temperature(value: float | None) -> SensorAssessment | None:
    if value is None:
        return None
    if value > 118:
        return SensorAssessment(
            code="ENGINE_TEMPERATURE_CRITICAL",
            severity=FindingSeverity.CRITICAL,
            score=6,
            title="Engine severely overheated",
            detail=f"Coolant temperature is {value:.1f} °C, above the safe limit.",
            threshold="> 118 °C",
        )
    if value > 110:
        return SensorAssessment(
            code="ENGINE_TEMPERATURE_HIGH",
            severity=FindingSeverity.HIGH,
            score=4,
            title="Engine temperature high",
            detail=f"Coolant temperature is {value:.1f} °C, well above the normal band.",
            threshold="> 110 °C",
        )
    if value > 100:
        return SensorAssessment(
            code="ENGINE_TEMPERATURE_ELEVATED",
            severity=FindingSeverity.WARNING,
            score=2,
            title="Engine temperature elevated",
            detail=f"Coolant temperature is {value:.1f} °C, above the normal band.",
            threshold="> 100 °C",
        )
    return None


def assess_battery_voltage(value: float | None) -> SensorAssessment | None:
    if value is None:
        return None
    if value < 11.8:
        return SensorAssessment(
            code="BATTERY_VOLTAGE_CRITICAL",
            severity=FindingSeverity.CRITICAL,
            score=5,
            title="Battery voltage critically low",
            detail=f"Battery voltage is {value:.2f} V; starting capability is at risk.",
            threshold="< 11.8 V",
        )
    if value < 12.4:
        return SensorAssessment(
            code="BATTERY_VOLTAGE_LOW",
            severity=FindingSeverity.HIGH,
            score=3,
            title="Battery voltage low",
            detail=f"Battery voltage is {value:.2f} V, below the healthy charging range.",
            threshold="< 12.4 V",
        )
    if value < 13.2:
        return SensorAssessment(
            code="BATTERY_VOLTAGE_WEAK",
            severity=FindingSeverity.WARNING,
            score=1,
            title="Charging voltage weak",
            detail=f"Battery voltage is {value:.2f} V, below the normal charging band.",
            threshold="< 13.2 V",
        )
    if value > 15.0:
        return SensorAssessment(
            code="BATTERY_VOLTAGE_OVERCHARGE",
            severity=FindingSeverity.WARNING,
            score=2,
            title="Charging voltage high",
            detail=f"Battery voltage is {value:.2f} V, suggesting possible overcharging.",
            threshold="> 15.0 V",
        )
    return None


def assess_engine_vibration(value: float | None) -> SensorAssessment | None:
    if value is None:
        return None
    if value > 8:
        return SensorAssessment(
            code="ENGINE_VIBRATION_CRITICAL",
            severity=FindingSeverity.CRITICAL,
            score=5,
            title="Severe engine vibration",
            detail=f"Engine vibration is {value:.2f} mm/s, indicating a severe mechanical fault.",
            threshold="> 8 mm/s",
        )
    if value > 6:
        return SensorAssessment(
            code="ENGINE_VIBRATION_HIGH",
            severity=FindingSeverity.HIGH,
            score=3,
            title="Engine vibration high",
            detail=f"Engine vibration is {value:.2f} mm/s, above the acceptable band.",
            threshold="> 6 mm/s",
        )
    if value > 3:
        return SensorAssessment(
            code="ENGINE_VIBRATION_ELEVATED",
            severity=FindingSeverity.WARNING,
            score=1,
            title="Engine vibration elevated",
            detail=f"Engine vibration is {value:.2f} mm/s, slightly above normal.",
            threshold="> 3 mm/s",
        )
    return None


@dataclass(frozen=True)
class DTCInfo:
    description: str
    system: str
    severity: FindingSeverity
    score: int


DTC_CATALOG: dict[str, DTCInfo] = {
    "P0217": DTCInfo(
        description="Engine coolant over-temperature condition",
        system="engine cooling",
        severity=FindingSeverity.CRITICAL,
        score=6,
    ),
    "P0301": DTCInfo(
        description="Cylinder 1 misfire detected",
        system="ignition",
        severity=FindingSeverity.HIGH,
        score=4,
    ),
    "P0128": DTCInfo(
        description="Coolant thermostat below regulating temperature",
        system="engine cooling",
        severity=FindingSeverity.WARNING,
        score=1,
    ),
    "U0100": DTCInfo(
        description="Lost communication with ECM/PCM",
        system="electrical",
        severity=FindingSeverity.HIGH,
        score=3,
    ),
}

UNKNOWN_DTC_SCORE = 1


def interpret_dtc(code: str) -> DTCInterpretation:
    info = DTC_CATALOG.get(code)
    if info is None:
        return DTCInterpretation(
            code=code,
            description="Unrecognised diagnostic trouble code",
            system="unknown",
            severity=FindingSeverity.WARNING,
            known=False,
        )
    return DTCInterpretation(
        code=code,
        description=info.description,
        system=info.system,
        severity=info.severity,
        known=True,
    )


def dtc_score(code: str) -> int:
    info = DTC_CATALOG.get(code)
    return info.score if info else UNKNOWN_DTC_SCORE


def score_to_level(score: int) -> RiskLevel:
    """Map a deterministic score to a risk level."""
    for upper_bound, level in RISK_BANDS:
        if score <= upper_bound:
            return level
    return RiskLevel.CRITICAL


def has_hard_override(
    engine_temperature_c: float | None,
    battery_voltage_v: float | None,
    engine_vibration_mm_s: float | None,
) -> bool:
    """Safety-critical breaches that always force CRITICAL."""
    return (
        (engine_temperature_c is not None and engine_temperature_c > 118)
        or (battery_voltage_v is not None and battery_voltage_v < 11.5)
        or (engine_vibration_mm_s is not None and engine_vibration_mm_s > 9)
    )
