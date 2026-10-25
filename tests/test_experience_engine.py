from copy import deepcopy
import unittest

from aicosy import engine_v3
from aicosy.dynamics_v3 import DEFAULT_INPUTS, initial_machine, simulate
from aicosy.errors import GameError


class ReservoirDynamicsTests(unittest.TestCase):
    def test_known_dual_path_response_and_prefix_storage(self):
        machine = initial_machine()
        first = simulate(machine, ticks=4, running=True)
        second = simulate(machine, ticks=8, running=True)
        result = simulate(machine, control_script=[{"tick": 8, "type": "release"}])
        self.assertEqual(first["experience"]["reservoirs"], {"n1": 2})
        self.assertEqual(second["experience"]["reservoirs"], {"n1": 4})
        self.assertEqual(result["summary"]["output_sequence"], [{"tick": 11, "value": 4}, {"tick": 12, "value": 1}, {"tick": 13, "value": -4}, {"tick": 14, "value": -1}])
        self.assertFalse(result["experience"]["remaining_activity"])
        self.assertEqual(result["frames"][:8], second["frames"])
        self.assertFalse(result["frames"][7]["gate_open"])
        self.assertTrue(result["frames"][8]["gate_open"])

    def test_overflow_and_horizon_residue_are_real(self):
        inputs = {"pulse_ticks": list(range(24)), "phase": 0}
        result = simulate(initial_machine(), inputs)
        self.assertEqual(result["experience"]["reservoirs"]["n1"], 8)
        self.assertTrue(any(e["kind"] == "overflow" for e in result["experience"]["events"]))
        self.assertTrue(result["experience"]["remaining_activity"])
        self.assertTrue(result["experience"]["completed"])

    def test_controls_change_only_future_and_validate_bounds(self):
        early = simulate(initial_machine(), control_script=[{"tick": 4, "type": "release"}])
        late = simulate(initial_machine(), control_script=[{"tick": 8, "type": "release"}])
        self.assertEqual(early["frames"][:4], late["frames"][:4])
        self.assertNotEqual(early["trace_hash"], late["trace_hash"])
        for controls in ([{"tick": True, "type": "release"}], [{"tick": 24, "type": "release"}], [{"tick": 4, "type": "open"}]):
            with self.assertRaises(ValueError):
                simulate(initial_machine(), control_script=controls)
        with self.assertRaises(ValueError):
            simulate(initial_machine(), ticks=4)


class ExperienceEngineTests(unittest.TestCase):
    def fresh(self, **kwargs):
        return engine_v3.create_state(session_id="test-v3", player_id="test", model_id="script", **kwargs)

    def act(self, state, kind, target=None, params=None):
        action = {"type": kind}
        if target is not None:
            action["target"] = target
        if params is not None:
            action["params"] = params
        return engine_v3.transition(state, action)[0]

    def full_interactive(self):
        state = self.act(self.fresh(), "enter", "resonance_1")
        for kind in ("begin", "wait", "release", "continue", "continue", "continue"):
            state = self.act(state, kind, "resonance_1")
        return state

    def test_interactive_cost_and_exact_replay_preserve_working_graph(self):
        state = self.full_interactive()
        self.assertEqual(state["turn"], 7)
        self.assertEqual(state["resources"]["energy"], 22)
        saved = engine_v3.export_library(state)[0]
        self.assertEqual(saved["engine_version"], 3)
        self.assertEqual(saved["control_script"], [{"tick": 8, "type": "release"}])
        state = self.act(state, "enter", "creation_1")
        state = self.act(state, "tune", "creation_1", {"node": "n3", "delay": 1, "phase": 0})
        working = deepcopy(state["world"]["machine"])
        for _ in range(3):
            state = self.act(state, "replay", saved["id"])
        self.assertEqual(state["world"]["machine"], working)
        self.assertEqual(state["world"]["performance"]["trace_hash"], saved["trace_hash"])
        self.assertTrue(state["last_outcome"]["exact_repeat"])

    def test_running_actions_are_exclusive_invalid_is_immutable(self):
        state = self.act(self.fresh(), "enter", "resonance_1")
        state = self.act(state, "begin", "resonance_1")
        before = deepcopy(state)
        kinds = {a["type"] for a in engine_v3.available_actions(state)}
        self.assertEqual(kinds, {"leave", "wait", "release", "stop"})
        with self.assertRaises(GameError):
            self.act(state, "perform", "resonance_1", {"release_tick": 8})
        with self.assertRaises(GameError):
            self.act(state, "release", "resonance_1", {"unexpected": 1})
        self.assertEqual(state, before)
        self.assertNotIn("seed", engine_v3.observe(state))

    def test_stop_leave_and_familiar_choice_do_not_count_as_exact(self):
        state = self.act(self.fresh(), "enter", "resonance_1")
        state = self.act(state, "begin", "resonance_1")
        state = self.act(state, "stop", "resonance_1")
        saved = state["world"]["saved_experiences"][0]
        self.assertTrue(saved["stopped"])
        self.assertEqual(saved["duration"], 4)
        self.assertNotIn("fork", {a["type"] for a in engine_v3.available_actions(state)})
        with self.assertRaises(GameError):
            self.act(state, "fork", saved["id"], {"release_tick": 4})
        state = self.act(state, "replay", saved["id"])
        self.assertEqual(state["world"]["performance"]["experience"]["state"], "stopped")
        state = self.act(state, "reperform", saved["id"])
        self.assertEqual(state["last_outcome"]["kind"], "reperform")
        self.assertNotIn("exact_repeat", state["last_outcome"])
        state = self.act(state, "leave")
        self.assertEqual(state["state"], "ended")
        self.assertEqual(state["world"]["performance"]["experience"]["state"], "stopped")

    def test_same_cost_choices_fork_and_library_validation(self):
        state = self.full_interactive()
        saved = engine_v3.export_library(state)
        loaded = self.fresh(library=saved)
        replay = next(a for a in engine_v3.available_actions(loaded) if a["type"] == "replay")
        fork = next(a for a in engine_v3.available_actions(loaded) if a["type"] == "fork")
        self.assertEqual(replay["cost"], fork["cost"])
        self.assertNotIn(8, fork["parameters"]["properties"]["release_tick"]["enum"])
        varied = self.act(loaded, "fork", saved[0]["id"], {"release_tick": 4})
        self.assertEqual(varied["last_outcome"]["changed_field"], "release_tick")
        self.assertNotEqual(varied["world"]["performance"]["trace_hash"], saved[0]["trace_hash"])
        corrupted = deepcopy(saved)
        corrupted[0]["engine_version"] = 2
        with self.assertRaises(GameError):
            self.fresh(library=corrupted)
        corrupted = deepcopy(saved)
        corrupted[0]["observation_version"] = True
        with self.assertRaises(GameError):
            self.fresh(library=corrupted)

    def test_begin_requires_six_remaining_positions_and_full_endpoint_is_available(self):
        state = self.act(self.fresh(max_turns=20), "enter", "resonance_1")
        state["turn"] = 15
        types = {a["type"] for a in engine_v3.available_actions(state)}
        self.assertNotIn("begin", types)
        self.assertIn("perform", types)
        state["turn"] = 14
        self.assertIn("begin", {a["type"] for a in engine_v3.available_actions(state)})


if __name__ == "__main__":
    unittest.main()
