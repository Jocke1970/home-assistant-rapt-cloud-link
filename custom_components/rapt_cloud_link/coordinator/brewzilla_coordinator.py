from .base_coordinator import BaseRaptCoordinator
from ..api.brewzilla_api import BrewZillaAPI
from homeassistant.helpers.update_coordinator import UpdateFailed


class BrewZillaDataUpdateCoordinator(BaseRaptCoordinator):
    def __init__(self, hass, token_manager, update_interval, entry):
        super().__init__(hass, token_manager, update_interval, entry, name="BrewZilla API")

    async def _async_update_data(self):
        try:
            api = await self._get_token_and_api(BrewZillaAPI)
            devices = await api.get_brewzillas()
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
