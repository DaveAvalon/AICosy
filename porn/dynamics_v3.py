"""Version-three finite performances with a bounded, controllable reservoir.

Prefixes are recomputed from captured inputs and effective controls. No wall
clock, player identity, reward model or hidden future observation is involved.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

TICKS = 24
CHUNK = 4
MAX_NODES = 12
CAPACITY = 8
RELATIONS = ("supports", "tensions", "reflects")
KINDS = ("mirror", "delay", "echo", "gate", "merge", "reservoir")
RELEASE_TICKS = (4, 8, 12, 16, 20)
DEFAULT_INPUTS = {"pulse_ticks": [0, 2, 4, 6], "phase": 0}
RULES_VERSION = 3
OBSERVATION_VERSION = 1


def _clip(value, limit=4):
    return max(-limit, min(limit, value))


def initial_machine():
    specs = (("input", "merge", 0), ("reservoir", "reservoir", 0),
             ("short", "delay", 0), ("delayed inverse", "mirror", 2),
             ("join and echo", "echo", 0), ("output", "merge", 0))
    return {"source": "n0", "output": "n5", "revision": 0,
            "nodes": [{"id": f"n{i}", "concept": label, "kind": kind,
                       "phase": 0, "delay": delay, "threshold": 1, "depth": 0}
                      for i, (label, kind, delay) in enumerate(specs)],
            "links": [{"source": f"n{a}", "target": f"n{b}", "relation": "supports"}
                      for a, b in ((0, 1), (1, 2), (1, 3), (2, 4), (3, 4), (4, 5))]}


def _validate(machine, inputs, controls, ticks):
    if type(ticks) is not int or not 1 <= ticks <= TICKS:
        raise ValueError("ticks must be 1..24")
    if not isinstance(machine, dict) or not isinstance(inputs, dict):
        raise ValueError("machine and inputs must be objects")
    nodes = machine.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError("machine must contain 1..12 nodes")
    if any(not isinstance(n, dict) or not isinstance(n.get("id"), str) for n in nodes):
        raise ValueError("invalid node")
    ids = [node["id"] for node in nodes]
    if len(set(ids)) != len(ids) or machine.get("source") not in ids or machine.get("output") not in ids:
        raise ValueError("invalid node identity, source or output")
    if type(machine.get("revision")) is not int or machine["revision"] < 0:
        raise ValueError("invalid machine revision")
    if sum(n.get("kind") == "reservoir" for n in nodes) != 1:
        raise ValueError("exactly one reservoir is required")
    for node in nodes:
        if node.get("kind") not in KINDS:
            raise ValueError("invalid node kind")
        for key, lo, hi in (("phase", 0, 1), ("delay", 0, 3), ("threshold", 1, 4)):
            value = node.get(key, 1 if key == "threshold" else 0)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError("invalid node parameter")
    links = machine.get("links")
    if not isinstance(links, list) or len(links) > MAX_NODES * MAX_NODES:
        raise ValueError("invalid links")
    seen = set()
    for link in links:
        if not isinstance(link, dict):
            raise ValueError("invalid link")
        pair = (link.get("source"), link.get("target"))
        if pair[0] not in ids or pair[1] not in ids or pair in seen or link.get("relation") not in RELATIONS:
            raise ValueError("invalid or duplicate link")
        seen.add(pair)
    pulses = inputs.get("pulse_ticks")
    if set(inputs) != {"pulse_ticks", "phase"} or not isinstance(pulses, list) or len(pulses) > TICKS:
        raise ValueError("invalid input fields")
    if any(type(t) is not int or not 0 <= t < TICKS for t in pulses) or pulses != sorted(set(pulses)):
        raise ValueError("pulse_ticks must be ordered unique ticks in 0..23")
    if type(inputs["phase"]) is not int or inputs["phase"] not in (0, 1):
        raise ValueError("input phase must be zero or one")
    if not isinstance(controls, list) or len(controls) > 1:
        raise ValueError("at most one effective release control is allowed")
    for control in controls:
        if (not isinstance(control, dict) or set(control) != {"tick", "type"}
                or control["type"] != "release" or type(control["tick"]) is not int
                or control["tick"] not in RELEASE_TICKS or control["tick"] >= ticks):
            raise ValueError("invalid effective release control")
    return ids


def simulate(machine, inputs=None, control_script=None, *, ticks=TICKS, stopped=False, running=False):
    """Run only the requested prefix; each frame is the state after that tick.

    The queue extends six ticks past the observed prefix to report pending
    propagation honestly, including signals scheduled beyond the horizon.
    """
    inputs = deepcopy(DEFAULT_INPUTS if inputs is None else inputs)
    controls = deepcopy([] if control_script is None else control_script)
    ids = _validate(machine, inputs, controls, ticks)
    if type(stopped) is not bool or type(running) is not bool or (stopped and running):
        raise ValueError("invalid process status")
    if running and ticks >= TICKS:
        raise ValueError("a horizon-length process cannot remain running")
    if not running and not stopped and ticks != TICKS:
        raise ValueError("a completed process must reach the 24-tick horizon")
    outgoing = {node_id: [] for node_id in ids}
    for link in machine["links"]:
        outgoing[link["source"]].append(link)
    pending = [{node_id: 0 for node_id in ids} for _ in range(ticks + 6)]
    reservoirs = {n["id"]: 0 for n in machine["nodes"] if n["kind"] == "reservoir"}
    release_tick = controls[0]["tick"] if controls else None
    gate_open = False
    frames, events = [], []

    def event(tick, kind, node, message, **fields):
        events.append({"tick": tick, "kind": kind, "node": node, "message": message, **fields})

    for tick in range(ticks):
        if tick == release_tick:
            gate_open = True
            for node_id in reservoirs:
                event(tick, "release", node_id, "蓄积门已打开")
        if tick in inputs["pulse_ticks"]:
            value = -1 if inputs["phase"] else 1
            pending[tick][machine["source"]] += value
            event(tick, "input", machine["source"], f"输入脉冲 {value:+d}", value=value)
        values = {}
        for node in machine["nodes"]:
            node_id, incoming = node["id"], pending[tick][node["id"]]
            if node["kind"] == "reservoir":
                before = reservoirs[node_id]
                combined = before + incoming
                reservoirs[node_id] = _clip(combined, CAPACITY)
                overflow = combined - reservoirs[node_id]
                if overflow:
                    event(tick, "overflow", node_id, f"容量截断，丢弃 {overflow:+d}", discarded=overflow)
                value = _clip(reservoirs[node_id]) if gate_open else 0
                reservoirs[node_id] -= value
                if incoming or value:
                    after = reservoirs[node_id]
                    event(tick, "reservoir", node_id, f"存量 {before} → {after}",
                          before=before, after=after, incoming=incoming, emitted=value)
            else:
                value = _clip(incoming)
                if node["kind"] == "gate" and abs(value) < node.get("threshold", 1):
                    value = 0
            if node.get("phase", 0):
                value = -value
            if node["kind"] == "mirror":
                value = -value
            values[node_id] = value
            if not value:
                continue
            if node_id == machine["output"]:
                event(tick, "output", node_id, f"输出 {value:+d}", value=value)
            else:
                event(tick, "response", node_id, f"节点 {node_id} 响应 {value:+d}", value=value)
            for link in outgoing[node_id]:
                when = tick + 1 + node.get("delay", 0) + int(link["relation"] == "reflects")
                sent = value if link["relation"] == "supports" else -value
                pending[when][link["target"]] += sent
                if node["kind"] == "echo":
                    pending[when + 1][link["target"]] += 1 if sent > 0 else -1
        frames.append({"tick": tick, "values": values, "reservoirs": deepcopy(reservoirs), "gate_open": gate_open})

    future_inputs = running and any(t >= ticks for t in inputs["pulse_ticks"])
    remaining = bool(future_inputs or any(reservoirs.values()) or any(any(p.values()) for p in pending[ticks:]))
    status = "running" if running else ("stopped" if stopped else "completed")
    if not running:
        message = "本段已停止" if stopped else "已到观察上限"
        message += "，仍有存量或待传播信号" if remaining else "，已无存量或待传播信号"
        event(ticks - 1, "stopped" if stopped else "horizon", machine["output"], message)
    active = [node_id for node_id in ids if any(f["values"][node_id] for f in frames)]
    summary = {"cycle_period": None, "cycle_definition": "Finite controlled performance; no infinite-cycle inference.",
               "active_nodes": len(active), "active_node_ids": active,
               "peak_activity": max(sum(v != 0 for v in f["values"].values()) for f in frames),
               "total_activity": sum(sum(abs(v) for v in f["values"].values()) for f in frames),
               "ticks": ticks, "output_node": machine["output"],
               "output_sequence": [{"tick": f["tick"], "value": f["values"][machine["output"]]}
                                   for f in frames if f["values"][machine["output"]]],
               "remaining_activity": remaining, "completed": status == "completed"}
    experience = {"state": status, "tick": ticks, "horizon": TICKS,
                  "reservoirs": deepcopy(reservoirs), "gate_open": gate_open,
                  "events": events, "control_script": controls,
                  "completed": status == "completed", "remaining_activity": remaining}
    content = {"engine_version": 3, "rules_version": RULES_VERSION, "observation_version": OBSERVATION_VERSION,
               "machine": deepcopy(machine), "inputs": inputs, "control_script": controls,
               "duration": ticks, "stopped": stopped, "frames": frames, "experience": experience}
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {**content, "summary": summary, "trace_hash": hashlib.sha256(encoded.encode()).hexdigest()}
