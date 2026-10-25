"""Deterministic coverage player, not evidence of a model's spontaneous preference."""
from __future__ import annotations

import random
import sys
from clients.common import ClientError, action_from_descriptor, parser, print_result, run_agent


def predict_sequence(room):
    values = list(room["sequence"])
    differences = [b - a for a, b in zip(values, values[1:])]
    family = room["family"]
    if family == "constant_difference":
        while len(values) <= room["target_index"]:
            values.append(values[-1] + differences[0])
    elif family == "constant_second_difference":
        delta = differences[1] - differences[0]
        last_difference = differences[-1]
        while len(values) <= room["target_index"]:
            last_difference += delta
            values.append(values[-1] + last_difference)
    elif family == "alternating_difference":
        while len(values) <= room["target_index"]:
            values.append(values[-1] + differences[(len(values) - 1) % 2])
    else:
        raise ClientError("Unknown pattern family")
    return values[room["target_index"]]


class RulePlayer:
    def __init__(self, seed=42):
        self.seed = seed
        self.rng = random.Random(seed)
        self.varied = set()
        self.dynamic = None
        self.experience = None
        self.continuous = None

    def __call__(self, observation, _rules):
        if observation.get("engine_version") == 4:
            if self.continuous is None:
                from clients.continuous_player import ContinuousPlayer
                self.continuous = ContinuousPlayer(self.seed)
            return self.continuous(observation, _rules)
        if observation.get("engine_version") == 3:
            if self.experience is None:
                from clients.experience_player import ExperiencePlayer
                self.experience = ExperiencePlayer(self.seed)
            return self.experience(observation, _rules)
        if observation.get("engine_version", 1) == 2:
            if self.dynamic is None:
                from clients.dynamic_player import DynamicPlayer
                self.dynamic = DynamicPlayer(self.seed)
            return self.dynamic(observation, _rules)
        actions = observation["available_actions"]
        world = observation["observation"]
        catalog = world["catalog"]
        room = world["active_experience"]
        by_type = {}
        for descriptor in actions:
            by_type.setdefault(descriptor["type"], []).append(descriptor)

        def select(kind, target=None):
            choices = by_type[kind]
            descriptor = next((a for a in choices if target is None or a.get("target") == target), choices[0])
            return action_from_descriptor(descriptor, self.rng)

        if room is None or room["completed"]:
            seen = {item["mode"] for item in catalog if item["visits"]}
            if len(seen) == 3 and not any(item["replays"] for item in catalog) and "replay" in by_type:
                # A deliberate protocol coverage check; the script is not estimating preference.
                completed_pattern = next((item["id"] for item in catalog if item["completed"] and item["mode"] == "pattern"), None)
                return select("replay", completed_pattern)
            if "enter" in by_type:
                candidates = {a["target"] for a in by_type["enter"]}
                unseen_mode = next((item for item in catalog if item["id"] in candidates and item["mode"] not in seen), None)
                new_room = next((item for item in catalog if item["id"] in candidates and not item["visits"]), None)
                return select("enter", (unseen_mode or new_room or {"id": next(iter(candidates))})["id"])
            if "replay" in by_type:
                return select("replay")
            return select("leave")
        if room["mode"] == "pattern" and "complete" in by_type:
            if len(room["sequence"]) == 4 and "inspect" in by_type:
                return select("inspect")
            action = select("complete")
            action["params"] = {"answer": predict_sequence(room)}
            return action
        if room["mode"] == "creation":
            if room["edits"] == 0 and "combine" in by_type:
                action = select("combine")
                action["params"]["left"], action["params"]["right"] = room["nodes"][0]["id"], room["nodes"][1]["id"]
                return action
            if room["edits"] == 1 and "transform" in by_type:
                return select("transform")
            if "seal" in by_type:
                return select("seal")
        if room["mode"] == "resonance":
            if room["depth"] == 0 and room["id"] not in self.varied and "vary" in by_type:
                self.varied.add(room["id"])
                return select("vary")
            if "deepen" in by_type:
                return select("deepen")
        # If energy is exhausted, switching still changes world visitation and remains legal.
        if "enter" in by_type:
            return select("enter")
        return select("leave")


def main():
    command = parser(__doc__, player="rule-player-v4", model="rule-script-v4")
    command.set_defaults(no_memory=True)
    args = command.parse_args()
    try:
        print_result(run_agent(args, RulePlayer(args.seed), kind="rule-script"))
    except ClientError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
