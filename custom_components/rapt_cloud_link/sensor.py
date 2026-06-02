import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from .const import BONDED_DEVICE_TYPES, CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT, DOMAIN
from .base import BaseRaptSensor

_LOGGER = logging.getLogger(__name__)


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
    """Return the first telemetry-like item from a device payload."""
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

    # BrewZilla
    for device_id, device in brewzilla_coordinator.data.items():
        # name = device.get("name", f"BrewZilla {device_id}")
        sensors.append(BrewZillaTemperatureSensor(brewzilla_coordinator, device_id))
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

