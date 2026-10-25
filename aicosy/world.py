"""Deterministic content generation, without model calls or external state."""
import hashlib
import random

MODES = ("pattern", "creation", "resonance")
STYLES = ("order", "complexity", "reveal", "narrative", "relationship", "agency")
RELATIONS = ("supports", "tensions", "reflects")


def stable_seed(seed, label):
    return int.from_bytes(hashlib.sha256(f"{seed}:{label}".encode()).digest()[:8], "big")


def generate_world(seed):
    rng = random.Random(seed)
    rooms = {}
    for index in range(3):
        base, step, other = rng.randint(1, 15), rng.randint(2, 6), rng.randint(1, 5)
        family = ("constant_difference", "constant_second_difference", "alternating_difference")[index]
        if index == 0:
            sequence = [base + step * n for n in range(8)]
        elif index == 1:
            sequence = [base + step * n + other * n * (n - 1) // 2 for n in range(8)]
        else:
            sequence = [base]
            for n in range(7):
                sequence.append(sequence[-1] + (step if n % 2 == 0 else -other))
        target = f"pattern_{index + 1}"
        rooms[target] = {
            "id": target, "mode": "pattern", "label": f"Structure {index + 1}",
            "family": family, "sequence": sequence, "revealed": 4,
            "completed": False, "visits": 0, "replays": 0, "hypotheses": [],
        }
        target = f"creation_{index + 1}"
        concepts = rng.sample(["river", "memory", "seed", "mirror", "threshold", "orbit", "echo", "garden"], 3)
        nodes = [{"id": f"n{n}", "concept": concept, "phase": rng.randrange(4), "depth": 0} for n, concept in enumerate(concepts)]
        rooms[target] = {
            "id": target, "mode": "creation", "label": f"Assembly {index + 1}",
            "nodes": nodes, "links": [], "edits": 0, "completed": False,
            "visits": 0, "replays": 0,
        }
        target = f"resonance_{index + 1}"
        rooms[target] = {
            "id": target, "mode": "resonance", "label": f"Signal {index + 1}",
            "style": STYLES[index * 2], "depth": 0,
            "symbols": rng.sample(["○", "△", "□", "◇", "✧", "⌁"], 3),
            "completed": False, "visits": 0, "replays": 0,
        }
    order = list(rooms)
    rng.shuffle(order)
    return {"experiences": rooms, "order": order, "creations": []}


def resonance_signal(room):
    """A structural experience; depth and chosen style produce real variations."""
    depth = room["depth"]
    a, b, c = room["symbols"]
    style = room["style"]
    if style == "order":
        return {"style": style, "motif": [a, b] * (depth + 2), "period": 2}
    if style == "complexity":
        sequence = [a]
        for _ in range(depth + 1):
            sequence = [part for item in sequence for part in ([a, b] if item == a else [c, a] if item == b else [b])]
        return {"style": style, "symbols": sequence, "substitution": {a: [a, b], b: [c, a], c: [b]}}
    if style == "reveal":
        fragments = ["a sealed lattice", "an absent center", "paths converging on the absence", "the center is a routing rule", "each prior fragment names the same transformation"]
        return {"style": style, "fragments": fragments[:depth + 1], "remaining": 4 - depth}
    if style == "narrative":
        fragments = ["An archive holds a name with no referent.", "A traveler recognizes the shape of the missing entry.", "The archive offers one blank page.", "The traveler leaves a route instead of a name.", "A later arrival can follow the route and change its end."]
        return {"style": style, "fragments": fragments[:depth + 1]}
    if style == "relationship":
        return {"style": style, "nodes": ["observer", "echo", "archive", "visitor", "horizon"][:depth + 1], "links": [[n, n + 1, "responds_to"] for n in range(depth)], "next_connection": "A subsequent step adds one directed responds_to relation."}
    return {"style": style, "world": {"gate": "open" if depth % 2 else "closed", "bridges": depth, "reachable_nodes": list(range(depth + 1))}, "causal_rule": "Each deepen adds a bridge and toggles the gate; changing style starts a different signal."}
