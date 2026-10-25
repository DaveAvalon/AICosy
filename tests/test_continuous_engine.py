from copy import deepcopy
import unittest

from aicosy import engine_v4
from aicosy.dynamics_v4 import advance, apply_control, initial_checkpoint, piece, remaining_activity
from aicosy.errors import GameError


class CheckpointDynamicsTests(unittest.TestCase):
    def test_split_advance_preserves_inflight_queue_and_matches_one_pass(self):
        machine, inputs = piece("orbit")
        initial = initial_checkpoint(machine, inputs)
        first = advance(machine, initial, 24, [{"tick": 4, "type": "release"}])
        self.assertFalse(any(first["frames"][-1]["values"].values()))
        self.assertTrue(first["checkpoint"]["pending"])
        second = advance(machine, first["checkpoint"], 24)
        full = advance(machine, initial, 48, [{"tick": 4, "type": "release"}])
        self.assertEqual(first["frames"] + second["frames"], full["frames"])
        self.assertEqual(first["events"] + second["events"], full["events"])
        self.assertEqual(second["checkpoint"], full["checkpoint"])
        self.assertEqual(initial["next_tick"], 0)
        self.assertEqual(initial["pending"], [])

    def test_cycle_requires_complete_non_silent_state(self):
        orbit, inputs = piece("orbit")
        result = advance(orbit, initial_checkpoint(orbit, inputs), 24, [{"tick": 4, "type": "release"}])
        self.assertEqual(result["checkpoint"]["cycle"]["period"], 16)
        self.assertEqual(result["checkpoint"]["cycle"]["detected_at"], 21)
        echo, inputs = piece("echo")
        settled = advance(echo, initial_checkpoint(echo, inputs), 24, [{"tick": 4, "type": "release"}])
        self.assertIsNone(settled["checkpoint"]["cycle"])
        self.assertFalse(remaining_activity(settled["checkpoint"]))
        held = advance(orbit, initial_checkpoint(orbit, {"pulse_ticks": [0], "phase": 0}), 24)
        self.assertEqual(held["checkpoint"]["reservoirs"]["n1"], 1)
        self.assertIsNone(held["checkpoint"]["cycle"])

    def test_tap_clears_old_certificate_and_preserves_actual_checkpoint(self):
        machine, inputs = piece("orbit")
        original = advance(machine, initial_checkpoint(machine, inputs), 24, [{"tick": 4, "type": "release"}])["checkpoint"]
        tapped, events = apply_control(machine, original, {"tick": 24, "type": "tap"})
        self.assertIsNone(tapped["cycle"])
        self.assertEqual(tapped["history"], [])
        self.assertEqual(tapped["pending"], original["pending"])
        self.assertEqual(tapped["reservoirs"], original["reservoirs"])
        self.assertEqual(tapped["remaining_inputs"], [{"tick": 24, "value": 1, "kind": "tap"}])
        self.assertIsNotNone(original["cycle"])


class ContinuousEngineTests(unittest.TestCase):
    def fresh(self, **kwargs):
        return engine_v4.create_state(session_id="continuous-test", player_id="script", model_id="rule", **kwargs)

    def act(self, state, kind, target=None, params=None):
        action = {"type": kind}
        if target is not None:
            action["target"] = target
        if params is not None:
            action["params"] = params
        return engine_v4.transition(state, action)[0]

    def perform(self, piece_id="orbit", release=4):
        state = self.fresh()
        if piece_id != "orbit":
            state = self.act(state, "select_piece", piece_id)
        return self.act(state, "perform", "resonance_1", {"release_tick": release})

    def descriptor(self, state, kind):
        return next(a for a in engine_v4.available_actions(state) if a["type"] == kind)

    def test_presets_known_hold_and_windowed_absolute_frames(self):
        state = self.perform()
        visible = engine_v4.observe(state)["observation"]
        self.assertEqual(visible["piece_id"], "orbit")
        self.assertEqual({p["id"] for p in visible["pieces"]}, {"echo", "orbit", "weave"})
        self.assertEqual(visible["experience"]["cycle"]["period"], 16)
        self.assertNotIn("extend", {a["type"] for a in engine_v4.available_actions(state)})
        ident = state["world"]["current_run"]["run_id"]
        before = deepcopy(state["world"]["current_run"]["frames"])
        state = self.act(state, "hold", ident)
        run = state["world"]["current_run"]
        self.assertEqual(run["run_id"], ident)
        self.assertEqual(run["frames"][:24], before)
        self.assertEqual(state["resources"]["energy"], 20)
        self.assertEqual(state["last_outcome"]["continuation_kind"], "known_cycle_continuation")
        public = engine_v4.observe(state)["observation"]["performance"]
        self.assertEqual(len(public["frames"]), 24)
        self.assertEqual([f["tick"] for f in public["frames"]], list(range(24, 48)))
        self.assertNotIn("checkpoint", public)

    def test_settled_has_no_paid_empty_extension_but_can_be_tapped(self):
        state = self.perform("echo", 8)
        kinds = {a["type"] for a in engine_v4.available_actions(state)}
        self.assertEqual(engine_v4.observe(state)["observation"]["experience"]["state"], "settled")
        self.assertNotIn("extend", kinds)
        self.assertNotIn("hold", kinds)
        self.assertIn("tap", kinds)
        previous = deepcopy(state["world"]["current_run"])
        state = self.act(state, "tap", previous["run_id"])
        run = state["world"]["current_run"]
        self.assertNotEqual(run["run_id"], previous["run_id"])
        self.assertEqual(run["parent_run_id"], previous["run_id"])
        self.assertEqual(run["parent_tick"], 24)
        self.assertEqual(run["branch_id"], run["run_id"])
        self.assertEqual(run["frames"][:24], previous["frames"])
        self.assertTrue(any(e["kind"] == "tap" and e["tick"] == 24 for e in run["events"]))
        self.assertNotIn("exact_repeat", state["last_outcome"])
        self.assertFalse(engine_v4._forkable(engine_v4.export_library(state)[-1]))
        state = self.act(state, "leave")
        self.assertEqual(engine_v4.observe(state)["observation"]["experience"]["state"], "settled")

    def test_closed_boundary_release_is_free_and_does_not_advance(self):
        state = self.act(self.fresh(), "begin", "resonance_1")
        for _ in range(5):
            state = self.act(state, "wait", "resonance_1")
        self.assertEqual(state["resources"]["energy"], 22)
        self.assertEqual(engine_v4.observe(state)["observation"]["experience"]["state"], "waiting_release")
        self.assertNotIn("extend", {a["type"] for a in engine_v4.available_actions(state)})
        state = self.act(state, "release", "resonance_1")
        self.assertEqual(state["world"]["current_run"]["duration"], 24)
        self.assertEqual(state["last_outcome"]["advanced_ticks"], 0)
        self.assertEqual(state["resources"]["energy"], 22)
        state = self.act(state, "extend", state["world"]["current_run"]["run_id"])
        self.assertEqual(state["world"]["current_run"]["duration"], 48)
        self.assertEqual(state["resources"]["energy"], 20)
        loaded = self.fresh(library=engine_v4.export_library(state))
        self.assertTrue(loaded["world"]["saved_experiences"])

    def test_replay_preserves_current_run_and_library_is_immutable(self):
        state = self.perform()
        old = deepcopy(engine_v4.export_library(state)[0])
        state = self.act(state, "hold", state["world"]["current_run"]["run_id"])
        checkpoint = deepcopy(state["world"]["current_run"])
        state = self.act(state, "replay", old["id"])
        visible = engine_v4.observe(state)["observation"]
        self.assertEqual(state["world"]["current_run"], checkpoint)
        self.assertEqual(visible["experience"]["tick"], 24)
        self.assertEqual(visible["current_run"]["tick"], 48)
        self.assertEqual(visible["performance"]["trace_hash"], old["trace_hash"])
        self.assertEqual(engine_v4.export_library(state)[0], old)
        loaded = self.fresh(library=engine_v4.export_library(state))
        self.assertEqual(len(loaded["world"]["saved_experiences"]), 2)
        broken = engine_v4.export_library(state)
        broken[0]["checkpoint"]["pending"] = []
        with self.assertRaises(GameError):
            self.fresh(library=broken)

    def test_cap_stop_and_invalid_actions_do_not_invent_activity(self):
        state = self.perform()
        for _ in range(3):
            state = self.act(state, "hold", state["world"]["current_run"]["run_id"])
        visible = engine_v4.observe(state)["observation"]
        self.assertEqual(visible["experience"]["state"], "limit")
        self.assertEqual(len(state["world"]["current_run"]["frames"]), 96)
        self.assertFalse({"extend", "hold", "tap"} & {a["type"] for a in engine_v4.available_actions(state)})
        before = deepcopy(state)
        with self.assertRaises(GameError):
            self.act(state, "hold", state["world"]["current_run"]["run_id"])
        self.assertEqual(state, before)
        state = self.act(state, "stop", "resonance_1")
        self.assertEqual(state["resources"]["energy"], before["resources"]["energy"])
        self.assertEqual(state["last_outcome"]["kind"], "stop")

    def test_continuation_and_stop_keep_captured_mode_after_area_switch(self):
        state = self.perform()
        captured = deepcopy(state["world"]["current_run"]["machine"])
        state = self.act(state, "enter", "creation_1")
        state = self.act(state, "tune", "creation_1", {"node": "n3", "delay": 1, "phase": 0})
        working = deepcopy(state["world"]["machine"])
        state = self.act(state, "hold", state["world"]["current_run"]["run_id"])
        self.assertEqual(state["last_outcome"]["mode"], "resonance")
        self.assertEqual(state["world"]["current_run"]["machine"], captured)
        self.assertEqual(state["world"]["machine"], working)
        state = self.act(state, "stop", "creation_1")
        self.assertEqual(state["last_outcome"]["mode"], "resonance")


if __name__ == "__main__":
    unittest.main()
