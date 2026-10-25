"""Small V4 runtime/SQLite/observer checks. No browser or remote model."""
from pathlib import Path
import tempfile
import unittest

from aicosy.service import GameService


class ContinuousServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aicosy-v4-service-")
        self.path = str(Path(self.temp.name) / "state.sqlite3")
        self.now = 1000.
        self.service = GameService(self.path, clock=lambda: self.now)

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def start(self, **kwargs):
        return self.service.start({"player_id": "continuous-check", "model_id": "test-script", "client_kind": "rule-script", **kwargs})

    def act(self, obs, kind, target=None, **params):
        action = {"expected_version": obs["state_version"], "type": kind}
        if target is not None:
            action["target"] = target
        if params:
            action["params"] = params
        return self.service.act(obs["session_id"], action)

    def advertised(self, obs, kind):
        return next(a for a in obs["available_actions"] if a["type"] == kind)

    def do(self, obs, kind):
        a = self.advertised(obs, kind)
        return self.act(obs, kind, a.get("target"))

    def test_checkpoint_survives_restart_and_advances_absolute_window(self):
        obs = self.act(self.start(), "perform", "resonance_1", release_tick=8)
        self.assertEqual(obs["engine_version"], 4)
        sid = obs["session_id"]
        first_run = obs["observation"]["current_run"]["run_id"]
        self.service.close()
        self.service = GameService(self.path, clock=lambda: self.now)
        self.assertEqual(self.service.observe(sid), obs)
        obs = self.do(obs, "extend")
        self.assertEqual(obs["observation"]["current_run"]["run_id"], first_run)
        self.assertEqual(obs["observation"]["current_run"]["tick"], 48)
        frames = obs["observation"]["performance"]["frames"]
        self.assertEqual([f["tick"] for f in frames], list(range(24, 48)))
        self.now += 61
        detail = self.service.observer(sid)
        self.assertEqual(detail["observation"], obs)
        self.assertEqual(detail["summary"]["activity"], "idle")
        self.assertEqual(detail["summary"]["counts"]["extensions"], 1)
        self.assertEqual(self.service.observe(sid), obs)
        self.assertTrue(self.service.replay(sid)["verified"])

    def test_replay_display_keeps_current_runtime_and_counts_separate(self):
        obs = self.act(self.start(), "perform", "resonance_1", release_tick=8)
        first_saved = obs["observation"]["saved_experiences"][0]["id"]
        obs = self.do(obs, "extend")
        live = obs["observation"]["current_run"]
        self.assertTrue(live["cycle"])
        obs = self.act(obs, "replay", first_saved)
        self.assertEqual(obs["observation"]["current_run"], live)
        self.assertEqual(obs["observation"]["performance"]["frames"][-1]["tick"], 23)
        obs = self.do(obs, "hold")
        self.assertEqual(obs["observation"]["current_run"]["tick"], 72)
        obs = self.do(obs, "tap")
        self.assertNotEqual(obs["observation"]["current_run"]["run_id"], live["run_id"])
        obs = self.act(obs, "leave")
        result = self.service.result(obs["session_id"])["summary"]
        self.assertEqual(result["paid_replays"], 1)
        self.assertEqual(result["extensions"], 1)
        self.assertEqual(result["known_cycle_holds"], 1)
        self.assertEqual(result["pulse_interventions"], 1)
        profile = self.service.profile("continuous-check")
        self.assertEqual(profile["engine_version"], 4)
        self.assertEqual(profile["experiences"]["resonance"]["holds"], 1)

    def test_settled_echo_can_be_tapped_but_not_extended_empty(self):
        obs = self.act(self.start(), "select_piece", "echo")
        obs = self.act(obs, "perform", "resonance_1", release_tick=8)
        types = {a["type"] for a in obs["available_actions"]}
        self.assertNotIn("extend", types)
        self.assertNotIn("hold", types)
        self.assertIn("tap", types)
        obs = self.do(obs, "tap")
        self.assertTrue(obs["observation"]["performance"]["frames"])
        self.assertTrue(self.service.replay(obs["session_id"])["verified"])

    def test_v3_library_and_profiles_do_not_mix_with_v4(self):
        old = self.start(engine_version=3, memory=False)
        old = self.act(old, "enter", "resonance_1")
        old = self.act(old, "perform", "resonance_1", release_tick=8)
        self.act(old, "leave")
        current = self.start()
        self.assertEqual(current["observation"]["saved_experiences"], [])
        current = self.act(current, "perform", "resonance_1", release_tick=8)
        saved_id = current["observation"]["saved_experiences"][-1]["id"]
        self.act(current, "leave")
        inherited = self.start()["observation"]["saved_experiences"]
        self.assertIn(saved_id, [x["id"] for x in inherited])
        self.assertTrue(all(x["engine_version"] == 4 for x in inherited))
        self.assertEqual(self.start(mode="research")["observation"]["saved_experiences"], [])
        self.service.reset_profile("continuous-check")
        self.assertEqual(self.service.profile("continuous-check")["sessions"], 0)
        self.assertGreater(self.service.profile("continuous-check", engine_version=3)["sessions"], 0)


if __name__ == "__main__":
    unittest.main()
