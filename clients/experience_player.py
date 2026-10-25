"""Finite V3 interface coverage; prescribed choices are not model preferences."""
from __future__ import annotations

import random

from clients.common import ClientError, action_from_descriptor


class ExperiencePlayer:
    def __init__(self, seed=42):
        self.rng = random.Random(seed)
        self.plan = [
            ("enter", "resonance_1", {}),
            ("begin", "resonance_1", {}),
            ("wait", "resonance_1", {}),
            ("release", "resonance_1", {}),
            ("continue", "resonance_1", {}),
            ("continue", "resonance_1", {}),
            ("continue", "resonance_1", {}),
            ("replay", "oldest", {}),
            ("fork", "oldest", {"release_tick": 4}),
            ("reperform", "oldest", {}),
            ("release", "resonance_1", {}),
            ("continue", "resonance_1", {}),
            ("continue", "resonance_1", {}),
            ("continue", "resonance_1", {}),
            ("continue", "resonance_1", {}),
            ("enter", "creation_1", {}),
            ("tune", "creation_1", {"node": "n3", "delay": 1, "phase": 0}),
            ("perform", "creation_1", {"release_tick": 8}),
            ("replay", "newest", {}),
            ("replay", "newest", {}),
            ("replay", "newest", {}),
            ("leave", None, {}),
        ]

    def __call__(self, observation, _rules):
        legal = observation["available_actions"]
        saved = observation["observation"].get("saved_experiences", [])
        index = observation["turn"]
        if index < len(self.plan):
            kind, target, params = self.plan[index]
            if target in ("oldest", "newest"):
                target = saved[0 if target == "oldest" else -1]["id"] if saved else None
            descriptor = next((a for a in legal if a["type"] == kind and a.get("target") == target), None)
            if descriptor:
                result = action_from_descriptor(descriptor, self.rng)
                if params:
                    result["params"] = params
                return result
        # A changed legal path should end cleanly, not silently invent activity.
        descriptor = next((a for a in legal if a["type"] == "leave"), None)
        if descriptor:
            return action_from_descriptor(descriptor, self.rng)
        raise ClientError("No legal exit in V3 observation")
