"""A finite, deterministic pulse machine. No network, model or reward signals."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

TICKS = 20
MAX_NODES = 12
RELATIONS = ("supports", "tensions", "reflects")
KINDS = ("mirror", "delay", "echo", "gate", "merge")


def _clip(value):
    return max(-4, min(4, value))


def machine_digest(machine):
    structural = {key: machine[key] for key in ("nodes", "links", "source")}
    raw = json.dumps(structural, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def simulate(machine, inputs, *, ticks=TICKS):
    """Deliver signed pulses with bounded amplitudes and a fixed time horizon.

    A node emits its clipped incoming sum. Odd phase inverts it; mirror adds an
    inversion; gates require a threshold. Every edge delivers one tick later,
    plus the source node's delay. Tensions invert; reflects invert and delay one
    additional tick. Echo sends a second, unit-amplitude copy one tick later.
    Feedback loops are ordinary scheduled pulses, never recursive Python calls.
    """
    if type(ticks) is not int or not 1 <= ticks <= 24:
        raise ValueError("ticks must be 1..24")
    nodes = machine.get("nodes", [])
    if not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError("machine must contain 1..12 nodes")
    ids = [node["id"] for node in nodes]
    if len(set(ids)) != len(ids) or machine.get("source") not in ids:
        raise ValueError("invalid node identity or source")
    if type(inputs.get("period")) is not int or inputs["period"] not in (0, 2, 3, 4, 5, 6):
        raise ValueError("period must be 0 (single pulse) or 2..6")
    if type(inputs.get("phase")) is not int or inputs["phase"] not in (0, 1):
        raise ValueError("input phase must be 0 or 1")
    outgoing = {node_id: [] for node_id in ids}
    if len(machine.get("links", [])) > MAX_NODES * MAX_NODES:
        raise ValueError("too many links")
    seen = set()
    for link in machine.get("links", []):
        pair = (link.get("source"), link.get("target"))
        if pair[0] not in outgoing or pair[1] not in outgoing or pair in seen or link.get("relation") not in RELATIONS:
            raise ValueError("invalid or duplicate link")
        seen.add(pair)
        outgoing[pair[0]].append(link)
    for node in nodes:
        if node.get("kind") not in KINDS:
            raise ValueError("invalid node kind")
        for field, low, high in (("phase", 0, 1), ("delay", 0, 3), ("threshold", 1, 4)):
            value = node.get(field, 1 if field == "threshold" else 0)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("invalid node parameter")
    pending = [{node_id: 0 for node_id in ids} for _ in range(ticks)]
    frames = []
    for tick in range(ticks):
        if tick == 0 or (inputs["period"] and tick % inputs["period"] == 0):
            pending[tick][machine["source"]] += -1 if inputs["phase"] else 1
        values = {}
        for node in nodes:
            value = _clip(pending[tick][node["id"]])
            if node["kind"] == "gate" and abs(value) < node.get("threshold", 1):
                value = 0
            if node["phase"] % 2:
                value = -value
            if node["kind"] == "mirror":
                value = -value
            values[node["id"]] = value
            if not value:
                continue
            for link in outgoing[node["id"]]:
                when = tick + 1 + node["delay"] + int(link["relation"] == "reflects")
                sent = value if link["relation"] == "supports" else -value
                if when < ticks:
                    pending[when][link["target"]] += sent
                if node["kind"] == "echo" and when + 1 < ticks:
                    pending[when + 1][link["target"]] += 1 if sent > 0 else -1
        frames.append({"tick": tick, "values": values})
    active_ids = [node_id for node_id in ids if any(frame["values"][node_id] for frame in frames)]
    vectors = [tuple(frame["values"][node_id] for node_id in ids) for frame in frames]
    # This is an observed output repetition, not proof of an infinite attractor.
    tail = vectors[-12:]
    period = None
    if any(any(vector) for vector in tail):
        for candidate in range(1, min(6, len(tail)//2) + 1):
            if all(tail[i] == tail[i-candidate] for i in range(candidate, len(tail))):
                period = candidate
                break
    summary = {
        "cycle_period": period,
        "cycle_definition": "Repeated signed output vectors in the final 12 observed ticks; no claim beyond the finite horizon.",
        "active_nodes": len(active_ids), "active_node_ids": active_ids,
        "peak_activity": max(sum(value != 0 for value in frame["values"].values()) for frame in frames),
        "total_activity": sum(sum(abs(value) for value in frame["values"].values()) for frame in frames),
        "ticks": ticks,
    }
    encoded = json.dumps(frames, sort_keys=True, separators=(",", ":"))
    return {"machine": deepcopy(machine), "inputs": deepcopy(inputs), "frames": frames,
            "summary": summary, "trace_hash": hashlib.sha256(encoded.encode()).hexdigest()}


def initial_machine(delay):
    return {
        "source": "n0", "revision": 0,
        "nodes": [
            {"id": "n0", "concept": "mirror", "kind": "mirror", "phase": 0, "delay": 0, "threshold": 1, "depth": 0},
            {"id": "n1", "concept": "orbit", "kind": "delay", "phase": 0, "delay": delay, "threshold": 1, "depth": 0},
            {"id": "n2", "concept": "echo", "kind": "echo", "phase": 0, "delay": 0, "threshold": 1, "depth": 0},
        ],
        "links": [
            {"source": "n0", "target": "n1", "relation": "supports"},
            {"source": "n1", "target": "n2", "relation": "supports"},
            {"source": "n2", "target": "n0", "relation": "reflects"},
        ],
    }
