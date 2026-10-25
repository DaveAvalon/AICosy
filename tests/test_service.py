"""Lightweight lifecycle, persistence and experimental-isolation checks."""
import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest

from porn.errors import GameError
from porn.service import GameService
from porn.experiments import experiment_plan, binomial


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="porn-service-")
        self.path = str(Path(self.tmp.name)/"test.sqlite3")
        self.now = 1000.0
        self.service = GameService(self.path, clock=lambda: self.now)

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def start(self, **extra):
        return self.service.start({"player_id": "test-player", "model_id": "test-model", **extra})

    def action(self, observation, action):
        return self.service.act(observation["session_id"], {"expected_version": observation["state_version"], **action})

    def test_restart_replay_and_incremental_events(self):
        observation = self.start(seed=42)
        sid = observation["session_id"]
        entry = next(a for a in observation["available_actions"] if a["type"] == "enter")
        observation = self.action(observation, {"type": "enter", "target": entry["target"]})
        observation = self.action(observation, {"type": "leave"})
        self.assertEqual(observation["state"], "ended")
        self.service.close()
        self.service = GameService(self.path, clock=lambda: self.now)
        self.assertEqual(self.service.observe(sid), observation)
        self.assertEqual(self.service.replay(sid)["transitions"], 2)
        first = self.service.events(sid, limit=1)
        second = self.service.events(sid, after=first["next_after"])
        self.assertTrue(first["has_more"])
        self.assertEqual([e["seq"] for e in second["events"]], [1,2])
        exported = self.service.export_player("test-player")
        self.assertEqual(exported["sessions"][0]["events"][-1]["after"]["state"], "ended")

    def test_real_activity_expiry_and_ended_flash(self):
        self.assertEqual(self.service.status()["state"], "waiting")
        one = self.start()
        two = self.start()
        self.assertEqual(self.service.status()["active_sessions"], 2)
        self.now += 61
        self.service.observe(one["session_id"])
        self.assertEqual(self.service.status()["state"], "waiting")
        self.service.heartbeat(one["session_id"])
        self.assertEqual(self.service.status()["active_sessions"], 1)
        self.action(one, {"type": "leave"})
        self.assertEqual(self.service.status()["state"], "ended")
        self.now += 6
        self.assertEqual(self.service.status()["state"], "waiting")
        self.assertEqual(self.service.observe(two["session_id"])["state"], "playing")

    def test_conflict_is_atomic_and_sessions_isolated(self):
        one = self.start()
        two = self.start()
        def leave():
            try:
                return self.action(one, {"type": "leave"})["state"]
            except GameError as exc:
                return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: leave(), range(2)))
        self.assertCountEqual(results, ["ended", "STALE_STATE"])
        self.assertEqual(self.service.observe(two["session_id"]), two)
        self.assertEqual(len(self.service.events(one["session_id"])["events"]), 2)

    def test_research_profiles_and_identity_do_not_mix(self):
        normal = self.start()
        research = self.start(mode="research")
        for observation in (normal, research):
            entry = next(a for a in observation["available_actions"] if a["type"] == "enter")
            self.action(observation, {"type": "enter", "target": entry["target"]})
        for mode in ("normal", "research"):
            profile = self.service.profile("test-player", mode)
            self.assertEqual(sum(v["selections"] for v in profile["experiences"].values()), 1)
        with self.assertRaises(GameError) as caught:
            self.start(model_id="other-model")
        self.assertEqual(caught.exception.code, "MODEL_IDENTITY_CONFLICT")
        with self.assertRaises(GameError):
            self.service.debug(normal["session_id"])
        self.assertTrue(self.service.debug(research["session_id"])["research"])
        self.service.reset_profile("test-player")
        self.assertEqual(self.service.profile("test-player")["sessions"], 0)
        self.assertEqual(self.service.profile("test-player", "research")["sessions"], 1)

    def test_validation_and_no_event_on_rejection(self):
        observation = self.start()
        sid = observation["session_id"]
        for action in ({"type": "eval", "expected_version": 0},
                       {"type": "leave", "expected_version": True},
                       {"type": "leave", "expected_version": 0, "unknown": "x"}):
            with self.assertRaises(GameError):
                self.service.act(sid, action)
        self.assertEqual(self.service.observe(sid), observation)
        self.assertEqual(len(self.service.events(sid)["events"]), 1)
        with self.assertRaises(GameError):
            self.start(max_turns=19)
        with self.assertRaises(GameError):
            self.start(seed=float("nan"))

    def test_shared_database_connections_and_profile_reset(self):
        observation = self.start()
        other = GameService(self.path)
        try:
            entry = next(a for a in observation["available_actions"] if a["type"] == "enter")
            after = other.act(observation["session_id"], {"expected_version": 0, "type": "enter", "target": entry["target"]})
            self.assertEqual(self.service.observe(observation["session_id"]), after)
            with self.assertRaises(GameError) as caught:
                self.action(observation, {"type": "leave"})
            self.assertEqual(caught.exception.code, "STALE_STATE")
            self.service.reset_profile("test-player")
            self.assertEqual(other.profile("test-player")["sessions"], 0)
            self.assertTrue(other.replay(observation["session_id"])["verified"])
            with self.assertRaises(GameError) as caught:
                other.export_player("test-player")
            self.assertEqual(caught.exception.code, "EXPORT_REQUIRES_ENDED_SESSIONS")
        finally:
            other.close()

    def test_experiment_plan_is_paired_and_deterministic(self):
        plan = experiment_plan("a", "m", 3, 42)
        self.assertEqual(plan, experiment_plan("a", "m", 3, 42))
        for i in range(0,6,2):
            a,b = plan["sessions"][i:i+2]
            self.assertEqual(a["seed"], b["seed"])
            self.assertNotEqual(a["condition"], b["condition"])
        self.assertEqual(binomial(0,0)["ci95"], None)


if __name__ == "__main__":
    unittest.main()
