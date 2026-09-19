"""No-hardware tests: command replies and cloud status readback are separate."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
import types
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "custom_components" /
          "rapt_cloud_link" / "coordinator" / "brewzilla_coordinator.py")


def command_methods():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "BrewZillaDataUpdateCoordinator")
    names = {"_refresh_profile_status_after_command", "_schedule_profile_status_refresh",
             "async_start_profile_session", "async_end_profile_session"}
    methods = [node for node in cls.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    assert {node.name for node in methods} == names, "Command/refresh methods missing"
    namespace = {"BrewZillaAPI": object, "_LOGGER": logging.getLogger(__name__)}
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class FakeHass:
    def __init__(self):
        self.pending = []

    def async_create_task(self, coroutine, name):
        self.pending.append((coroutine, name))

    async def run_pending(self):
        pending, self.pending = self.pending, []
        for coroutine, _ in pending:
            await coroutine


class FakeAPI:
    def __init__(self):
        self.calls = []
        self.failure = None

    async def start_profile_session(self, device_id, profile_id, name):
        self.calls.append(("start", device_id, profile_id, name))
        if self.failure:
            raise self.failure
        return {"accepted": "start"}

    async def end_profile_session(self, device_id):
        self.calls.append(("end", device_id))
        if self.failure:
            raise self.failure
        return {"accepted": "end"}


class FakeCoordinator:
    def __init__(self, methods):
        self.hass = FakeHass()
        self.api = FakeAPI()
        self.refresh_calls = 0
        self.refresh_failure = None
        for name in ("_refresh_profile_status_after_command", "_schedule_profile_status_refresh"):
            setattr(self, name, types.MethodType(methods[name], self))

    async def _get_token_and_api(self, _api_class):
        return self.api

    async def async_request_refresh(self):
        self.refresh_calls += 1
        if self.refresh_failure:
            raise self.refresh_failure


class ProfileCommandRefreshTest(unittest.IsolatedAsyncioTestCase):
    async def test_end_result_returns_before_failed_status_refresh(self):
        methods = command_methods()
        coordinator = FakeCoordinator(methods)
        coordinator.refresh_failure = TimeoutError("status cloud read failed")

        result = await methods["async_end_profile_session"](coordinator, "brewzilla-1")
        self.assertEqual(result, {"accepted": "end"})
        self.assertEqual(coordinator.api.calls, [("end", "brewzilla-1")])
        self.assertEqual(coordinator.refresh_calls, 0)
        self.assertEqual(len(coordinator.hass.pending), 1)

        # Readback is isolated: failure cannot turn the accepted command into an
        # error or send another end command.
        with self.assertLogs(level="WARNING") as logs:
            await coordinator.hass.run_pending()
        self.assertIn("status refresh failed", " ".join(logs.output))
        self.assertEqual(coordinator.api.calls, [("end", "brewzilla-1")])

    async def test_start_result_returns_before_failed_status_refresh(self):
        methods = command_methods()
        coordinator = FakeCoordinator(methods)
        coordinator.refresh_failure = TimeoutError("status cloud read failed")
        result = await methods["async_start_profile_session"](
            coordinator, "brewzilla-1", "profile-1", "Test"
        )
        self.assertEqual(result, {"accepted": "start"})
        self.assertEqual(coordinator.refresh_calls, 0)
        with self.assertLogs(level="WARNING"):
            await coordinator.hass.run_pending()
        self.assertEqual(coordinator.api.calls,
                         [("start", "brewzilla-1", "profile-1", "Test")])

    async def test_failed_command_has_no_refresh_and_no_retry(self):
        methods = command_methods()
        coordinator = FakeCoordinator(methods)
        coordinator.api.failure = TimeoutError("command response unknown")
        with self.assertRaises(TimeoutError):
            await methods["async_end_profile_session"](coordinator, "brewzilla-1")
        self.assertEqual(coordinator.api.calls, [("end", "brewzilla-1")])
        self.assertEqual(coordinator.hass.pending, [])
        self.assertEqual(coordinator.refresh_calls, 0)

    async def test_successful_readback_still_scheduled(self):
        methods = command_methods()
        coordinator = FakeCoordinator(methods)
        result = await methods["async_end_profile_session"](coordinator, "brewzilla-1")
        self.assertEqual(result, {"accepted": "end"})
        await coordinator.hass.run_pending()
        self.assertEqual(coordinator.refresh_calls, 1)
        self.assertEqual(coordinator.api.calls, [("end", "brewzilla-1")])

    async def test_scheduler_failure_cannot_mask_start_or_end_result(self):
        methods = command_methods()
        for operation in ("start", "end"):
            with self.subTest(operation=operation):
                coordinator = FakeCoordinator(methods)

                def unavailable_scheduler(_coroutine, _name):
                    raise RuntimeError("HA task scheduler unavailable")

                coordinator.hass.async_create_task = unavailable_scheduler
                with self.assertLogs(level="WARNING") as logs:
                    if operation == "start":
                        result = await methods["async_start_profile_session"](
                            coordinator, "brewzilla-1", "profile-1", "Test"
                        )
                    else:
                        result = await methods["async_end_profile_session"](
                            coordinator, "brewzilla-1"
                        )
                self.assertEqual(result, {"accepted": operation})
                self.assertEqual(len(coordinator.api.calls), 1)
                self.assertEqual(coordinator.hass.pending, [])
                self.assertEqual(coordinator.refresh_calls, 0)
                self.assertIn("could not be scheduled", " ".join(logs.output))


if __name__ == "__main__":
    unittest.main()
