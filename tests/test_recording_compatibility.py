"""Compact historical goldens, independent of unpublished local evidence."""
import hashlib
import json
from pathlib import Path
import unittest

from porn import engine


class RecordingCompatibilityTests(unittest.TestCase):
    def check_recording(self, version):
        fixture = json.loads((Path(__file__).parent / f"fixtures/v{version}-golden.json").read_text())
        state = fixture["initial_state"]
        def digest(value):
            raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            return hashlib.sha256(raw.encode()).hexdigest()
        for index, step in enumerate(fixture["steps"], 1):
            state, outcome = engine.transition(state, step["action"])
            self.assertEqual(digest(state), step["state_hash"], (version, index, "state"))
            self.assertEqual(digest(outcome), step["outcome_hash"], (version, index, "outcome"))
        self.assertEqual(state["state"], "ended")

    def test_v2_recording_12_transitions_unchanged(self):
        self.check_recording(2)

    def test_v3_recording_8_transitions_unchanged(self):
        self.check_recording(3)
