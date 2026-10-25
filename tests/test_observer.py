"""Targeted observer, versioned data and cross-session memory checks."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from aicosy.service import GameService
from aicosy.storage import encode


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aicosy-observer-")
        self.path = str(Path(self.temp.name)/"test.sqlite3")
        self.now = 1000.
        self.service = GameService(self.path, clock=lambda: self.now)

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def start(self, **kwargs):
        return self.service.start({"player_id": "viewer", "model_id": "script", "client_kind": "rule-script", "engine_version": 2, **kwargs})

    def act(self, observation, kind, target=None, params=None):
        payload = {"expected_version": observation["state_version"], "type": kind}
        if target is not None:
            payload["target"] = target
        if params is not None:
            payload["params"] = params
        return self.service.act(observation["session_id"], payload)

    def test_observer_tracks_progress_without_renewing_activity(self):
        self.assertEqual(self.service.list_sessions()["sessions"], [])
        obs = self.start()
        sid = obs["session_id"]
        view = self.service.observer(sid)
        self.assertEqual(view["summary"]["activity"], "active")
        self.assertEqual(view["summary"]["client_info"]["kind"], "rule-script")
        self.assertFalse(view["summary"]["client_info"]["verified"])
        before = self.service.observe(sid)
        obs = self.act(obs, "enter", "creation_1")
        view = self.service.observer(sid)
        self.assertEqual(view["summary"]["turn"], 1)
        self.assertEqual(view["summary"]["counts"]["actions"], 1)
        self.assertEqual(view["events"][-1]["action"]["type"], "enter")
        self.assertEqual(view["observation"], obs)
        self.assertNotIn("seed", view["observation"])
        self.assertTrue(view["read_only"])
        self.now += 61
        self.assertEqual(self.service.list_sessions()["sessions"][0]["activity"], "idle")
        self.assertEqual(self.service.observer(sid)["summary"]["last_activity"], 1000.)
        self.assertEqual(self.service.observe(sid), obs)
        self.service.heartbeat(sid)
        self.assertEqual(self.service.list_sessions()["recommended_session_id"], sid)
        obs = self.act(obs, "leave")
        self.assertEqual(self.service.observer(sid)["summary"]["activity"], "ended")
        self.assertNotEqual(before, obs)

    def test_recorded_v1_game_still_replays_and_is_separate(self):
        from aicosy import engine
        fixture = json.loads((Path(__file__).parent/"fixtures/v1-golden.json").read_text())
        initial = fixture["initial_state"]
        def digest(value):
            return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        events = [{"seq": 0, "at": 0, "action": None, "outcome": {"kind": "start", "cost": 0}, "before": None, "after": initial}]
        final = initial
        for seq, step in enumerate(fixture["steps"], 1):
            before = final
            final, outcome = engine.transition(before, step["action"])
            self.assertEqual(digest(final), step["state_hash"])
            self.assertEqual(digest(outcome), step["outcome_hash"])
            events.append({"seq": seq, "at": seq, "action": step["action"], "outcome": outcome, "before": before, "after": final})
        sid, player, model = initial["session_id"], initial["player_id"], initial["model_id"]
        db = self.service.store.db
        db.execute("INSERT INTO players VALUES(?,?,?)", (player, model, 0))
        db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?)", (sid, player, model, "normal", "control", encode(initial), encode(final), 0, 1, 1))
        for event in events:
            db.execute("INSERT INTO events(session_id,seq,at,action,outcome,before_state,after_state) VALUES(?,?,?,?,?,?,?)", (sid, event["seq"], event["at"], encode(event["action"]) if event["action"] else None, encode(event["outcome"]), encode(event["before"]) if event["before"] else None, encode(event["after"])))
        self.assertEqual(self.service.replay(sid)["transitions"], 17)
        self.assertEqual(self.service.observer(sid)["summary"]["engine_version"], 1)
        self.assertEqual(self.service.profile(player, engine_version=1)["sessions"], 1)
        self.assertEqual(self.service.profile(player, engine_version=2)["sessions"], 0)
        groups = self.service.compare(player)["groups"]
        self.assertEqual(sum(g["metrics"]["sessions_total"] for g in groups if g["engine_version"] == 1), 1)
        self.assertEqual(sum(g["metrics"]["sessions_total"] for g in groups if g["engine_version"] == 2), 0)
        self.service.reset_profile(player, engine_version=1)
        self.assertEqual(self.service.profile(player, engine_version=1)["sessions"], 0)
        self.assertTrue(self.service.replay(sid)["verified"])

    def test_memory_keeps_latest_six_in_chronological_order(self):
        ids = []
        for count in (5, 2):
            obs = self.start(memory=False)
            obs = self.act(obs, "enter", "resonance_1")
            for index in range(count):
                self.now += 1
                obs = self.act(obs, "perform", "resonance_1", {"period": 2+index%5, "phase": 0})
                ids.append(obs["observation"]["saved_experiences"][-1]["id"])
            self.now += 1
            self.act(obs, "leave")
        inherited = self.start()["observation"]["saved_experiences"]
        self.assertEqual([entry["id"] for entry in inherited], ids[-6:])

    def test_research_debug_uses_stored_rules_version(self):
        from aicosy.legacy_engine import create_state
        state = create_state(session_id="legacy-research", player_id="legacy", model_id="old", mode="research")
        db = self.service.store.db
        db.execute("INSERT INTO players VALUES(?,?,?)", ("legacy", "old", 0))
        db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?)", ("legacy-research", "legacy", "old", "research", "control", encode(state), encode(state), 0, 0, None))
        debug = self.service.debug("legacy-research")
        self.assertEqual(debug["rules"]["rules_version"], 1)
        current = self.start(mode="research")
        self.assertEqual(self.service.debug(current["session_id"])["rules"]["rules_version"], 2)

    def test_cross_session_memory_is_own_model_and_research_partition(self):
        obs = self.start()
        obs = self.act(obs, "enter", "resonance_1")
        # Exact run schema is advertised by the authoritative engine.
        descriptors = obs["available_actions"]
        run = next(a for a in descriptors if a["type"] in ("perform", "run"))
        from clients.common import action_from_descriptor
        import random
        action = action_from_descriptor(run, random.Random(1))
        obs = self.service.act(obs["session_id"], {"expected_version": obs["state_version"], **action})
        saved = obs["observation"]["saved_experiences"]
        self.assertTrue(saved)
        saved_id = saved[-1]["id"]
        obs = self.act(obs, "leave")
        normal = self.start()
        self.assertIn(saved_id, [s["id"] for s in normal["observation"]["saved_experiences"]])
        self.assertEqual(self.start(mode="research")["observation"]["saved_experiences"], [])
        self.assertEqual(self.start(memory=False)["observation"]["saved_experiences"], [])
        other = self.service.start({"player_id": "separate-model", "model_id": "model-two"})
        self.assertEqual(other["observation"]["saved_experiences"], [])
        self.assertTrue(self.service.replay(normal["session_id"])["verified"])
        self.service.close()
        self.service = GameService(self.path, clock=lambda: self.now)
        self.assertEqual(self.service.observe(normal["session_id"]), normal)
