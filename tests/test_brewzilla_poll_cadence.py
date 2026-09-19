"""Exercise the real coordinator cadence logic without Home Assistant or RAPT API calls."""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path
import unittest

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "custom_components/rapt_cloud_link/coordinator/brewzilla_coordinator.py"
)


def coordinator_logic():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    interval = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "ACTIVE_PROFILE_POLL_INTERVAL" for target in node.targets)
    )
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_has_active_profile"
    )
    cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BrewZillaDataUpdateCoordinator"
    )
    update = next(
        node for node in cls.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_update_data"
    )
    namespace = {"timedelta": timedelta, "BrewZillaAPI": object, "UpdateFailed": RuntimeError}
    exec(compile(ast.Module(body=[interval, helper, update], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class StubAPI:
    def __init__(self, devices):
        self.devices = devices

    async def get_brewzillas(self):
        return self.devices


class StubCoordinator:
    def __init__(self, devices, interval=timedelta(minutes=3)):
        self.api = StubAPI(devices)
        self._idle_update_interval = interval
        self.update_interval = interval

    async def _get_token_and_api(self, _api_class):
        return self.api


class BrewZillaCadenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_active_profile_polls_within_ba_freshness_gate(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator([{
            "id": "brewzilla-1", "activeProfileId": "profile-1",
            "activeProfileSession": {"id": "session-1"},
            "activeProfileStepId": "step-1",
        }])
        result = await logic["_async_update_data"](coordinator)
        self.assertIn("brewzilla-1", result)
        self.assertEqual(coordinator.update_interval, timedelta(seconds=60))
        self.assertLess(coordinator.update_interval, timedelta(seconds=90))

    async def test_step_handoff_keeps_fast_polling(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator([{
            "id": "brewzilla-1", "activeProfileId": "profile-1",
            "activeProfileSession": {"id": "session-1"},
            "activeProfileStepId": None,
        }])
        await logic["_async_update_data"](coordinator)
        self.assertEqual(coordinator.update_interval, timedelta(seconds=60))

    async def test_inactive_profile_restores_configured_cadence(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator([{"id": "brewzilla-1", "activeProfileId": None}])
        coordinator.update_interval = timedelta(seconds=60)
        await logic["_async_update_data"](coordinator)
        self.assertEqual(coordinator.update_interval, timedelta(minutes=3))

    async def test_faster_operator_setting_is_preserved(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator([{
            "id": "brewzilla-1", "activeProfileId": "profile-1",
            "activeProfileSession": {"id": "session-1"},
        }], interval=timedelta(seconds=30))
        await logic["_async_update_data"](coordinator)
        self.assertEqual(coordinator.update_interval, timedelta(seconds=30))


if __name__ == "__main__":
    unittest.main()
