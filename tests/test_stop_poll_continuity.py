"""No-hardware regressions for uninterrupted, session-bound STOP observations."""

import unittest

from test_brewzilla_poll_cadence import StubCoordinator, active, coordinator_logic, inactive


class StopPollContinuityTest(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_between_clean_polls_resets_stop_proof(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator(logic, [active()])
        await logic["_async_update_data"](coordinator)

        coordinator.api.devices = [inactive()]
        first = await logic["_async_update_data"](coordinator)
        self.assertFalse(first["bz"]["_baProfileStopConfirmed"])
        self.assertEqual(coordinator._clean_stop_polls["bz"], 1)

        coordinator.api.devices = TimeoutError("cloud unavailable")
        with self.assertRaises(RuntimeError):
            await logic["_async_update_data"](coordinator)
        self.assertEqual(coordinator._last_active_session["bz"], "run")
        self.assertEqual(coordinator._clean_stop_polls["bz"], 0)

        coordinator.api.devices = [inactive()]
        resumed = await logic["_async_update_data"](coordinator)
        self.assertFalse(resumed["bz"]["_baProfileStopConfirmed"])
        confirmed = await logic["_async_update_data"](coordinator)
        self.assertTrue(confirmed["bz"]["_baProfileStopConfirmed"])
        self.assertEqual(confirmed["bz"]["_baStoppedSessionId"], "run")

    async def test_missing_device_breaks_stop_observation_sequence(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator(logic, [active()])
        await logic["_async_update_data"](coordinator)

        coordinator.api.devices = [inactive()]
        await logic["_async_update_data"](coordinator)
        self.assertEqual(coordinator._clean_stop_polls["bz"], 1)

        coordinator.api.devices = []
        self.assertEqual(await logic["_async_update_data"](coordinator), {})
        self.assertEqual(coordinator._clean_stop_polls["bz"], 0)

        coordinator.api.devices = [inactive()]
        resumed = await logic["_async_update_data"](coordinator)
        self.assertFalse(resumed["bz"]["_baProfileStopConfirmed"])
        confirmed = await logic["_async_update_data"](coordinator)
        self.assertTrue(confirmed["bz"]["_baProfileStopConfirmed"])

    async def test_invalid_payload_breaks_stop_observation_sequence(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator(logic, [active()])
        await logic["_async_update_data"](coordinator)
        coordinator.api.devices = [inactive()]
        await logic["_async_update_data"](coordinator)

        coordinator.api.devices = {"unexpected": "payload"}
        with self.assertRaises(RuntimeError):
            await logic["_async_update_data"](coordinator)
        self.assertEqual(coordinator._clean_stop_polls["bz"], 0)

        coordinator.api.devices = [inactive()]
        self.assertFalse((await logic["_async_update_data"](coordinator))["bz"]["_baProfileStopConfirmed"])

    async def test_duplicate_device_rows_cannot_count_as_separate_polls(self):
        logic = coordinator_logic()
        coordinator = StubCoordinator(logic, [active()])
        await logic["_async_update_data"](coordinator)

        coordinator.api.devices = [inactive(), inactive()]
        with self.assertRaises(RuntimeError):
            await logic["_async_update_data"](coordinator)
        self.assertEqual(coordinator._last_active_session["bz"], "run")
        self.assertEqual(coordinator._clean_stop_polls["bz"], 0)

        coordinator.api.devices = [inactive()]
        self.assertFalse((await logic["_async_update_data"](coordinator))["bz"]["_baProfileStopConfirmed"])
        self.assertTrue((await logic["_async_update_data"](coordinator))["bz"]["_baProfileStopConfirmed"])


if __name__ == "__main__":
    unittest.main()
