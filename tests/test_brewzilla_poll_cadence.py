"""Exercise actual coordinator functions without HA, credentials or hardware."""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path
import types
import unittest

SOURCE = (Path(__file__).resolve().parents[1]
          / "custom_components/rapt_cloud_link/coordinator/brewzilla_coordinator.py")


def coordinator_logic():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    wanted = {"_has_active_profile", "_clean_profile_stop"}
    helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    interval = next(node for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "ACTIVE_PROFILE_POLL_INTERVAL"
                            for target in node.targets))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "BrewZillaDataUpdateCoordinator")
    methods = [node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name in {"_annotate_profile_handoff", "_async_update_data"}]
    namespace = {"timedelta": timedelta, "BrewZillaAPI": object, "UpdateFailed": RuntimeError}
    exec(compile(ast.Module(body=[interval, *helpers, *methods], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class StubAPI:
    def __init__(self, devices):
        self.devices = devices

    async def get_brewzillas(self):
        if isinstance(self.devices, Exception):
            raise self.devices
        return self.devices


class StubCoordinator:
    def __init__(self, logic, devices, interval=timedelta(minutes=3)):
        self.api = StubAPI(devices)
        self._idle_update_interval = interval
        self.update_interval = interval
        self._last_active_session = {}
        self._clean_stop_polls = {}
        self._annotate_profile_handoff = types.MethodType(logic["_annotate_profile_handoff"], self)

    async def _get_token_and_api(self, _api_class):
        return self.api


def active():
    return {"id": "bz", "connectionState": "Connected", "activeProfileId": "p",
            "activeProfileStepId": "s", "activeProfileSession": {"id": "run", "profileId": "p"},
            "telemetry": {"profileId": "p", "profileStepId": "s"}}


def inactive():
    return {"id": "bz", "connectionState": "Connected", "activeProfileId": None,
            "activeProfileStepId": None, "activeProfileSession": None, "telemetry": {}}


class BrewZillaCadenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_active_profile_and_step_handoff_poll_within_freshness_gate(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator(logic, [active()])
        result = await logic["_async_update_data"](coordinator)
        self.assertIn("bz", result)
        self.assertEqual(coordinator.update_interval, timedelta(seconds=60))
        coordinator.api.devices = [{**active(), "activeProfileStepId": None}]
        await logic["_async_update_data"](coordinator)
        self.assertEqual(coordinator.update_interval, timedelta(seconds=60))

    async def test_two_clean_connected_polls_required_to_attest_stop(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator(logic, [active()])
        await logic["_async_update_data"](coordinator)
        coordinator.api.devices = [inactive()]
        first = await logic["_async_update_data"](coordinator)
        self.assertIs(first["bz"]["_baProfileStopConfirmed"], False)
        self.assertEqual(coordinator.update_interval, timedelta(seconds=60))
        coordinator.api.devices = [inactive()]
        second = await logic["_async_update_data"](coordinator)
        self.assertIs(second["bz"]["_baProfileStopConfirmed"], True)
        self.assertEqual(second["bz"]["_baStoppedSessionId"], "run")
        self.assertEqual(coordinator.update_interval, timedelta(minutes=3))

    async def test_missing_or_disconnected_payload_cannot_confirm_stop(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator(logic, [active()])
        await logic["_async_update_data"](coordinator)
        for payload in ({**inactive(), "connectionState": "Disconnected"},
                        {**inactive(), "activeProfileStepId": "old"},
                        {**inactive(), "telemetry": {"profileId": "old"}}):
            coordinator.api.devices = [payload]
            result = await logic["_async_update_data"](coordinator)
            self.assertFalse(result["bz"]["_baProfileStopConfirmed"])
        coordinator.api.devices = [inactive()]
        self.assertFalse((await logic["_async_update_data"](coordinator))["bz"]["_baProfileStopConfirmed"])

    async def test_failed_poll_keeps_last_session_without_stop_confirmation(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator(logic, [active()])
        await logic["_async_update_data"](coordinator)
        coordinator.api.devices = TimeoutError("RAPT unavailable")
        with self.assertRaises(RuntimeError):
            await logic["_async_update_data"](coordinator)
        self.assertEqual(coordinator._last_active_session["bz"], "run")
        self.assertEqual(coordinator._clean_stop_polls.get("bz"), 0)
        self.assertEqual(coordinator.update_interval, timedelta(seconds=60))

    async def test_anonymous_new_session_cannot_attest_old_run_stop(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator(logic, [active()])
        await logic["_async_update_data"](coordinator)
        coordinator.api.devices = [{**active(), "activeProfileSession": {"profileId": "p-new"},
                                    "activeProfileId": "p-new"}]
        await logic["_async_update_data"](coordinator)
        self.assertNotIn("bz", coordinator._last_active_session)
        for _ in range(3):
            coordinator.api.devices = [inactive()]
            result = await logic["_async_update_data"](coordinator)
            self.assertFalse(result["bz"]["_baProfileStopConfirmed"])

    async def test_cold_start_off_never_attests_previous_run(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator(logic, [inactive()])
        for _ in range(3):
            coordinator.api.devices = [inactive()]
            self.assertFalse((await logic["_async_update_data"](coordinator))["bz"]["_baProfileStopConfirmed"])
        self.assertEqual(coordinator.update_interval, timedelta(minutes=3))

    async def test_faster_operator_setting_preserved(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator(logic, [active()], interval=timedelta(seconds=30))
        await logic["_async_update_data"](coordinator)
        self.assertEqual(coordinator.update_interval, timedelta(seconds=30))


if __name__ == "__main__":
    unittest.main()
