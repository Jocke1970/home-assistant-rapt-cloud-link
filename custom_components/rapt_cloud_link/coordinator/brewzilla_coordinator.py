"""BrewZilla cloud coordinator; never infer STOP from a failed poll."""

import logging
from datetime import datetime, timedelta, timezone

from .base_coordinator import BaseRaptCoordinator
from ..api.brewzilla_api import BrewZillaAPI
from homeassistant.helpers.update_coordinator import UpdateFailed

_LOGGER = logging.getLogger(__name__)
BREWZILLA_IDLE_POLL_INTERVAL = timedelta(seconds=30)
ACTIVE_PROFILE_POLL_INTERVAL = timedelta(seconds=60)


def _has_active_profile(devices):
    """Recognize a concrete session, not a possibly transient step ID."""
    if not isinstance(devices, list):
        return False
    for device in devices:
        if not isinstance(device, dict):
            continue
        session = device.get("activeProfileSession")
        if isinstance(session, dict) and session and (device.get("activeProfileId") or session.get("profileId")):
            return True
    return False


def _clean_profile_stop(device):
    """Only a connected BrewZilla with ALL profile markers absent can count."""
    if str(device.get("connectionState") or "").casefold() != "connected":
        return False
    if any(device.get(key) for key in ("activeProfileId", "activeProfileStepId", "activeProfileSession")):
        return False
    telemetry = device.get("telemetry")
    if isinstance(telemetry, dict):
        if telemetry.get("profileId") or telemetry.get("profileStepId"):
            return False
    elif isinstance(telemetry, list):
        if any(isinstance(row, dict) and (row.get("profileId") or row.get("profileStepId")) for row in telemetry):
            return False
    return True


class BrewZillaDataUpdateCoordinator(BaseRaptCoordinator):
    def __init__(self, hass, token_manager, update_interval, entry):
        super().__init__(hass, token_manager, update_interval, entry, name="BrewZilla API")
        # BrewZilla carries the control-device/BLE thermometer telemetry used
        # by BrewAssistant. Keep this coordinator responsive even when no RAPT
        # profile is active, without changing Pill/other coordinator cadence.
        self._idle_update_interval = min(update_interval, BREWZILLA_IDLE_POLL_INTERVAL)
        self.update_interval = self._idle_update_interval
        # These are *observations*, never commands. A restart has no STOP proof.
        self._last_active_session = {}
        self._clean_stop_polls = {}
        # Passive step transitions; never used to advance RAPT or actuate.
        self._step_observations = {}

    def _annotate_profile_handoff(self, devices):
        observed = set()
        for device in devices:
            if not isinstance(device, dict) or not device.get("id"):
                continue
            key = device["id"]
            observed.add(key)
            session = device.get("activeProfileSession")
            active = bool(isinstance(session, dict) and session and
                          (device.get("activeProfileId") or session.get("profileId")))
            device["_baProfileStopConfirmed"] = False
            device["_baStoppedSessionId"] = None
            # A successful cloud poll can report the *same* profile step for
            # minutes. Its HA last_updated then stays old despite healthy
            # polling. Publish a real per-poll observation timestamp instead.
            # Only a connected active profile is a current observation;
            # missing/offline is never evidence of STOP or a fresh session.
            device["_baProfileObservedAt"] = (
                datetime.now(timezone.utc).isoformat()
                if active and str(device.get("connectionState") or "").casefold() == "connected"
                else None
            )
            # No timer anchor from initial observation, reconnect or
            # changed session. A consecutive poll seeing a new step only
            # proves an approximate transition instant (polling uncertainty).
            device["_baStepTransitionObservedAt"] = None
            connected = device["_baProfileObservedAt"] is not None
            session_id = session.get("id") if active else None
            step_id = device.get("activeProfileStepId") if active else None
            previous = self._step_observations.get(key)
            if connected and session_id and step_id:
                now = datetime.now(timezone.utc)
                evidence = (previous is not None
                    and previous["session"] == session_id
                    and previous["step"] != step_id
                    and (now - previous["last"]).total_seconds() <= 90)
                transition_at = (
                    now.isoformat() if evidence
                    else previous.get("transition_at") if previous
                    and previous["session"] == session_id and previous["step"] == step_id
                    else None
                )
                self._step_observations[key] = {
                    "session": session_id, "step": step_id,
                    "last": now, "transition_at": transition_at,
                }
                device["_baStepTransitionObservedAt"] = transition_at
            else:
                self._step_observations.pop(key, None)
            if active:
                session_id = session.get("id")
                # A new anonymous active session must invalidate earlier STOP
                # identity. It is unsafe to attest STOP for the *old* run.
                if session_id:
                    self._last_active_session[key] = session_id
                else:
                    self._last_active_session.pop(key, None)
                self._clean_stop_polls[key] = 0
                continue
            if key not in self._last_active_session or not _clean_profile_stop(device):
                self._clean_stop_polls[key] = 0
                continue
            count = self._clean_stop_polls.get(key, 0) + 1
            self._clean_stop_polls[key] = count
            if count >= 2:
                device["_baProfileStopConfirmed"] = True
                device["_baStoppedSessionId"] = self._last_active_session[key]

        # A successful response omitting a previously observed device interrupts
        # its STOP proof, even if the next response reports it as connected.
        for key in self._last_active_session.keys() - observed:
            self._clean_stop_polls[key] = 0
            self._step_observations.pop(key, None)

    async def _async_update_data(self):
        try:
            api = await self._get_token_and_api(BrewZillaAPI)
            devices = await api.get_brewzillas()
            if not isinstance(devices, list):
                raise ValueError("BrewZilla API payload is not a device list")
            # Duplicate IDs in one response are NOT separate observations.
            # Reject the entire ambiguous snapshot before advancing STOP proof.
            device_ids = [device["id"] for device in devices
                          if isinstance(device, dict) and device.get("id")]
            if len(device_ids) != len(set(device_ids)):
                raise ValueError("BrewZilla API payload contains duplicate device IDs")
            self._annotate_profile_handoff(devices)
            awaiting_stop = any(
                isinstance(device, dict)
                and device.get("id") in self._last_active_session
                and not device.get("_baProfileStopConfirmed")
                for device in devices
            )
            # Only BrewZilla polls faster during an active or unverified session;
            # Pill and other coordinators keep their configured intervals.
            self.update_interval = (
                min(self._idle_update_interval, ACTIVE_PROFILE_POLL_INTERVAL)
                if _has_active_profile(devices) or awaiting_stop else self._idle_update_interval
            )
            return {device["id"]: device for device in devices if isinstance(device, dict) and "id" in device}
        except Exception as err:
            # Two STOP observations must be consecutive successful polls.
            # Preserve the last live session identity, but discard partial proof
            # after a timeout, malformed payload or other failed update.
            for key in self._last_active_session:
                self._clean_stop_polls[key] = 0
            # Do not project timer anchors through a failed or ambiguous poll.
            self._step_observations.clear()
            raise UpdateFailed(f"Failed to fetch BrewZilla data: {err}") from err

    async def _refresh_profile_status_after_command(self, operation: str):
        """Best-effort readback, independent of an already returned command result."""
        try:
            await self.async_request_refresh()
        except Exception:
            # The command may already have been accepted. A read failure is NOT
            # command failure and must never trigger an automatic retry or STOP.
            _LOGGER.warning(
                "BrewZilla %s command returned; subsequent status refresh failed",
                operation,
                exc_info=True,
            )

    def _schedule_profile_status_refresh(self, operation: str):
        """Schedule best-effort readback; never overwrite the API command result."""
        refresh = self._refresh_profile_status_after_command(operation)
        try:
            self.hass.async_create_task(
                refresh,
                f"rapt_cloud_link_{operation}_status_refresh",
            )
        except Exception:
            # Scheduling is readback infrastructure, not part of command success.
            # Close a coroutine that could not be scheduled to avoid a warning.
            try:
                refresh.close()
            except RuntimeError:
                pass  # It may already have started before the scheduler failed.
            _LOGGER.warning(
                "BrewZilla %s command returned; status refresh could not be scheduled",
                operation,
                exc_info=True,
            )

    async def async_start_profile_session(self, device_id: str, profile_id: str, name: str):
        """Send start once; return its API response without waiting for readback."""
        api = await self._get_token_and_api(BrewZillaAPI)
        result = await api.start_profile_session(device_id, profile_id, name)
        self._schedule_profile_status_refresh("start_profile")
        return result

    async def async_end_profile_session(self, device_id: str):
        """Send end once; return its API response without waiting for readback."""
        api = await self._get_token_and_api(BrewZillaAPI)
        result = await api.end_profile_session(device_id)
        self._schedule_profile_status_refresh("end_profile")
        return result
