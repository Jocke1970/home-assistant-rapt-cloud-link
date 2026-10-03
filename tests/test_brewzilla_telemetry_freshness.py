"""Regression tests for BrewZilla telemetry freshness diagnostics."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1]
          / "custom_components/rapt_cloud_link/sensor.py")


def helpers():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    wanted = {
        "_debug_first_telemetry_item",
        "_debug_telemetry_freshness_snapshot",
        "_age_seconds",
    }
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    namespace = {"datetime": datetime, "timezone": timezone}
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"),
        namespace,
    )
    return namespace


class BrewZillaTelemetryFreshnessTest(unittest.TestCase):
    def test_exposes_root_and_telemetry_freshness_metadata(self):
        device = {
            "telemetryFrequency": 30,
            "lastActivityTime": "2026-10-03T08:01:02Z",
            "modifiedOn": "2026-10-03T08:00:00Z",
            "createdOn": "2026-01-01T00:00:00Z",
            "telemetry": {
                "createdOn": "2026-10-03T08:00:42Z",
                "controlDeviceTemperature": 45.0,
            },
        }

        result = helpers()["_debug_telemetry_freshness_snapshot"](device)

        self.assertEqual(result["telemetry_frequency"], 30)
        self.assertEqual(result["last_activity_time"], "2026-10-03T08:01:02Z")
        self.assertEqual(result["root_modified_on"], "2026-10-03T08:00:00Z")
        self.assertEqual(result["root_created_on"], "2026-01-01T00:00:00Z")
        self.assertEqual(result["telemetry_created_on"], "2026-10-03T08:00:42Z")

    def test_age_seconds_handles_iso_timestamp(self):
        now = datetime(2026, 10, 3, 8, 1, 12, tzinfo=timezone.utc)
        result = helpers()["_age_seconds"]("2026-10-03T08:00:42Z", now)
        self.assertEqual(result, 30.0)

    def test_age_seconds_never_goes_negative(self):
        now = datetime(2026, 10, 3, 8, 0, 0, tzinfo=timezone.utc)
        result = helpers()["_age_seconds"]("2026-10-03T08:00:10Z", now)
        self.assertEqual(result, 0.0)

    def test_age_seconds_rejects_invalid_timestamp(self):
        result = helpers()["_age_seconds"]("not-a-timestamp")
        self.assertIsNone(result)

    def test_sensor_contracts_are_present(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("BrewZillaTelemetryAgeSensor", source)
        self.assertIn("unique_suffix=\"telemetry_age\"", source)
        self.assertIn("rapt_cloud_link_brewzilla_telemetry_age", source)
        self.assertIn("BrewZillaBleDataAgeSensor", source)
        self.assertIn("unique_suffix=\"ble_data_age\"", source)
        self.assertIn("rapt_cloud_link_brewzilla_ble_data_age", source)

    def test_missing_telemetry_is_safe(self):
        result = helpers()["_debug_telemetry_freshness_snapshot"]({})
        self.assertIsNone(result["telemetry_frequency"])
        self.assertIsNone(result["last_activity_time"])
        self.assertIsNone(result["telemetry_created_on"])


if __name__ == "__main__":
    unittest.main()
