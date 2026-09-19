"""Read-only regression tests for the BA/RCL release contract.

Extract the pure profile normalizer so CI needs no live HA, RAPT credentials,
or hardware. These tests do NOT establish physical command safety.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "rapt_cloud_link"


def normalizer():
    source = (PKG / "binary_sensor.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_profile_context")
    namespace = {"Any": Any, "MAX_PROFILE_STEPS": 32}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "binary_sensor.py", "exec"), namespace)
    return namespace["_profile_context"]


def device():
    return {
        "activeProfileId": "profile-1",
        "activeProfileStepId": "step-1",
        "activeProfileSession": {
            "id": "session-1", "profileId": "profile-1",
            "startDate": "2026-09-19T20:39:12+00:00",
            "profile": {"id": "profile-1", "name": "Julol (Test)", "steps": [
                {"id": "step-1", "name": "Heatstrike", "order": 0,
                 "temperature": 40.0, "controlType": "Target"},
                {"id": "step-2", "name": "Mash-in", "order": 1,
                 "temperature": 38.0, "controlType": "Target"},
            ]},
        },
    }


class ProfileContractTest(unittest.TestCase):
    def test_live_rcl_payload_yields_ba_contract(self):
        result = normalizer()(device())
        self.assertTrue(result["active"])
        self.assertTrue(result["contract_complete"])
        self.assertEqual(result["profile_session_id"], "session-1")
        self.assertEqual(result["step_id"], "step-1")
        self.assertEqual(result["step_name"], "Heatstrike")
        self.assertEqual(result["step_target_temperature"], 40.0)
        self.assertEqual(result["next_step_name"], "Mash-in")
        self.assertEqual(result["step_count"], 2)

    def test_step_handoff_does_not_look_like_stop(self):
        payload = device()
        payload["activeProfileStepId"] = None
        result = normalizer()(payload)
        self.assertTrue(result["active"])
        self.assertFalse(result["contract_complete"])

    def test_session_missing_denies_complete_contract(self):
        payload = device()
        payload["activeProfileSession"].pop("id")
        result = normalizer()(payload)
        self.assertTrue(result["active"])
        self.assertFalse(result["contract_complete"])

    def test_unknown_step_denies_complete_contract(self):
        payload = device()
        payload["activeProfileStepId"] = "step-not-in-profile"
        result = normalizer()(payload)
        self.assertTrue(result["active"])
        self.assertFalse(result["contract_complete"])

    def test_missing_step_target_denies_complete_contract(self):
        payload = device()
        payload["activeProfileSession"]["profile"]["steps"][0].pop("temperature")
        result = normalizer()(payload)
        self.assertTrue(result["active"])
        self.assertFalse(result["contract_complete"])

    def test_confirmed_stop_is_inactive(self):
        payload = device()
        payload.update(activeProfileId=None, activeProfileStepId=None, activeProfileSession=None)
        result = normalizer()(payload)
        self.assertFalse(result["active"])
        self.assertFalse(result["contract_complete"])

    def test_platform_and_ba_marker_exposed(self):
        initialization = (PKG / "__init__.py").read_text(encoding="utf-8")
        entity = (PKG / "binary_sensor.py").read_text(encoding="utf-8")
        self.assertIn('"binary_sensor"', initialization)
        self.assertIn('"rapt_cloud_link_brewzilla_profile_runtime"', entity)
        self.assertIn('"profile_contract_complete"', entity)
        self.assertIn('"profile_session_id"', entity)
        self.assertIn('"step_target_temperature"', entity)

    def test_prerelease_version(self):
        manifest = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["domain"], "rapt_cloud_link")
        self.assertEqual(manifest["version"], "0.5.0-beta.1")
        self.assertTrue((PKG / "services.yaml").exists())


if __name__ == "__main__":
    unittest.main()
