"""Unit tests for deterministic sensor/DTC rules and risk bands."""

from __future__ import annotations

import pytest
from app.agents.rules import (
    assess_battery_voltage,
    assess_engine_temperature,
    assess_engine_vibration,
    dtc_score,
    has_hard_override,
    interpret_dtc,
    score_to_level,
)
from app.models.diagnostics import FindingSeverity, RiskLevel


@pytest.mark.parametrize(
    ("value", "code", "severity", "score"),
    [
        (100.0, None, None, None),
        (100.1, "ENGINE_TEMPERATURE_ELEVATED", FindingSeverity.WARNING, 2),
        (110.0, "ENGINE_TEMPERATURE_ELEVATED", FindingSeverity.WARNING, 2),
        (110.1, "ENGINE_TEMPERATURE_HIGH", FindingSeverity.HIGH, 4),
        (118.0, "ENGINE_TEMPERATURE_HIGH", FindingSeverity.HIGH, 4),
        (118.1, "ENGINE_TEMPERATURE_CRITICAL", FindingSeverity.CRITICAL, 6),
    ],
)
def test_engine_temperature_thresholds(
    value: float, code: str | None, severity: FindingSeverity | None, score: int | None
) -> None:
    assessment = assess_engine_temperature(value)

    if code is None:
        assert assessment is None
        return
    assert assessment is not None
    assert assessment.code == code
    assert assessment.severity is severity
    assert assessment.score == score


@pytest.mark.parametrize(
    ("value", "code", "score"),
    [
        (15.0, None, None),
        (15.1, "BATTERY_VOLTAGE_OVERCHARGE", 2),
        (13.2, None, None),
        (13.19, "BATTERY_VOLTAGE_WEAK", 1),
        (12.4, "BATTERY_VOLTAGE_WEAK", 1),
        (12.39, "BATTERY_VOLTAGE_LOW", 3),
        (11.8, "BATTERY_VOLTAGE_LOW", 3),
        (11.79, "BATTERY_VOLTAGE_CRITICAL", 5),
    ],
)
def test_battery_thresholds(value: float, code: str | None, score: int | None) -> None:
    assessment = assess_battery_voltage(value)

    if code is None:
        assert assessment is None
        return
    assert assessment is not None
    assert assessment.code == code
    assert assessment.score == score


@pytest.mark.parametrize(
    ("value", "code", "score"),
    [
        (3.0, None, None),
        (3.1, "ENGINE_VIBRATION_ELEVATED", 1),
        (6.0, "ENGINE_VIBRATION_ELEVATED", 1),
        (6.1, "ENGINE_VIBRATION_HIGH", 3),
        (8.0, "ENGINE_VIBRATION_HIGH", 3),
        (8.1, "ENGINE_VIBRATION_CRITICAL", 5),
    ],
)
def test_vibration_thresholds(value: float, code: str | None, score: int | None) -> None:
    assessment = assess_engine_vibration(value)

    if code is None:
        assert assessment is None
        return
    assert assessment is not None
    assert assessment.code == code
    assert assessment.score == score


def test_unavailable_readings_produce_no_assessment() -> None:
    assert assess_engine_temperature(None) is None
    assert assess_battery_voltage(None) is None
    assert assess_engine_vibration(None) is None


@pytest.mark.parametrize(
    ("score", "level"),
    [
        (0, RiskLevel.LOW),
        (1, RiskLevel.LOW),
        (2, RiskLevel.MEDIUM),
        (5, RiskLevel.MEDIUM),
        (6, RiskLevel.HIGH),
        (8, RiskLevel.HIGH),
        (9, RiskLevel.CRITICAL),
        (26, RiskLevel.CRITICAL),
    ],
)
def test_score_to_level_bands(score: int, level: RiskLevel) -> None:
    assert score_to_level(score) is level


@pytest.mark.parametrize(
    ("temperature", "battery", "vibration", "expected"),
    [
        (118.0, 11.5, 9.0, False),
        (118.1, None, None, True),
        (None, 11.49, None, True),
        (None, None, 9.01, True),
        (None, None, None, False),
    ],
)
def test_hard_override_boundaries(
    temperature: float | None,
    battery: float | None,
    vibration: float | None,
    expected: bool,
) -> None:
    assert has_hard_override(temperature, battery, vibration) is expected


def test_known_dtc_is_interpreted_and_weighted() -> None:
    interpretation = interpret_dtc("P0217")

    assert interpretation.known is True
    assert interpretation.system == "engine cooling"
    assert interpretation.severity is FindingSeverity.CRITICAL
    assert dtc_score("P0217") == 6


def test_unknown_dtc_is_flagged_for_verification() -> None:
    interpretation = interpret_dtc("P0999")

    assert interpretation.known is False
    assert interpretation.system == "unknown"
    assert dtc_score("P0999") == 1
