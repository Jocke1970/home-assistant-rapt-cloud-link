"""Read-only RAPT profile timing and ingredient alert data contracts."""
from __future__ import annotations
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "custom_components/rapt_cloud_link/binary_sensor.py"


def funcs():
    tree = ast.parse(FILE.read_text(encoding="utf-8"))
    wanted = {"_compact_alerts", "_profile_step_progress", "_profile_context"}
    nodes = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name in wanted]
    assert {x.name for x in nodes} == wanted
    scope = {"Any": object, "MAX_PROFILE_STEPS": 32, "MAX_PROFILE_ALERTS": 16}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(FILE), "exec"), scope)
    return scope


class ProfileTimerAlertsTest(unittest.TestCase):
    def test_bounded_alerts_and_current_step_identity(self):
        scope = funcs()
        rows = [
            {"id": str(i), "alertText": "Hop " + str(i), "trigger": "Duration",
             "length": i*60, "temperature": None}
            for i in range(25)
        ]
        device = {
            "activeProfileId": "p", "activeProfileStepId": "boil",
            "activeProfileSession": {
                "id": "run", "profileId": "p",
                "currentProfileTime": 185.25,
                "remainingProfileTime": 99.5,
                "profile": {"steps": [
                    {"id": "mash", "name": "Mash Rest", "order": 0},
                    {"id": "boil", "name": "Boil", "order": 1, "endType": "Duration",
                     "length": 3600, "temperature": 100, "alerts": rows},
                ]},
            },
        }
        ctx = scope["_profile_context"](device)
        self.assertEqual(ctx["step_name"], "Boil")
        self.assertEqual(ctx["step_alerts"][0]["text"], "Hop 0")
        self.assertEqual(len(ctx["step_alerts"]), 16)
        self.assertEqual(ctx["step_alerts"][1]["length_raw"], 60)
        self.assertEqual(ctx["profile_current_time_raw"], 185.25)
        self.assertEqual(ctx["profile_remaining_time_raw"], 99.5)
        self.assertEqual(len(ctx["profile_steps"][-1]["alerts"]), 16)
        self.assertNotIn("due_seconds", ctx["step_alerts"][0])

    def test_progress_payload_not_converted_to_seconds_or_percentage(self):
        fn = funcs()["_profile_step_progress"]
        self.assertEqual(fn({"telemetry": {"profileStepProgress": 123456}}), 123456)
        self.assertEqual(fn({"telemetry": [{"profileStepProgress": 9}]}), 9)
        self.assertIsNone(fn({"telemetry": {}}))
        self.assertIsNone(fn({"telemetry": None}))

    def test_no_alerts_or_session_stays_empty(self):
        scope = funcs()
        c = scope["_profile_context"]({"activeProfileStepId": None})
        self.assertEqual(c["step_alerts"], [])
        self.assertIsNone(c["profile_current_time_raw"])
