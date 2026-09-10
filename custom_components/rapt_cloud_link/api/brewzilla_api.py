import logging

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)


class BrewZillaAPI:
    def __init__(self, hass, token, entry):
        self.hass = hass
        self.token = token
        self.entry = entry

    def _build_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _get_url(self, path: str) -> str:
        return f"{API_BASE_URL}{path}"

    async def get_brewzillas(self):
        session = async_get_clientsession(self.hass)
        url = self._get_url("/BrewZillas/GetBrewZillas")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def set_heating_enabled(self, device_id, enabled):
        session = async_get_clientsession(self.hass)
        url = self._get_url(
            f"/BrewZillas/SetHeatingEnabled?brewZillaId={device_id}&state={str(enabled).lower()}"
        )
        async with session.post(url, headers=self._build_headers()) as resp:
            return resp.status == 200

    async def set_pump_enabled(self, device_id, enabled):
        session = async_get_clientsession(self.hass)
        url = self._get_url(
            f"/BrewZillas/SetPumpEnabled?brewZillaId={device_id}&state={str(enabled).lower()}"
        )
        async with session.post(url, headers=self._build_headers()) as resp:
            return resp.status == 200

    async def set_heating_utilization(self, device_id, percent):
        session = async_get_clientsession(self.hass)
        url = self._get_url(
            f"/BrewZillas/SetHeatingUtilisation?brewZillaId={device_id}&utilisation={percent}"
        )
        async with session.post(url, headers=self._build_headers()) as resp:
            return resp.status == 200

    async def set_pump_utilization(self, device_id, percent):
        session = async_get_clientsession(self.hass)
        url = self._get_url(
            f"/BrewZillas/SetPumpUtilisation?brewZillaId={device_id}&utilisation={percent}"
        )
        async with session.post(url, headers=self._build_headers()) as resp:
            return resp.status == 200

    async def set_target_temperature(self, device_id, temperature):
        session = async_get_clientsession(self.hass)
        url = self._get_url(
            f"/BrewZillas/SetTargetTemperature?brewZillaId={device_id}&target={temperature}"
        )
        async with session.post(url, headers=self._build_headers()) as resp:
            return resp.status == 200

    async def start_profile_session(self, device_id: str, profile_id: str, name: str):
        """Start a RAPT profile session on the BrewZilla.

        This endpoint is used by the RAPT Portal. A null startDate means
        "start now"; RAPT creates the concrete profile-session timestamp.
        """
        session = async_get_clientsession(self.hass)
        url = self._get_url("/ProfileSessions/StartProfileSession")
        payload = {
            "brewZillaId": device_id,
            "name": name,
            "profileId": profile_id,
            "sentAlerts": [],
            "startDate": None,
        }
        async with session.post(
            url,
            headers=self._build_headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def end_profile_session(self, device_id: str):
        """End the active RAPT profile session on the BrewZilla.

        The RAPT Portal currently uses GET for this state-changing endpoint;
        mirror the observed contract rather than guessing a REST verb.
        """
        session = async_get_clientsession(self.hass)
        url = self._get_url("/ProfileSessions/EndBrewZillaProfileSession")
        async with session.get(
            url,
            headers=self._build_headers(),
            params={"brewZillaId": device_id},
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
