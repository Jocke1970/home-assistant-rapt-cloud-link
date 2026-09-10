from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity

from .base import BaseRaptEntity
from .const import DOMAIN

MAX_PROFILE_STEPS = 32


def _profile_context(device: dict[str, Any]) -> dict[str, Any]:
    """Return a compact BrewAssistant-friendly active-profile snapshot."""
    session = device.get("activeProfileSession")
    if not isinstance(session, dict):
        session = {}

    profile = session.get("profile")
    if not isinstance(profile, dict):
        profile = {}

    raw_steps = profile.get("steps")
    steps = [step for step in raw_steps if isinstance(step, dict)] if isinstance(raw_steps, list) else []

    profile_id = device.get("activeProfileId") or session.get("profileId") or profile.get("id")
    step_id = device.get("activeProfileStepId")

    current_step: dict[str, Any] = {}
    current_index: int | None = None
    for index, step in enumerate(steps):
        if step.get("id") == step_id:
            current_step = step
            current_index = index
            break

    next_step: dict[str, Any] = {}
    if current_index is not None and current_index + 1 < len(steps):
        next_step = steps[current_index + 1]

    # Treat the profile as active while the profile id and concrete session are
    # present. Do not key activity only on activeProfileStepId; a transient step
    # handoff must never look like a confirmed STOP to BrewAssistant.
    active = bool(profile_id and session)
    contract_complete = bool(active and step_id)

    compact_steps = []
    for index, step in enumerate(steps[:MAX_PROFILE_STEPS]):
        order = step.get("order")
        step_number = int(order) + 1 if isinstance(order, int) else index + 1
        compact_steps.append(
            {
                "step_number": step_number,
                "id": step.get("id"),
                "name": step.get("name"),
                "order": order,
                "control_type": step.get("controlType"),
                "end_type": step.get("endType"),
                "duration_type": step.get("durationType"),
                "length": step.get("length"),
                "target_temperature": step.get("temperature"),
                "pump_enabled": step.get("pumpEnabled"),
                "pump_utilisation": step.get("pumpUtilisation"),
                "heating_utilisation": step.get("heatingUtilisation"),
                "pid_enabled": step.get("pidEnabled"),
                "sensor_differential": step.get("sensorDifferential"),
            }
        )

    current_order = current_step.get("order")
    if isinstance(current_order, int):
        current_step_number = current_order + 1
    elif current_index is not None:
        current_step_number = current_index + 1
    else:
        current_step_number = None

    return {
        "active": active,
        "contract_complete": contract_complete,
        "profile_id": profile_id,
        "profile_name": profile.get("name") or session.get("name"),
        "profile_session_id": session.get("id"),
        "profile_session_start_date": session.get("startDate"),
        "profile_length": session.get("profileLength"),
        "step_id": step_id,
        "step_number": current_step_number,
        "step_name": current_step.get("name"),
        "step_order": current_step.get("order"),
        "step_target_temperature": current_step.get("temperature"),
        "step_control_type": current_step.get("controlType"),
        "step_end_type": current_step.get("endType"),
        "step_duration_type": current_step.get("durationType"),
        "step_length": current_step.get("length"),
        "step_pid_enabled": current_step.get("pidEnabled"),
        "next_step_id": next_step.get("id"),
        "next_step_name": next_step.get("name"),
        "next_step_target_temperature": next_step.get("temperature"),
        "step_count": len(steps),
        "profile_steps": compact_steps,
        "profile_steps_truncated": len(steps) > MAX_PROFILE_STEPS,
    }


async def async_setup_entry(hass, entry, async_add_entities):
    brewzilla_coordinator = hass.data[DOMAIN][entry.entry_id]["brewzilla_coordinator"]
    entities = [
        BrewZillaProfileActiveBinarySensor(brewzilla_coordinator, device_id)
        for device_id in brewzilla_coordinator.data
    ]
    if entities:
        async_add_entities(entities, update_before_add=True)


class BrewZillaProfileActiveBinarySensor(BaseRaptEntity, BinarySensorEntity):
    """Expose the active local BrewZilla profile as a stable BA contract."""

    _attr_icon = "mdi:playlist-play"

    def __init__(self, coordinator, device_id: str):
        super().__init__(coordinator, device_id, model="BrewZilla")
        self._attr_name = f"{self._device_name} Profile Active"
        self._attr_unique_id = f"{device_id}_profile_active"

    @property
    def is_on(self) -> bool:
        device = self.coordinator.data.get(self._device_id, {})
        return bool(_profile_context(device).get("active"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self.coordinator.data.get(self._device_id, {})
        context = _profile_context(device)
        return {
            "ba_source": "rapt_cloud_link_brewzilla_profile_runtime",
            "raw_device_id": self._device_id,
            "profile_active": bool(context.get("active")),
            "profile_contract_complete": bool(context.get("contract_complete")),
            "profile_id": context.get("profile_id"),
            "profile_name": context.get("profile_name"),
            "profile_session_id": context.get("profile_session_id"),
            "profile_session_start_date": context.get("profile_session_start_date"),
            "profile_length": context.get("profile_length"),
            "step_id": context.get("step_id"),
            "step_number": context.get("step_number"),
            "step_name": context.get("step_name"),
            "step_order": context.get("step_order"),
            "step_target_temperature": context.get("step_target_temperature"),
            "step_control_type": context.get("step_control_type"),
            "step_end_type": context.get("step_end_type"),
            "step_duration_type": context.get("step_duration_type"),
            "step_length": context.get("step_length"),
            "step_pid_enabled": context.get("step_pid_enabled"),
            "next_step_id": context.get("next_step_id"),
            "next_step_name": context.get("next_step_name"),
            "next_step_target_temperature": context.get("next_step_target_temperature"),
            "step_count": context.get("step_count", 0),
            "profile_steps": context.get("profile_steps", []),
            "profile_steps_truncated": bool(context.get("profile_steps_truncated")),
        }
