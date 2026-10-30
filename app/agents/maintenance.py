"""Maintenance Agent: deterministic, prioritised advisory actions."""

from __future__ import annotations

from app.agents.rules import SENSOR_LABELS
from app.core.logging import get_logger
from app.models.diagnostics import (
    DiagnosticResult,
    MaintenanceAction,
    MaintenancePlan,
    MaintenancePriority,
    RiskAssessment,
    RiskLevel,
)

logger = get_logger("agents.maintenance")

_PRIORITY_BY_RISK: dict[RiskLevel, MaintenancePriority] = {
    RiskLevel.LOW: MaintenancePriority.ROUTINE,
    RiskLevel.MEDIUM: MaintenancePriority.SCHEDULED,
    RiskLevel.HIGH: MaintenancePriority.URGENT,
    RiskLevel.CRITICAL: MaintenancePriority.IMMEDIATE,
}

_PRIORITY_ORDER: dict[MaintenancePriority, int] = {
    MaintenancePriority.IMMEDIATE: 0,
    MaintenancePriority.URGENT: 1,
    MaintenancePriority.SCHEDULED: 2,
    MaintenancePriority.ROUTINE: 3,
}

_FINDING_ACTIONS: dict[str, tuple[str, str, str]] = {
    "ENGINE_TEMPERATURE": (
        "Inspect the engine cooling system",
        "Check coolant level and condition, thermostat operation, radiator and water pump.",
        "cooling",
    ),
    "BATTERY_VOLTAGE": (
        "Test the battery and charging system",
        "Load-test the battery and verify alternator output and belt condition.",
        "electrical",
    ),
    "ENGINE_VIBRATION": (
        "Diagnose engine vibration",
        "Inspect ignition components, injectors, compression and engine mounts.",
        "engine",
    ),
    "SENSOR_UNAVAILABLE": (
        "Inspect the affected sensor circuit",
        "Check sensor connector, wiring harness and signal with a diagnostic scan tool.",
        "sensors",
    ),
}

_DTC_ACTIONS: dict[str, tuple[str, str, str]] = {
    "P0217": (
        "Investigate the over-temperature condition",
        "Pressure-test the cooling system and verify fan and thermostat operation.",
        "cooling",
    ),
    "P0301": (
        "Perform a cylinder 1 misfire diagnosis",
        "Inspect spark plug, ignition coil, injector and compression for cylinder 1.",
        "engine",
    ),
    "P0128": (
        "Inspect the coolant thermostat",
        "Verify thermostat opening behaviour and coolant temperature sensor readings.",
        "cooling",
    ),
    "U0100": (
        "Check ECM/PCM communication wiring",
        "Inspect CAN wiring, connectors and power/ground feeds to the ECM/PCM.",
        "electrical",
    ),
}

_NOTES = (
    "Advisory recommendations only. No inspection or repair has been performed; a "
    "qualified technician must verify findings on the physical vehicle."
)


class MaintenanceAgent:
    """Prioritises inspection actions from findings and risk."""

    name = "MaintenanceAgent"

    def recommend(
        self, diagnostic: DiagnosticResult, risk: RiskAssessment
    ) -> MaintenancePlan:
        priority = _PRIORITY_BY_RISK[risk.level]
        actions: dict[str, MaintenanceAction] = {}

        def add(title: str, description: str, category: str, trigger: str) -> None:
            existing = actions.get(title)
            if existing is not None:
                if trigger not in existing.related_findings:
                    existing.related_findings.append(trigger)
                return
            actions[title] = MaintenanceAction(
                title=title,
                description=description,
                category=category,
                priority=priority,
                rationale=(
                    f"Selected because {trigger} was detected at "
                    f"{risk.level.value.upper()} risk."
                ),
                related_findings=[trigger],
            )

        for finding in diagnostic.findings:
            if finding.code == "SENSOR_UNAVAILABLE" and finding.sensor:
                title, description, category = _FINDING_ACTIONS["SENSOR_UNAVAILABLE"]
                add(
                    f"{title} ({SENSOR_LABELS[finding.sensor]})",
                    description,
                    category,
                    finding.code,
                )
                continue
            prefix = finding.code.rsplit("_", 1)[0]
            template = _FINDING_ACTIONS.get(prefix)
            if template is not None:
                add(*template, finding.code)

        for interpretation in diagnostic.dtc_interpretations:
            template = _DTC_ACTIONS.get(interpretation.code)
            if template is not None:
                add(*template, interpretation.code)
            else:
                add(
                    f"Perform a full diagnostic scan for {interpretation.code}",
                    "Retrieve freeze-frame data and follow the manufacturer procedure.",
                    "diagnostics",
                    interpretation.code,
                )

        if not actions:
            add(
                "Continue routine monitoring",
                "No abnormal conditions detected; keep the regular maintenance schedule.",
                "routine",
                "normal telemetry",
            )

        ordered = sorted(actions.values(), key=lambda action: _PRIORITY_ORDER[action.priority])
        logger.info(
            "maintenance_recommended",
            extra={
                "risk_level": risk.level.value,
                "plan_priority": priority.value,
                "action_count": len(ordered),
                "repair_performed": False,
            },
        )
        return MaintenancePlan(priority=priority, actions=ordered, notes=_NOTES)
