"""Small exact checks for the V2 causal process, snapshots and input validation."""
from copy import deepcopy
import json
import unittest

from porn.dynamics import initial_machine, simulate
from porn.engine_v2 import available_actions, create_state, export_library, observe, transition
from porn.errors import GameError


def new(**kwargs):
    return create_state(session_id="dynamic-test", player_id="player", model_id="model", **kwargs)


def act(state, kind, target=None, **params):
    action = {"type": kind}
    if target is not None:
        action["target"] = target
    if params:
        action["params"] = params
    return transition(state, action)


class DynamicEngineTests(unittest.TestCase):
    def test_pure_deterministic_real_propagation_and_bounded_feedback(self):
        machine = initial_machine(1)
        snapshot = deepcopy(machine)
        left = simulate(machine, {"period": 4, "phase": 0})
        self.assertEqual(left, simulate(machine, {"period": 4, "phase": 0}))
        self.assertEqual(machine, snapshot)
        self.assertEqual(20, len(left["frames"]))
        self.assertNotEqual(0, left["frames"][0]["values"]["n0"])
        self.assertEqual(0, left["frames"][0]["values"]["n2"])
        self.assertTrue(any(frame["values"]["n2"] for frame in left["frames"][1:]))
        self.assertTrue(all(-4 <= value <= 4 for frame in left["frames"] for value in frame["values"].values()))
        changed = deepcopy(machine)
        changed["nodes"][1]["delay"] = 3
        self.assertNotEqual(left["trace_hash"], simulate(changed, {"period": 4, "phase": 0})["trace_hash"])
        changed = deepcopy(machine)
        changed["links"][-1]["relation"] = "supports"
        self.assertNotEqual(left["trace_hash"], simulate(changed, {"period": 4, "phase": 0})["trace_hash"])

    def test_shared_machine_pattern_discovery_and_downstream_edit(self):
        state = new(seed=17)
        original = deepcopy(state)
        state, _ = act(state, "enter", "pattern_1")
        state, _ = act(state, "inspect", "pattern_1")
        probe = observe(state)["observation"]["active_experience"]["probe"]
        arrival = next(frame["tick"] for frame in probe["frames"] if frame["values"]["n2"])
        state, outcome = act(state, "complete", "pattern_1", answer=arrival)
        self.assertTrue(outcome["correct"])
        self.assertEqual(arrival, state["world"]["discoveries"][0]["tick"])
        state, _ = act(state, "enter", "creation_1")
        before = deepcopy(state)
        state, _ = act(state, "transform", "creation_1", node="n0", operation="invert")
        self.assertNotEqual(probe["trace_hash"], simulate(state["world"]["machine"], {"period": 0, "phase": 0})["trace_hash"])
        self.assertEqual(before["world"]["machine"]["revision"]+1, state["world"]["machine"]["revision"])
        self.assertEqual(new(seed=17), original)
        self.assertEqual(0, original["turn"])
        self.assertEqual(state, json.loads(json.dumps(state)))

    def test_transform_advertises_one_real_binary_operation(self):
        state, _ = act(new(), "enter", "creation_1")
        descriptor = next(a for a in available_actions(state) if a["type"] == "transform")
        self.assertEqual(descriptor["parameters"]["properties"]["operation"]["enum"], ["invert"])
        before = simulate(state["world"]["machine"], {"period": 4, "phase": 0})
        changed, _ = act(state, "transform", "creation_1", node="n0", operation="invert")
        self.assertNotEqual(before["frames"], changed["world"]["performance"]["frames"])
        restored, _ = act(changed, "transform", "creation_1", node="n0", operation="invert")
        self.assertEqual(before["frames"], restored["world"]["performance"]["frames"])

    def test_exact_replay_preserves_working_graph_after_edits(self):
        state, _ = act(new(), "enter", "creation_1")
        state, outcome = act(state, "perform", "creation_1", period=4, phase=0)
        saved_id = outcome["saved_id"]
        frames = deepcopy(outcome["performance"]["frames"])
        state, _ = act(state, "tune", "creation_1", node="n1", delay=3, phase=1)
        graph = deepcopy(state["world"]["machine"])
        energy = state["resources"]["energy"]
        state, outcome = act(state, "replay", saved_id)
        self.assertEqual(energy-2, state["resources"]["energy"])
        self.assertEqual(graph, state["world"]["machine"])
        self.assertEqual(frames, outcome["performance"]["frames"])
        self.assertEqual("replay", outcome["kind"])
        self.assertTrue(outcome["exact_repeat"])
        self.assertEqual(1, len(state["world"]["saved_experiences"]))

    def test_fork_and_revision_are_separate_from_repeat(self):
        state, _ = act(new(), "enter", "creation_1")
        state, _ = act(state, "combine", "creation_1", left="n0", right="n1", relation="supports")
        state, outcome = act(state, "perform", "creation_1", period=4, phase=0)
        saved = deepcopy(state["world"]["saved_experiences"][0])
        graph = deepcopy(state["world"]["machine"])
        state, fork = act(state, "fork", saved["id"], period=3)
        self.assertEqual("fork", fork["kind"])
        self.assertEqual(graph, state["world"]["machine"])
        self.assertEqual({"period": 3, "phase": 0}, fork["performance"]["inputs"])
        self.assertNotEqual(saved["trace_hash"], fork["performance"]["trace_hash"])
        state, _ = act(state, "seal", "creation_1")
        archives = deepcopy(state["world"]["creations"])
        state, revision = act(state, "revise", "creation_1")
        self.assertEqual("revise", revision["kind"])
        self.assertEqual(graph, state["world"]["machine"])
        self.assertEqual(archives, state["world"]["creations"])

    def test_saved_library_survives_new_session_and_restore(self):
        first, _ = act(new(), "enter", "resonance_1")
        first, output = act(first, "perform", "resonance_1", period=3, phase=1)
        library = export_library(first)
        second = create_state(session_id="next-session", player_id="player", model_id="model", seed=71, library=library)
        self.assertNotIn("seed", json.dumps(library))
        self.assertEqual(output["saved_id"], second["world"]["saved_experiences"][0]["id"])
        second, repeated = act(second, "replay", output["saved_id"])
        self.assertEqual(output["performance"]["frames"], repeated["performance"]["frames"])
        second, restored = act(second, "restore", output["saved_id"])
        self.assertEqual("restore", restored["kind"])
        self.assertEqual("creation_1", second["active_target"])
        self.assertEqual(library[0]["machine"]["nodes"], second["world"]["machine"]["nodes"])
        self.assertEqual(library, export_library(first))
        second["world"]["saved_experiences"][0]["label"] = "changed"
        self.assertNotEqual(second["world"]["saved_experiences"], library)

    def test_library_is_bounded_without_disabling_new_performances(self):
        state, _ = act(new(max_turns=30), "enter", "resonance_1")
        for index in range(8):
            state, _ = act(state, "perform", "resonance_1", period=2+index%5, phase=index%2)
        self.assertEqual(6, len(export_library(state)))
        self.assertTrue(any(action["type"] == "perform" for action in available_actions(state)))
        self.assertEqual(8, state["world"]["saved_experiences"][-1]["created_turn"]-1)

    def test_normal_projection_and_unknown_input_safety(self):
        state = new(seed=91)
        self.assertNotIn("seed", json.dumps(observe(state)))
        state, _ = act(state, "enter", "creation_1")
        snapshot = deepcopy(state)
        for action in ({"type": "shell"}, {"type": "perform", "target": "creation_1", "params": {"period": True, "phase": 0}},
                       {"type": "perform", "target": "creation_1", "params": {"period": 4, "phase": 0, "extra": 1}},
                       {"type": "perform", "target": "creation_1", "params": {}},
                       {"type": "leave", "params": None}):
            with self.subTest(action=action), self.assertRaises(GameError):
                transition(state, action)
        self.assertEqual(state, snapshot)

    def test_advertised_descriptors_and_turn_limit(self):
        states = [new()]
        for target in ("pattern_1", "creation_1", "resonance_1"):
            state, _ = act(new(), "enter", target)
            states.append(state)
        state, _ = act(states[2], "perform", "creation_1", period=4, phase=0)
        states.append(state)
        for state in states:
            for desc in available_actions(state):
                action = {key: desc[key] for key in ("type", "target") if key in desc}
                action["params"] = {key: spec["enum"][0] if "enum" in spec else spec.get("minimum", 0) for key, spec in desc["parameters"].get("properties", {}).items()}
                with self.subTest(action=action):
                    after, _ = transition(state, action)
                    self.assertEqual(state["state_version"]+1, after["state_version"])
        state = new(max_turns=20)
        for n in range(20):
            state, _ = act(state, "enter", "creation_1" if n%2 == 0 else "resonance_1")
        self.assertEqual("ended", state["state"])
        self.assertEqual("turn_limit", state["end_reason"])


if __name__ == "__main__":
    unittest.main()
