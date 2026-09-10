import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import BONDED_DEVICE_TYPES, CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT, DOMAIN
from .base import BaseRaptSensor

_LOGGER = logging.getLogger(__name__)


BREWZILLA_EXTERNAL_TEMP_CANDIDATE_KEYS = (
    "controlDeviceTemperature",
    "control_device_temperature",
    "controlDeviceTemp",
    "control_device_temp",
    "externalTemperature",
    "external_temperature",
    "externalTemp",
    "external_temp",
    "probeTemperature",
    "probe_temperature",
    "probeTemp",
    "probe_temp",
    "bleTemperature",
    "ble_temperature",
    "bluetoothTemperature",
    "bluetooth_temperature",
    "mashTemperature",
    "mash_temperature",
    "mashTemp",
    "mash_temp",
    "temperature2",
    "temperature_2",
)


def _debug_first_telemetry_item(device: dict) -> dict:
    """Return first telemetry-like payload item without requiring prior BA helpers."""
    for key in ("telemetry", "telemetries", "readings", "values"):
        telemetry = device.get(key)
        if isinstance(telemetry, list) and telemetry and isinstance(telemetry[0], dict):
            return telemetry[0]
        if isinstance(telemetry, dict):
            return telemetry
    return {}


def _debug_get_value(device: dict, key: str):
    """Return value from root payload or first telemetry payload."""
    if key in device and device.get(key) is not None:
        return device.get(key)
    telemetry = _debug_first_telemetry_item(device)
    if key in telemetry and telemetry.get(key) is not None:
        return telemetry.get(key)
    return None


def _debug_pick_values(device: dict, keys: tuple[str, ...]) -> dict:
    """Return non-empty candidate values from a device payload."""
    values = {}
    for key in keys:
        value = _debug_get_value(device, key)
        if value not in (None, ""):
            values[key] = value
    return values


def _debug_profile_runtime_snapshot(device: dict) -> dict:
    """Return a bounded snapshot of BrewZilla active profile/session data."""
    telemetry = _debug_first_telemetry_item(device)

    session = device.get("activeProfileSession")
    if not isinstance(session, dict):
        session = {}

    profile = session.get("profile")
    if not isinstance(profile, dict):
        profile = {}

    raw_steps = profile.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []

    step_keys = sorted(
        {
            key
            for step in steps
            if isinstance(step, dict)
            for key in step.keys()
        }
    )

    preview_fields = (
        "id",
        "name",
        "order",
        "controlType",
        "endType",
        "durationType",
        "length",
        "temperature",
        "minTemperature",
        "maxTemperature",
        "pumpEnabled",
        "pumpUtilisation",
        "heatingUtilisation",
        "pidEnabled",
        "sensorDifferential",
    )
    steps_preview = []
    for step in steps[:20]:
        if not isinstance(step, dict):
            continue
        steps_preview.append(
            {
                key: step.get(key)
                for key in preview_fields
                if step.get(key) is not None
            }
        )

    session_profile_id = session.get("profileId")
    if session_profile_id is None:
        session_profile_id = profile.get("id")

    return {
        "active_profile_id": device.get("activeProfileId"),
        "active_profile_step_id": device.get("activeProfileStepId"),
        "active_profile_session_keys": sorted(session.keys()) if session else [],
        "active_profile_session_profile_id": session_profile_id,
        "active_profile_session_start_date": session.get("startDate"),
        "active_profile_session_end_date": session.get("endDate"),
        "active_profile_session_estimated_end_date": session.get("estimatedEndDate"),
        "active_profile_session_profile_length": session.get("profileLength"),
        "active_profile_session_current_time": session.get("currentProfileTime"),
        "active_profile_session_remaining_time": session.get("remainingProfileTime"),
        "profile_id": profile.get("id"),
        "profile_name": profile.get("name"),
        "profile_keys": sorted(profile.keys()) if profile else [],
        "profile_steps_count": len(steps),
        "profile_step_keys": step_keys,
        "profile_steps_preview": steps_preview,
        "profile_steps_truncated": len(steps) > 20,
        "telemetry_profile_id": telemetry.get("profileId"),
        "telemetry_profile_step_id": telemetry.get("profileStepId"),
        "telemetry_profile_session_start_date": telemetry.get("profileSessionStartDate"),
        "telemetry_profile_session_time": telemetry.get("profileSessionTime"),
        "telemetry_profile_step_progress": telemetry.get("profileStepProgress"),
    }


TELEMETRY_KEYS = ("telemetry", "telemetries", "readings", "values")
UPDATED_AT_KEYS = (
    "updatedAt",
    "updated_at",
    "lastUpdated",
    "last_updated",
    "lastSeen",
    "last_seen",
    "timestamp",
    "timeStamp",
)
PARENT_DEVICE_ID_KEYS = (
    "parentDeviceId",
    "parent_device_id",
    "gatewayDeviceId",
    "gateway_device_id",
    "linkedDeviceId",
    "linked_device_id",
)


def _first_telemetry_item(device: dict) -> dict:
    """Return the first telemetry-like item from the device payload."""
    for key in TELEMETRY_KEYS:
        telemetry = device.get(key)
        if isinstance(telemetry, list) and telemetry:
            if isinstance(telemetry[0], dict):
                return telemetry[0]
        if isinstance(telemetry, dict):
            return telemetry
    return {}


def _get_device_value(device: dict, key: str, default=None):
    """Return a value from the root payload or the first telemetry payload."""
    if not isinstance(device, dict):
        return default
    if key in device and device.get(key) is not None:
        return device.get(key)
    telemetry = _first_telemetry_item(device)
    if key in telemetry and telemetry.get(key) is not None:
        return telemetry.get(key)
    return default


def _get_first_existing_value(device: dict, keys: tuple[str, ...]):
    """Return the first non-empty value for a list of possible payload keys."""
    for key in keys:
        value = _get_device_value(device, key)
        if value not in (None, ""):
            return value
    return None


def _rounded_device_value(device: dict, key: str, digits: int = 1):
    """Return a rounded numeric payload value, or None if not numeric."""
    value = _get_device_value(device, key)
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None



def _numeric_payload_value(value):
    """Return a float payload value, or None if not numeric."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid_control_device_temperature(value) -> bool:
    """Return whether a control-device temperature looks like real BLE data."""
    numeric = _numeric_payload_value(value)
    if numeric is None:
        return False

    # RAPT/BrewZilla can expose 0.0 when no cloud-side BLE value is available.
    # Treat that as unavailable, not as a real mash temperature.
    return abs(numeric) > 0.001


def _control_device_temperature_snapshot(device: dict) -> dict:
    """Return root, telemetry and selected control-device temperature metadata."""
    telemetry = _first_telemetry_item(device)

    root_raw = device.get("controlDeviceTemperature") if isinstance(device, dict) else None
    telemetry_raw = telemetry.get("controlDeviceTemperature") if isinstance(telemetry, dict) else None

    root_value = _numeric_payload_value(root_raw)
    telemetry_value = _numeric_payload_value(telemetry_raw)

    selected = None
    selected_source = None

    # Prefer telemetry. It is usually the fresher cloud observation.
    if _valid_control_device_temperature(telemetry_value):
        selected = telemetry_value
        selected_source = "telemetry"
    elif _valid_control_device_temperature(root_value):
        selected = root_value
        selected_source = "root"

    rejected = selected is None and (root_raw not in (None, "") or telemetry_raw not in (None, ""))

    return {
        "root_control_device_temperature": round(root_value, 1) if root_value is not None else None,
        "telemetry_control_device_temperature": round(telemetry_value, 1) if telemetry_value is not None else None,
        "selected_control_device_temperature": round(selected, 1) if selected is not None else None,
        "selected_control_device_temperature_source": selected_source,
        "ba_value_rejected": rejected,
        "ba_reject_reason": "control_device_temperature_zero_or_invalid" if rejected else None,
    }

def _brewzilla_control_device_attributes(device: dict, device_id: str) -> dict:
    """Return metadata for BrewZilla external/control-device temperature."""
    control_temp = _control_device_temperature_snapshot(device)
    attrs = {
        "ba_source": "rapt_cloud_link_brewzilla_control_device",
        "raw_device_id": device_id,
        "control_device_type": _get_device_value(device, "controlDeviceType"),
        "control_device_mac_address": _get_device_value(device, "controlDeviceMacAddress"),
        "use_internal_sensor": _get_device_value(device, "useInternalSensor"),
        "sensor_differential": _get_device_value(device, "sensorDifferential"),
        **control_temp,
    }
    return {key: value for key, value in attrs.items() if value not in (None, "", [])}


def _bonded_device_attributes(device: dict) -> dict:
    """Return BrewAssistant-friendly metadata for bonded devices."""
    telemetry = _first_telemetry_item(device)
    attrs = {
        "ba_source": "rapt_cloud_link_bonded_device",
        "device_type": device.get("deviceType"),
        "raw_device_id": device.get("id"),
        "parent_device_id": _get_first_existing_value(device, PARENT_DEVICE_ID_KEYS),
        "updated_at": _get_first_existing_value(device, UPDATED_AT_KEYS),
    }

    # Expose payload keys for first-pass BLE mapping/debug without dumping
    # the whole raw payload into the HA state machine.
    attrs["payload_keys"] = sorted(device.keys())
    if telemetry:
        attrs["telemetry_keys"] = sorted(telemetry.keys())

    return {key: value for key, value in attrs.items() if value not in (None, "", [])}



async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    brewzilla_coordinator = hass.data[DOMAIN][entry.entry_id]["brewzilla_coordinator"]
    hydrometer_coordinator = hass.data[DOMAIN][entry.entry_id]["hydrometer_coordinator"]
    temperature_controller_coordinator = hass.data[DOMAIN][entry.entry_id]["temperature_controller_coordinator"]
    bonded_devices_coordinator = hass.data[DOMAIN][entry.entry_id]["bonded_devices_coordinator"]

    sensors = []

    # BrewAssistant diagnostics: always expose bonded device discovery state.
    sensors.append(BondedDevicesDebugSensor(bonded_devices_coordinator))

    # Bonded Devices
    for device_id, device in bonded_devices_coordinator.data.items():
        if device.get("deviceType") in BONDED_DEVICE_TYPES:
            device_type = device.get("deviceType")
            if "Temp" in device_type:
                sensors.append(BondedDeviceTemperatureSensor(bonded_devices_coordinator, device_id))
            if "Humidity" in device_type:
                sensors.append(BondedDeviceHumiditySensor(bonded_devices_coordinator, device_id))
            if "Pressure" in device_type:
                sensors.append(BondedDevicePressureSensor(bonded_devices_coordinator, device_id))
            sensors.append(BondedDeviceBatterySensor(bonded_devices_coordinator, device_id))
            sensors.append(BondedDeviceConnectionStateSensor(bonded_devices_coordinator, device_id))

    # BrewAssistant diagnostics: expose BrewZilla raw discovery state.
    sensors.append(BrewZillaDebugSensor(brewzilla_coordinator))

    # BrewZilla
    for device_id, device in brewzilla_coordinator.data.items():
        # name = device.get("name", f"BrewZilla {device_id}")
        sensors.append(BrewZillaTemperatureSensor(brewzilla_coordinator, device_id))
        sensors.append(BrewZillaControlDeviceTemperatureSensor(brewzilla_coordinator, device_id))
        sensors.append(BrewZillaBleThermometerTemperatureSensor(brewzilla_coordinator, device_id))
        sensors.append(BrewZillaConnectionStateSensor(brewzilla_coordinator, device_id))

    # Hydrometer
    for device_id, device in hydrometer_coordinator.data.items():
        # name = device.get("name", f"Pill {device_id}")
        sensors.append(HydrometerTemperatureSensor(hydrometer_coordinator, device_id))
        sensors.append(HydrometerGravitySensor(hydrometer_coordinator, device_id))
        sensors.append(HydrometerBatterySensor(hydrometer_coordinator, device_id))
        sensors.append(HydrometerConnectionStateSensor(hydrometer_coordinator, device_id))

    # Temperature Controller
    for device_id, device in temperature_controller_coordinator.data.items():
        # name = device.get("name", f"Temperature Controller {device_id}")
        sensors.append(TemperatureControllerTemperatureSensor(temperature_controller_coordinator, device_id))

    # Add sensors if any
    if sensors:
        async_add_entities(sensors, update_before_add=True)




class BondedDevicesDebugSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic sensor exposing bonded device discovery metadata."""

    _attr_name = "RAPT Cloud Link Bonded Devices Debug"
    _attr_unique_id = "rapt_cloud_link_bonded_devices_debug"
    _attr_icon = "mdi:bluetooth-searching"

    def __init__(self, coordinator):
        super().__init__(coordinator)

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return len(data)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        devices = []

        for device_id, device in data.items():
            telemetry = _first_telemetry_item(device)
            devices.append(
                {
                    "id": device_id,
                    "name": device.get("name"),
                    "device_type": device.get("deviceType"),
                    "temperature": _get_device_value(device, "temperature"),
                    "battery": _get_device_value(device, "battery"),
                    "connection_state": _get_device_value(device, "connectionState"),
                    "parent_device_id": _get_first_existing_value(device, PARENT_DEVICE_ID_KEYS),
                    "updated_at": _get_first_existing_value(device, UPDATED_AT_KEYS),
                    "payload_keys": sorted(device.keys()),
                    "telemetry_keys": sorted(telemetry.keys()) if telemetry else [],
                }
            )

        return {
            "ba_source": "rapt_cloud_link_bonded_devices_debug",
            "device_count": len(data),
            "device_types": sorted(
                {
                    device.get("deviceType", "unknown")
                    for device in data.values()
                    if isinstance(device, dict)
                }
            ),
            "devices": devices,
        }




class BrewZillaDebugSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic sensor exposing BrewZilla payload metadata."""

    _attr_name = "RAPT Cloud Link BrewZilla Debug"
    _attr_unique_id = "rapt_cloud_link_brewzilla_debug"
    _attr_icon = "mdi:kettle-alert"

    def __init__(self, coordinator):
        super().__init__(coordinator)

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return len(data)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        devices = []

        for device_id, device in data.items():
            telemetry = _debug_first_telemetry_item(device)
            external_candidates = _debug_pick_values(
                device,
                BREWZILLA_EXTERNAL_TEMP_CANDIDATE_KEYS,
            )
            profile_runtime = _debug_profile_runtime_snapshot(device)

            devices.append(
                {
                    "id": device_id,
                    "name": device.get("name"),
                    "device_type": device.get("deviceType"),
                    "temperature": _debug_get_value(device, "temperature"),
                    "control_device_temperature": _control_device_temperature_snapshot(device).get("selected_control_device_temperature"),
                    "root_control_device_temperature": _control_device_temperature_snapshot(device).get("root_control_device_temperature"),
                    "telemetry_control_device_temperature": _control_device_temperature_snapshot(device).get("telemetry_control_device_temperature"),
                    "selected_control_device_temperature_source": _control_device_temperature_snapshot(device).get("selected_control_device_temperature_source"),
                    "ba_value_rejected": _control_device_temperature_snapshot(device).get("ba_value_rejected"),
                    "ba_reject_reason": _control_device_temperature_snapshot(device).get("ba_reject_reason"),
                    "control_device_type": _debug_get_value(device, "controlDeviceType"),
                    "control_device_mac_address": _debug_get_value(device, "controlDeviceMacAddress"),
                    "use_internal_sensor": _debug_get_value(device, "useInternalSensor"),
                    "sensor_differential": _debug_get_value(device, "sensorDifferential"),
                    "target_temperature": _debug_get_value(device, "targetTemperature"),
                    "connection_state": _debug_get_value(device, "connectionState"),
                    "heating_enabled": _debug_get_value(device, "heatingEnabled"),
                    "pump_enabled": _debug_get_value(device, "pumpEnabled"),
                    "heating_utilisation": _debug_get_value(device, "heatingUtilisation"),
                    "pump_utilisation": _debug_get_value(device, "pumpUtilisation"),
                    "external_temperature_candidates": external_candidates,
                    "profile_runtime": profile_runtime,
                    "payload_keys": sorted(device.keys()),
                    "telemetry_keys": sorted(telemetry.keys()) if telemetry else [],
                }
            )

        return {
            "ba_source": "rapt_cloud_link_brewzilla_debug",
            "device_count": len(data),
            "devices": devices,
        }


# ---------------------
# BrewZilla
# ---------------------
class BrewZillaTemperatureSensor(BaseRaptSensor):
    """BrewZilla Temperature Sensor."""

    def __init__(self, coordinator, device_id: str):
        super().__init__(
            coordinator,
            device_id,
            model="BrewZilla",
            name_suffix="Temperature",
            unique_suffix="temperature",
            unit="°C",
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unit_of_measurement(self):
        unit = self.coordinator.config_entry.data.get(CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT)
        return "°F" if unit == "F" else "°C"

    @property
    def native_value(self):
        device = self.coordinator.data.get(self._device_id)
        if device:
            return device.get("temperature")
        return None

    @property
    def extra_state_attributes(self):
        return {
            "ba_source": "rapt_cloud_link_brewzilla_internal",
            "ba_temperature_role": "wort_or_kettle_temperature",
            "raw_device_id": self._device_id,
        }


class BrewZillaControlDeviceTemperatureSensor(BaseRaptSensor):
    """BrewZilla external/control-device temperature sensor."""

    def __init__(self, coordinator, device_id: str):
        super().__init__(
            coordinator,
            device_id,
            model="BrewZilla",
            name_suffix="Control Device Temperature",
            unique_suffix="control_device_temperature",
            unit="°C",
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unit_of_measurement(self):
        unit = self.coordinator.config_entry.data.get(CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT)
        return "°F" if unit == "F" else "°C"

    @property
    def native_value(self):
        device = self.coordinator.data.get(self._device_id)
        if not device:
            return None
        return _control_device_temperature_snapshot(device).get("selected_control_device_temperature")

    @property
    def extra_state_attributes(self):
        device = self.coordinator.data.get(self._device_id, {})
        attrs = _brewzilla_control_device_attributes(device, self._device_id)
        attrs["ba_temperature_role"] = "candidate_mash_temperature"
        attrs["ba_sensor_role"] = "brewzilla_control_device_temperature"
        return attrs


class BrewZillaBleThermometerTemperatureSensor(BaseRaptSensor):
    """Logical BLE thermometer sensor backed by BrewZilla control-device payload."""

    def __init__(self, coordinator, device_id: str):
        super().__init__(
            coordinator,
            device_id,
            model="RAPT BLE Thermometer",
            name_suffix="BLE Thermometer Temperature",
            unique_suffix="ble_thermometer_temperature",
            unit="°C",
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unit_of_measurement(self):
        unit = self.coordinator.config_entry.data.get(CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT)
        return "°F" if unit == "F" else "°C"

    @property
    def native_value(self):
        device = self.coordinator.data.get(self._device_id)
        if not device:
            return None
        return _control_device_temperature_snapshot(device).get("selected_control_device_temperature")

    @property
    def extra_state_attributes(self):
        device = self.coordinator.data.get(self._device_id, {})
        attrs = _brewzilla_control_device_attributes(device, self._device_id)
        attrs.update(
            {
                "ba_temperature_role": "mash_temperature",
                "ba_sensor_role": "ble_thermometer_temperature",
                "linked_brewzilla_id": self._device_id,
                "source_payload_key": "controlDeviceTemperature",
            }
        )
        return attrs


class BrewZillaConnectionStateSensor(BaseRaptSensor):
    """BrewZilla Connection State Sensor."""

    def __init__(self, coordinator, device_id: str):
        super().__init__(
            coordinator,
            device_id,
            model="BrewZilla",
            name_suffix="Connection",
            unique_suffix="connection_state",
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["Connected", "Disconnected"]

    @property
    def native_value(self):
        """Return the current connection state."""
        device = self.coordinator.data.get(self._device_id)
        if device:
            return device.get("connectionState", "Disconnected")
        return "Disconnected"


# ---------------------
# Hydrometer
# ---------------------
class HydrometerTemperatureSensor(BaseRaptSensor):
    """Hydrometer Temperature Sensor."""

    def __init__(self, coordinator, device_id: str):
        super().__init__(
            coordinator,
            device_id,
            model="Hydrometer",
            name_suffix="Temperature",
            unique_suffix="temperature",
            unit="°C",
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unit_of_measurement(self):
        unit = self.coordinator.config_entry.data.get(CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT)
        return "°F" if unit == "F" else "°C"

    @property
    def native_value(self):
        device = self.coordinator.data.get(self._device_id)
        if device:
            return device.get("temperature")
        return None


class HydrometerGravitySensor(BaseRaptSensor):
    """Hydrometer Gravity Sensor."""

    def __init__(self, coordinator, device_id: str):
        super().__init__(
            coordinator,
            device_id,
            model="Hydrometer",
            name_suffix="Gravity",
            unique_suffix="gravity",
            unit="SG",  # Specific Gravity
        )
        self._attr_device_class = None  # No specific device class for gravity
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the current gravity."""
        device = self.coordinator.data.get(self._device_id)
        if device:
            sg = device.get("gravity")
            while sg > 10:
                sg /= 10
            return round(sg, 3)
        return None


class HydrometerBatterySensor(BaseRaptSensor):
    """Hydrometer Battery Sensor."""

    def __init__(self, coordinator, device_id: str):
        super().__init__(
            coordinator,
            device_id,
            model="Hydrometer",
            name_suffix="Battery",
            unique_suffix="battery",
            unit="%",
        )
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the current battery."""
        device = self.coordinator.data.get(self._device_id)
        if device:
            return _rounded_device_value(device, "battery", 1)
        return None

    @property
    def extra_state_attributes(self):
        device = self.coordinator.data.get(self._device_id, {})
        return _bonded_device_attributes(device)


class HydrometerConnectionStateSensor(BaseRaptSensor):
    """Hydrometer Connection State Sensor."""

    def __init__(self, coordinator, device_id: str):
        super().__init__(
            coordinator,
            device_id,
            model="Hydrometer",
            name_suffix="Connection",
            unique_suffix="connection_state",
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["Connected", "Disconnected"]

    @property
    def native_value(self):
        """Return the current connection state."""
        device = self.coordinator.data.get(self._device_id)
        if device:
            return device.get("connectionState", "Disconnected")
        return "Disconnected"


# ---------------------
# Temperature Controller
# ---------------------
class TemperatureControllerTemperatureSensor(BaseRaptSensor):
    """TemperatureController Temperature Sensor."""

    def __init__(self, coordinator, device_id: str):
        super().__init__(
            coordinator,
            device_id,
            model="Temperature Controller",
            name_suffix="Temperature",
            unique_suffix="temperature",
            unit="°C",
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unit_of_measurement(self):
        unit = self.coordinator.config_entry.data.get(CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT)
        return "°F" if unit == "F" else "°C"

    @property
    def native_value(self):
        device = self.coordinator.data.get(self._device_id)
        if device:
            return round(device.get("temperature"), 1)
        return None


# ---------------------
# Bonded Devices
# ---------------------
class BondedDeviceTemperatureSensor(BaseRaptSensor):
    """Bonded Device Temperature Sensor."""

    def __init__(self, coordinator, device_id: str):
        device = coordinator.data.get(device_id, {})
        model = f"{device.get('deviceType', 'Bonded Device')} (Bonded Device)"
        super().__init__(
            coordinator,
            device_id,
            model=model,
            name_suffix="Temperature",
            unique_suffix="temperature",
            unit="°C",
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unit_of_measurement(self):
        unit = self.coordinator.config_entry.data.get(CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT)
        return "°F" if unit == "F" else "°C"

    @property
    def native_value(self):
        device = self.coordinator.data.get(self._device_id)
        if device:
            return _rounded_device_value(device, "temperature", 1)
        return None

    @property
    def extra_state_attributes(self):
        device = self.coordinator.data.get(self._device_id, {})
        attrs = _bonded_device_attributes(device)
        attrs["ba_temperature_role"] = "candidate_mash_temperature"
        return attrs


class BondedDeviceHumiditySensor(BaseRaptSensor):
    """Bonded Device Humidity Sensor."""

    def __init__(self, coordinator, device_id: str):
        device = coordinator.data.get(device_id, {})
        model = f"{device.get('deviceType', 'Bonded Device')} (Bonded Device)"
        super().__init__(
            coordinator,
            device_id,
            model=model,
            name_suffix="Humidity",
            unique_suffix="humidity",
            unit="%",
        )
        self._attr_device_class = SensorDeviceClass.HUMIDITY
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        device = self.coordinator.data.get(self._device_id)
        if device:
            return _rounded_device_value(device, "humidity", 1)
        return None

    @property
    def extra_state_attributes(self):
        device = self.coordinator.data.get(self._device_id, {})
        return _bonded_device_attributes(device)


class BondedDevicePressureSensor(BaseRaptSensor):
    """Bonded Device Pressure Sensor."""

    def __init__(self, coordinator, device_id: str):
        device = coordinator.data.get(device_id, {})
        model = f"{device.get('deviceType', 'Bonded Device')} (Bonded Device)"
        super().__init__(
            coordinator,
            device_id,
            model=model,
            name_suffix="Pressure",
            unique_suffix="pressure",
            unit="kPa",
        )
        self._attr_device_class = SensorDeviceClass.PRESSURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        device = self.coordinator.data.get(self._device_id)
        if device:
            return _rounded_device_value(device, "pressure", 1)
        return None

    @property
    def extra_state_attributes(self):
        device = self.coordinator.data.get(self._device_id, {})
        return _bonded_device_attributes(device)


class BondedDeviceBatterySensor(BaseRaptSensor):
    """Bonded Device Battery Sensor."""

    def __init__(self, coordinator, device_id: str):
        device = coordinator.data.get(device_id, {})
        model = f"{device.get('deviceType', 'Bonded Device')} (Bonded Device)"
        super().__init__(
            coordinator,
            device_id,
            model=model,
            name_suffix="Battery",
            unique_suffix="battery",
            unit="%",
        )
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the current battery."""
        device = self.coordinator.data.get(self._device_id)
        if device:
            return round(device.get("battery"), 1)
        return None

class BondedDeviceConnectionStateSensor(BaseRaptSensor):
    """Bonded Device Connection State Sensor."""

    def __init__(self, coordinator, device_id: str):
        device = coordinator.data.get(device_id, {})
        model = f"{device.get('deviceType', 'Bonded Device')} (Bonded Device)"
        super().__init__(
            coordinator,
            device_id,
            model=model,
            name_suffix="Connection",
            unique_suffix="connection_state",
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["Connected", "Disconnected", "Unknown"]

    @property
    def native_value(self):
        device = self.coordinator.data.get(self._device_id)
        if device:
            return _get_device_value(device, "connectionState", "Unknown")
        return "Unknown"

    @property
    def extra_state_attributes(self):
        device = self.coordinator.data.get(self._device_id, {})
        return _bonded_device_attributes(device)
