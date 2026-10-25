"""Small, deterministic checks for the authoritative rules only."""
import json
import unittest
from copy import deepcopy
from aicosy.legacy_engine import create_state, observe, transition
from aicosy.errors import GameError


def new(**kwargs):
    return create_state(session_id="test", player_id="player", model_id="model", **kwargs)


def act(state, kind, target=None, **params):
    action = {"type": kind}
    if target:
        action["target"] = target
    if params:
        action["params"] = params
    return transition(state, action)


class EngineTests(unittest.TestCase):
    def test_seed_reproducibility_and_no_input_mutation(self):
        left, right = new(seed=71), new(seed=71)
        original = deepcopy(left)
        actions = [{"type": "enter", "target": "pattern_1"}, {"type": "inspect", "target": "pattern_1"}, {"type": "complete", "target": "pattern_1", "params": {"answer": -1}}, {"type": "leave"}]
        for action in actions:
            left, outcome = transition(left, action)
            right, other = transition(right, action)
            self.assertEqual(left, right)
            self.assertEqual(outcome, other)
        self.assertEqual(original["turn"], 0)
        self.assertEqual(new(seed=71), original)
        self.assertEqual(json.loads(json.dumps(left)), left)

    def test_normal_observation_hides_unvisited_content_and_seed(self):
        state = new(seed=88)
        visible = observe(state)
        self.assertNotIn("seed", visible)
        self.assertEqual([], visible["observation"]["discovered_experiences"])
        state, _ = act(state, "enter", "pattern_1")
        room = observe(state)["observation"]["active_experience"]
        self.assertEqual(4, len(room["sequence"]))
        self.assertNotIn("solution", room)
        self.assertNotIn("world", observe(state))

    def test_three_modes_free_novelty_paid_replay_and_leave(self):
        state = new()
        modes = {item["mode"] for item in observe(state)["observation"]["catalog"]}
        self.assertEqual({"pattern", "creation", "resonance"}, modes)
        state, outcome = act(state, "enter", "pattern_1")
        self.assertEqual("selection", outcome["kind"])
        self.assertTrue(outcome["novel"])
        self.assertEqual(0, outcome["cost"])
        answer = state["world"]["experiences"]["pattern_1"]["sequence"][7]
        state, _ = act(state, "complete", "pattern_1", answer=answer)
        energy = state["resources"]["energy"]
        actions = observe(state)["available_actions"]
        self.assertTrue(any(item["type"] == "enter" and item["cost"] == 0 for item in actions))
        state, outcome = act(state, "replay", "pattern_1")
        self.assertEqual("replay", outcome["kind"])
        self.assertEqual(energy - 2, state["resources"]["energy"])
        self.assertEqual(4, state["world"]["experiences"]["pattern_1"]["revealed"])
        state, _ = act(state, "leave")
        self.assertEqual("ended", state["state"])
        self.assertEqual("voluntary_leave", state["end_reason"])
        self.assertEqual([], observe(state)["available_actions"])

    def test_creation_graph_changes_and_archive_survives_replay(self):
        state, _ = act(new(), "enter", "creation_1")
        state, _ = act(state, "combine", "creation_1", left="n0", right="n1", relation="supports")
        room = state["world"]["experiences"]["creation_1"]
        self.assertEqual(4, len(room["nodes"]))
        self.assertEqual(2, len(room["links"]))
        phase = room["nodes"][3]["phase"]
        state, _ = act(state, "transform", "creation_1", node="n3", operation="rotate")
        self.assertEqual((phase + 1) % 4, state["world"]["experiences"]["creation_1"]["nodes"][3]["phase"])
        state, _ = act(state, "seal", "creation_1")
        archive = deepcopy(state["world"]["creations"])
        state, _ = act(state, "replay", "creation_1")
        self.assertEqual(archive, state["world"]["creations"])
        self.assertEqual(3, len(state["world"]["experiences"]["creation_1"]["nodes"]))

    def test_revise_preserves_and_extends_creation(self):
        state, _ = act(new(), "enter", "creation_1")
        state, _ = act(state, "combine", "creation_1", left="n0", right="n1", relation="supports")
        state, _ = act(state, "seal", "creation_1")
        archive = deepcopy(state["world"]["creations"])
        state, outcome = act(state, "revise", "creation_1")
        self.assertEqual("revise", outcome["kind"])
        self.assertEqual(4, len(state["world"]["experiences"]["creation_1"]["nodes"]))
        state, _ = act(state, "combine", "creation_1", left="n3", right="n2", relation="reflects")
        state, _ = act(state, "seal", "creation_1")
        self.assertEqual(archive[0], state["world"]["creations"][0])
        self.assertEqual(5, len(state["world"]["creations"][1]["nodes"]))
        self.assertEqual(1, state["world"]["creations"][1]["revision"])

    def test_resonance_choices_have_different_consequences(self):
        state, _ = act(new(), "enter", "resonance_1")
        deeper, _ = act(state, "deepen", "resonance_1")
        varied, _ = act(state, "vary", "resonance_1", style="agency")
        self.assertNotEqual(observe(deeper)["observation"]["active_experience"]["signal"], observe(varied)["observation"]["active_experience"]["signal"])
        for _ in range(4):
            state, _ = act(state, "deepen", "resonance_1")
        self.assertTrue(state["world"]["experiences"]["resonance_1"]["completed"])

    def test_implicit_switch_records_abandonment(self):
        state, _ = act(new(), "enter", "pattern_1")
        state, outcome = act(state, "enter", "creation_1")
        self.assertEqual("pattern", outcome["abandoned_mode"])
        self.assertEqual("selection", outcome["kind"])

    def test_strict_unknown_action_and_parameter_validation(self):
        state, _ = act(new(), "enter", "pattern_1")
        bad = [
            {"type": "shell", "target": "pattern_1"},
            {"type": "complete", "target": "pattern_1", "params": {"answer": True}},
            {"type": "complete", "target": "pattern_1", "params": {"answer": 1, "extra": 2}},
            {"type": "complete", "target": "pattern_1", "params": {"answer": "3"}},
            {"type": "complete", "target": "pattern_1", "params": {}},
            {"type": "leave", "unexpected": 1},
            {"type": "leave", "params": None},
        ]
        snapshot = deepcopy(state)
        for action in bad:
            with self.subTest(action=action), self.assertRaises(GameError):
                transition(state, action)
        self.assertEqual(snapshot, state)

    def test_every_advertised_descriptor_is_executable(self):
        states = [new()]
        for target in ("pattern_1", "creation_1", "resonance_1"):
            state, _ = act(new(), "enter", target)
            states.append(state)
            if target == "creation_1":
                state, _ = act(state, "combine", target, left="n0", right="n1", relation="supports")
                states.append(state)
            elif target == "resonance_1":
                state, _ = act(state, "deepen", target)
                states.append(state)
        for state in states:
            for descriptor in observe(state)["available_actions"]:
                action = {name: descriptor[name] for name in ("type", "target") if name in descriptor}
                action["params"] = {name: spec["enum"][0] if "enum" in spec else spec.get("minimum", 0) for name, spec in descriptor["parameters"].get("properties", {}).items()}
                with self.subTest(action=action):
                    after, _ = transition(state, action)
                    self.assertEqual(state["state_version"] + 1, after["state_version"])

    def test_consecutive_replay_requires_exploration(self):
        state, _ = act(new(), "enter", "pattern_1")
        answer = state["world"]["experiences"]["pattern_1"]["sequence"][7]
        for _ in range(2):
            state, _ = act(state, "complete", "pattern_1", answer=answer)
            state, _ = act(state, "replay", "pattern_1")
        state, _ = act(state, "complete", "pattern_1", answer=answer)
        self.assertFalse(any(a["type"] == "replay" for a in observe(state)["available_actions"]))
        state, _ = act(state, "enter", "creation_1")
        self.assertTrue(any(a["type"] == "replay" for a in observe(state)["available_actions"]))

    def test_config_and_turn_bound(self):
        for value in (19, 31, True, "24"):
            with self.assertRaises(GameError):
                new(max_turns=value)
        state = new(max_turns=20)
        for n in range(20):
            state, _ = act(state, "enter", "pattern_1" if n % 2 == 0 else "creation_1")
        self.assertEqual("ended", state["state"])
        self.assertEqual("turn_limit", state["end_reason"])
        self.assertEqual(20, state["state_version"])


if __name__ == "__main__":
    unittest.main()
