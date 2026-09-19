from datetime import timedelta

from .base_coordinator import BaseRaptCoordinator
from ..api.brewzilla_api import BrewZillaAPI
from homeassistant.helpers.update_coordinator import UpdateFailed


ACTIVE_PROFILE_POLL_INTERVAL = timedelta(seconds=60)


def _has_active_profile(devices):
    """Recognize a concrete session, not a possibly transient step ID."""
    if not isinstance(devices, list):
        return False
    for device in devices:
        if not isinstance(device, dict):
            continue
        session = device.get("activeProfileSession")
        if (
            isinstance(session, dict)
            and session
            and (device.get("activeProfileId") or session.get("profileId"))
        ):
            return True
    return False


class BrewZillaDataUpdateCoordinator(BaseRaptCoordinator):
    def __init__(self, hass, token_manager, update_interval, entry):
        super().__init__(hass, token_manager, update_interval, entry, name="BrewZilla API")
        self._idle_update_interval = update_interval

    async def _async_update_data(self):
        try:
            api = await self._get_token_and_api(BrewZillaAPI)
            devices = await api.get_brewzillas()
            # BA rejects RAPT telemetry older than 90 seconds. Poll only the
            # BrewZilla coordinator at <=60s while a profile is running;
            # restore the configured interval when its session disappears.
            # A failed poll leaves the previous cadence in place. BA's age
            # gate remains authoritative if the cloud does not respond.
            self.update_interval = (
                min(self._idle_update_interval, ACTIVE_PROFILE_POLL_INTERVAL)
                if _has_active_profile(devices)
                else self._idle_update_interval
            )
            return {device["id"]: device for device in devices if "id" in device}
        except Exception as err:
            raise UpdateFailed(f"Failed to fetch BrewZilla data: {err}") from err

    async def async_start_profile_session(self, device_id: str, profile_id: str, name: str):
        """Start a RAPT profile on a BrewZilla and refresh live state."""
        api = await self._get_token_and_api(BrewZillaAPI)
        result = await api.start_profile_session(device_id, profile_id, name)
        await self.async_request_refresh()
        return result

    async def async_end_profile_session(self, device_id: str):
        """End the active RAPT profile on a BrewZilla and refresh live state."""
        api = await self._get_token_and_api(BrewZillaAPI)
        result = await api.end_profile_session(device_id)
        await self.async_request_refresh()
        return result
