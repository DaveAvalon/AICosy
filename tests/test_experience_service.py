"""Focused V3 persistence, observer and version boundary checks; no GUI."""
from pathlib import Path
import tempfile
import unittest

from aicosy.errors import GameError
from aicosy.service import GameService


class ExperienceServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aicosy-v3-service-")
        self.path = str(Path(self.temp.name) / "state.sqlite3")
        self.now = 1000.
        self.service = GameService(self.path, clock=lambda: self.now)

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def start(self, **kwargs):
        return self.service.start({"player_id": "v3-check", "model_id": "test-script", "client_kind": "rule-script", "engine_version": 3, **kwargs})

    def act(self, obs, kind, target=None, **params):
        action = {"expected_version": obs["state_version"], "type": kind}
        if target is not None:
            action["target"] = target
        if params:
            action["params"] = params
        return self.service.act(obs["session_id"], action)

    def test_midperformance_restart_and_observer_are_real(self):
        obs = self.act(self.start(), "enter", "resonance_1")
        self.assertEqual(obs["engine_version"], 3)
        obs = self.act(obs, "begin", "resonance_1")
        self.assertEqual(obs["observation"]["experience"]["tick"], 4)
        self.assertEqual(obs["observation"]["experience"]["reservoirs"]["n1"], 2)
        before = obs
        with self.assertRaises(GameError):
            self.act(obs, "tune", "creation_1", node="n3", delay=1, phase=0)
        self.assertEqual(self.service.observe(obs["session_id"]), before)
        self.service.close()
        self.service = GameService(self.path, clock=lambda: self.now)
        self.assertEqual(self.service.observe(obs["session_id"]), before)
        obs = self.act(obs, "wait", "resonance_1")
        self.assertEqual(obs["observation"]["experience"]["reservoirs"]["n1"], 4)
        self.now += 61
        detail = self.service.observer(obs["session_id"])
        self.assertTrue(detail["read_only"])
        self.assertEqual(detail["observation"], obs)
        self.assertEqual(detail["summary"]["activity"], "idle")
        self.assertEqual(detail["summary"]["last_activity"], 1000.)
        obs = self.act(obs, "release", "resonance_1")
        for _ in range(3):
            obs = self.act(obs, "continue", "resonance_1")
        self.assertTrue(obs["observation"]["saved_experiences"])
        self.assertEqual(obs["resources"]["energy"], 22)
        self.assertTrue(self.service.replay(obs["session_id"])["verified"])

    def test_repeat_fork_and_familiar_control_have_separate_counts(self):
        obs = self.act(self.start(), "enter", "resonance_1")
        obs = self.act(obs, "perform", "resonance_1", release_tick=8)
        saved = obs["observation"]["saved_experiences"][-1]
        machine = obs["observation"]["machine"]
        for _ in range(3):
            obs = self.act(obs, "replay", saved["id"])
            self.assertEqual(obs["observation"]["performance"]["trace_hash"], saved["trace_hash"])
        self.assertEqual(obs["observation"]["machine"], machine)
        obs = self.act(obs, "fork", saved["id"], release_tick=4)
        self.assertNotEqual(obs["observation"]["performance"]["trace_hash"], saved["trace_hash"])
        obs = self.act(obs, "reperform", saved["id"])
        obs = self.act(obs, "stop", "resonance_1")
        obs = self.act(obs, "leave")
        result = self.service.result(obs["session_id"])["summary"]
        self.assertEqual(result["paid_replays"], 3)
        self.assertEqual(result["forks"], 1)
        self.assertEqual(result["familiar_reperformances"], 1)
        counts = self.service.observer(obs["session_id"])["summary"]["counts"]
        self.assertEqual(counts["reperformances"], 1)
        profile = self.service.profile("v3-check", engine_version=3)
        self.assertEqual(profile["engine_version"], 3)
        self.assertEqual(profile["experiences"]["resonance"]["reperformances"], 1)

    def test_versions_keep_rules_memory_and_profiles_separate(self):
        saved_ids = {}
        for version, params in ((2, {"period": 4, "phase": 0}), (3, {"release_tick": 8})):
            obs = self.act(self.start(engine_version=version, memory=False), "enter", "resonance_1")
            obs = self.act(obs, "perform", "resonance_1", **params)
            saved_ids[version] = obs["observation"]["saved_experiences"][-1]["id"]
            self.act(obs, "leave")
            self.assertEqual(self.service.rules(version)["rules_version"], version)
        for version in (2, 3):
            obs = self.start(engine_version=version)
            self.assertEqual([s["id"] for s in obs["observation"]["saved_experiences"]], [saved_ids[version]])
            self.act(obs, "leave")
        self.service.reset_profile("v3-check", engine_version=3)
        self.assertEqual(self.service.profile("v3-check", engine_version=3)["sessions"], 0)
        self.assertGreater(self.service.profile("v3-check", engine_version=2)["sessions"], 0)
        for invalid in (1, 5, True):
            with self.assertRaises(GameError):
                self.start(engine_version=invalid)


if __name__ == "__main__":
    unittest.main()
