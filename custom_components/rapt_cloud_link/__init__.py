from datetime import timedelta
import logging

import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .coordinator.bonded_devices_coordinator import BondedDevicesDataUpdateCoordinator
from .coordinator.brewzilla_coordinator import BrewZillaDataUpdateCoordinator
from .coordinator.hydrometer_coordinator import HydrometerDataUpdateCoordinator
from .coordinator.temperature_controller_coordinator import TemperatureControllerDataUpdateCoordinator

from .const import DOMAIN
from .api.token_manager import TokenManager

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "switch", "number", "binary_sensor"]

SERVICE_START_BREWZILLA_PROFILE = "start_brewzilla_profile"
SERVICE_END_BREWZILLA_PROFILE = "end_brewzilla_profile"

START_PROFILE_SCHEMA = vol.Schema(
    {
        vol.Required("brewzilla_id"): cv.string,
        vol.Required("profile_id"): cv.string,
        vol.Required("name"): cv.string,
    }
)

END_PROFILE_SCHEMA = vol.Schema(
    {
        vol.Required("brewzilla_id"): cv.string,
    }
)


def _find_brewzilla_coordinator(hass, device_id: str):
    """Find the RCL BrewZilla coordinator that currently owns a device id."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if not isinstance(entry_data, dict):
            continue
        coordinator = entry_data.get("brewzilla_coordinator")
        if coordinator is not None and device_id in (coordinator.data or {}):
            return coordinator
    return None


def _register_profile_services(hass) -> None:
    """Register BrewZilla profile services once for the integration domain."""
    if not hass.services.has_service(DOMAIN, SERVICE_START_BREWZILLA_PROFILE):

        async def _async_start_profile(call):
            device_id = call.data["brewzilla_id"]
            coordinator = _find_brewzilla_coordinator(hass, device_id)
            if coordinator is None:
                raise HomeAssistantError(f"Unknown BrewZilla id: {device_id}")
            await coordinator.async_start_profile_session(
                device_id,
                call.data["profile_id"],
                call.data["name"],
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_START_BREWZILLA_PROFILE,
            _async_start_profile,
            schema=START_PROFILE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_END_BREWZILLA_PROFILE):

        async def _async_end_profile(call):
            device_id = call.data["brewzilla_id"]
            coordinator = _find_brewzilla_coordinator(hass, device_id)
            if coordinator is None:
                raise HomeAssistantError(f"Unknown BrewZilla id: {device_id}")
            await coordinator.async_end_profile_session(device_id)

        hass.services.async_register(
            DOMAIN,
            SERVICE_END_BREWZILLA_PROFILE,
            _async_end_profile,
            schema=END_PROFILE_SCHEMA,
        )


async def async_setup_entry(hass, entry):
    update_interval = timedelta(minutes=entry.options.get("poll_interval", 3))
    _LOGGER.info("Using polling interval: %s", update_interval)

    email = entry.data["email"]
    api_token = entry.data["api_token"]

    token_manager = TokenManager(hass, email, api_token, entry)

    # Coordinators
    bonded_devices_coordinator = BondedDevicesDataUpdateCoordinator(hass, token_manager, update_interval, entry)
    brewzilla_coordinator = BrewZillaDataUpdateCoordinator(hass, token_manager, update_interval, entry)
    hydrometer_coordinator = HydrometerDataUpdateCoordinator(hass, token_manager, update_interval, entry)
    temperature_controller_coordinator = TemperatureControllerDataUpdateCoordinator(hass, token_manager, update_interval, entry)

    await bonded_devices_coordinator.async_config_entry_first_refresh()
    await brewzilla_coordinator.async_config_entry_first_refresh()
    await hydrometer_coordinator.async_config_entry_first_refresh()
    await temperature_controller_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "token_manager": token_manager,
        "bonded_devices_coordinator": bonded_devices_coordinator,
        "brewzilla_coordinator": brewzilla_coordinator,
        "hydrometer_coordinator": hydrometer_coordinator,
        "temperature_controller_coordinator": temperature_controller_coordinator,
    }

    _register_profile_services(hass)

    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass, entry):
    """Unload the integration: remove platforms and clear data."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_START_BREWZILLA_PROFILE)
            hass.services.async_remove(DOMAIN, SERVICE_END_BREWZILLA_PROFILE)
        return True
    return False


async def update_listener(hass, entry):
    """Handle options update: reload the integration to apply new polling interval."""
    await hass.config_entries.async_reload(entry.entry_id)
