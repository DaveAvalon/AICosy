"""Finite coverage policy for V2; its choices are prescribed software checks."""
from __future__ import annotations

import random
from clients.common import ClientError, action_from_descriptor


class DynamicPlayer:
    """Uses only public observations and legal descriptors, with no core imports.

    This deliberately exercises original replay, fork and revision. It must not
    be used as evidence that a model spontaneously preferred any experience.
    """
    def __init__(self, seed=42):
        self.rng = random.Random(seed)

    def __call__(self, observation, _rules):
        actions = observation["available_actions"]
        visible = observation["observation"]
        room = visible.get("active_experience") or {}
        saved = visible.get("saved_experiences", [])
        turn = observation["turn"]

        def choose(kind, target=None, **params):
            descriptor = next((a for a in actions if a["type"] == kind and (target is None or a.get("target") == target)), None)
            if descriptor is None:
                return None
            action = action_from_descriptor(descriptor, self.rng)
            if params:
                schema = descriptor["parameters"].get("properties", {})
                values = action.get("params", {})
                for name, value in params.items():
                    spec = schema.get(name)
                    if spec is None:
                        continue
                    if "enum" in spec and value not in spec["enum"]:
                        value = spec["enum"][0]
                    values[name] = value
                if values:
                    action["params"] = values
            return action

        def replay(kind, newest=False):
            if not saved:
                return None
            targets = [s["id"] for s in (reversed(saved) if newest else saved)]
            for target in targets:
                picked = choose(kind, target)
                if picked:
                    return picked
            return None

        # Every item is a known coverage objective. The fallback still submits
        # only advertised actions if an earlier check changes availability.
        planned = None
        if turn == 0:
            planned = choose("enter", "pattern_1")
        elif turn == 1:
            planned = choose("inspect", "pattern_1")
        elif turn == 2:
            probe = room.get("probe") or {}
            frames = probe.get("frames", [])
            first = next((frame["tick"] for frame in frames if frame.get("values", {}).get("n2", 0)), None)
            if first is not None:
                planned = choose("complete", "pattern_1", answer=first)
        elif turn == 3:
            planned = choose("enter", "creation_1")
        elif turn == 4:
            planned = choose("combine", "creation_1", left="n0", right="n1", relation="supports")
        elif turn == 5:
            planned = choose("connect", "creation_1", left="n2", right="n0", relation="supports")
        elif turn == 6:
            planned = choose("perform", "creation_1", period=4, phase=0)
        elif turn == 7:
            planned = choose("seal", "creation_1")
        elif turn == 8:
            planned = choose("enter", "resonance_1")
        elif turn == 9:
            planned = choose("perform", "resonance_1", period=3, phase=1)
        elif turn == 10:
            planned = replay("replay")
        elif turn == 11:
            planned = replay("fork")
        elif turn == 12:
            planned = choose("revise", "creation_1")
        elif turn == 13:
            planned = choose("tune", "creation_1", node="n1", delay=2, phase=1)
        elif turn == 14:
            planned = choose("perform", "creation_1", period=4, phase=0)
        elif turn == 15:
            planned = choose("seal", "creation_1")
        elif turn == 16:
            planned = replay("replay", newest=True)
        elif turn == 17:
            planned = replay("fork", newest=True)
        elif turn == 18:
            planned = choose("revise", "creation_1")
        elif turn == 19:
            planned = choose("transform", "creation_1", node="n0", operation="invert")
        elif turn == 20:
            planned = choose("perform", "creation_1", period=2, phase=0)
        elif turn == 21:
            planned = choose("seal", "creation_1")
        elif turn == 22:
            planned = choose("enter", "resonance_1")
        elif turn == 23:
            planned = choose("perform", "resonance_1", period=5, phase=1)
        if planned:
            return planned

        for kind in ("perform", "inspect", "seal", "revise", "enter", "leave"):
            chosen = choose(kind)
            if chosen:
                return chosen
        raise ClientError("No supported V2 action is available")
