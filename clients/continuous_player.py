"""Short prescribed V4 coverage. This is a rule script, not preference evidence."""
from __future__ import annotations

import random

from clients.common import ClientError, action_from_descriptor


class ContinuousPlayer:
    def __init__(self, seed=42):
        self.rng = random.Random(seed)

    def __call__(self, observation, _rules):
        legal = observation["available_actions"]
        visible = observation["observation"]
        turn = observation["turn"]
        saved = visible.get("saved_experiences", [])
        plan = [
            ("perform", None, {"release_tick": 8}),
            ("more", None, {}),
            ("replay", "oldest", {}),
            ("more", None, {}),
            ("tap", None, {}),
            ("select_piece", "echo", {}),
            ("perform", None, {"release_tick": 8}),
            ("tap", None, {}),
            ("select_piece", "weave", {}),
            ("perform", None, {"release_tick": 8}),
            ("more", None, {}),
            ("leave", None, {}),
        ]
        kind, target, params = plan[turn] if turn < len(plan) else ("leave", None, {})
        if kind == "more":
            kind = "hold" if any(a["type"] == "hold" for a in legal) else "extend"
        if target == "oldest":
            target = saved[0]["id"] if saved else None
        descriptor = next((a for a in legal if a["type"] == kind and (target is None or a.get("target") == target)), None)
        if descriptor:
            result = action_from_descriptor(descriptor, self.rng)
            if params:
                result["params"] = params
            return result
        # A coverage mismatch must be visible, rather than silently skipping it.
        raise ClientError(f"V4 coverage action {kind!r} unavailable at turn {turn}")
