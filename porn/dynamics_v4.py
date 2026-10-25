"""Incremental deterministic pulse dynamics with serializable checkpoints.

The checkpoint, rather than a displayed frame, owns all future propagation.
Cycle certificates compare the complete relative state already observed.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from .dynamics_v3 import (CAPACITY, CHUNK, KINDS, MAX_NODES, RELEASE_TICKS,
                          RELATIONS, _clip, _validate, initial_machine as echo_machine)

SEGMENT = 24
TICKS = 96
RULES_VERSION = 4
OBSERVATION_VERSION = 1
PIECES = (
    {"id": "echo", "label": "双路回声", "description": "两路不同延迟和反相的回应；输入结束后可以自然静止。"},
    {"id": "orbit", "label": "反相回环", "description": "单个脉冲经过六个节点，每次回到蓄积门时反相。"},
    {"id": "weave", "label": "交织回响", "description": "双路回声重新进入蓄积门，形成持续的叠合与反馈。"},
)


def piece(piece_id):
    if piece_id not in {p["id"] for p in PIECES}:
        raise ValueError("unknown piece")
    machine = echo_machine()
    inputs = {"pulse_ticks": [0, 2, 4, 6], "phase": 0}
    if piece_id == "orbit":
        inputs["pulse_ticks"] = [0]
        machine["nodes"][4]["kind"] = "merge"
        machine["nodes"][4]["concept"] = "return"
        machine["nodes"][5]["delay"] = 1
        machine["links"] = [{"source": f"n{a}", "target": f"n{b}", "relation": "supports"}
                            for a, b in ((0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 1))]
    elif piece_id == "weave":
        machine["nodes"][5]["delay"] = 3
        machine["links"].append({"source": "n5", "target": "n1", "relation": "supports"})
    return machine, inputs


def machine_ids(machine):
    # V3's frozen structural validation is shared; V4 advances independently.
    return _validate(machine, {"pulse_ticks": [0], "phase": 0}, [], SEGMENT)


def initial_checkpoint(machine, inputs):
    machine_ids(machine)
    if (not isinstance(inputs, dict) or set(inputs) != {"pulse_ticks", "phase"}
            or not isinstance(inputs["pulse_ticks"], list) or len(inputs["pulse_ticks"]) > TICKS
            or any(type(t) is not int or not 0 <= t < TICKS for t in inputs["pulse_ticks"])
            or inputs["pulse_ticks"] != sorted(set(inputs["pulse_ticks"]))
            or type(inputs["phase"]) is not int or inputs["phase"] not in (0, 1)):
        raise ValueError("invalid input schedule")
    value = -1 if inputs["phase"] else 1
    return {"checkpoint_version": 1, "next_tick": 0,
            "reservoirs": {n["id"]: 0 for n in machine["nodes"] if n["kind"] == "reservoir"},
            "gate_open": False, "pending": [],
            "remaining_inputs": [{"tick": t, "value": value, "kind": "input"} for t in inputs["pulse_ticks"]],
            "history": [], "cycle": None}


def validate_checkpoint(machine, checkpoint):
    ids = machine_ids(machine)
    required = {"checkpoint_version", "next_tick", "reservoirs", "gate_open", "pending", "remaining_inputs", "history", "cycle"}
    if not isinstance(checkpoint, dict) or set(checkpoint) != required:
        raise ValueError("invalid checkpoint fields")
    if type(checkpoint["checkpoint_version"]) is not int or checkpoint["checkpoint_version"] != 1:
        raise ValueError("unsupported checkpoint version")
    tick = checkpoint["next_tick"]
    if type(tick) is not int or not 0 <= tick <= TICKS or type(checkpoint["gate_open"]) is not bool:
        raise ValueError("invalid checkpoint cursor or gate")
    stores = {n["id"] for n in machine["nodes"] if n["kind"] == "reservoir"}
    if (not isinstance(checkpoint["reservoirs"], dict) or set(checkpoint["reservoirs"]) != stores
            or any(type(v) is not int or not -CAPACITY <= v <= CAPACITY for v in checkpoint["reservoirs"].values())):
        raise ValueError("invalid reservoir checkpoint")
    pending = checkpoint["pending"]
    if not isinstance(pending, list) or len(pending) > 6 * MAX_NODES:
        raise ValueError("invalid pending queue")
    seen = set()
    for pulse in pending:
        if (not isinstance(pulse, dict) or set(pulse) != {"offset", "target", "value"}
                or type(pulse["offset"]) is not int or not 0 <= pulse["offset"] <= 5
                or pulse["target"] not in ids or type(pulse["value"]) is not int or pulse["value"] == 0):
            raise ValueError("invalid pending pulse")
        key = (pulse["offset"], pulse["target"])
        if key in seen:
            raise ValueError("duplicate pending pulse")
        seen.add(key)
    inputs = checkpoint["remaining_inputs"]
    if not isinstance(inputs, list) or len(inputs) > TICKS:
        raise ValueError("invalid remaining input schedule")
    previous = -1
    for pulse in inputs:
        if (not isinstance(pulse, dict) or set(pulse) != {"tick", "value", "kind"}
                or type(pulse["tick"]) is not int or not tick <= pulse["tick"] < TICKS
                or pulse["tick"] < previous or type(pulse["value"]) is not int
                or pulse["value"] not in (-1, 1) or pulse["kind"] not in ("input", "tap")):
            raise ValueError("invalid remaining input")
        previous = pulse["tick"]
    history = checkpoint["history"]
    if not isinstance(history, list) or len(history) > TICKS:
        raise ValueError("invalid cycle history")
    previous = -1
    for entry in history:
        if (not isinstance(entry, dict) or set(entry) != {"tick", "signature", "emitted"}
                or type(entry["tick"]) is not int or not previous < entry["tick"] <= tick
                or not isinstance(entry["signature"], str) or len(entry["signature"]) != 64
                or type(entry["emitted"]) is not bool):
            raise ValueError("invalid cycle evidence")
        previous = entry["tick"]
    cycle = checkpoint["cycle"]
    if cycle is not None:
        if (not isinstance(cycle, dict) or set(cycle) != {"period", "detected_at", "first_seen_at", "conditions"}
                or type(cycle["period"]) is not int or cycle["period"] < 1
                or type(cycle["detected_at"]) is not int or not cycle["period"] <= cycle["detected_at"] <= tick
                or type(cycle["first_seen_at"]) is not int
                or cycle["detected_at"] - cycle["first_seen_at"] != cycle["period"]
                or not isinstance(cycle["conditions"], str)):
            raise ValueError("invalid cycle certificate")
    return ids


def remaining_activity(checkpoint):
    return bool(checkpoint["pending"] or checkpoint["remaining_inputs"] or any(checkpoint["reservoirs"].values()))


def waiting_for_release(checkpoint):
    return bool(not checkpoint["gate_open"] and any(checkpoint["reservoirs"].values())
                and not checkpoint["pending"] and not checkpoint["remaining_inputs"])


def _event(tick, kind, node, message, **fields):
    return {"tick": tick, "kind": kind, "node": node, "message": message, **fields}


def apply_control(machine, checkpoint, control):
    """Apply an immediate control at the checkpoint cursor without advancing."""
    validate_checkpoint(machine, checkpoint)
    if not isinstance(control, dict) or set(control) != {"tick", "type"}:
        raise ValueError("invalid control fields")
    if type(control["tick"]) is not int or control["tick"] != checkpoint["next_tick"] or control["tick"] >= TICKS:
        raise ValueError("control must apply at the next unprocessed tick")
    if control["type"] not in ("release", "tap"):
        raise ValueError("unknown control")
    updated, events = deepcopy(checkpoint), []
    if control["type"] == "release":
        if updated["gate_open"]:
            raise ValueError("gate is already open")
        updated["gate_open"] = True
        events.extend(_event(control["tick"], "release", node_id, "蓄积门已打开；尚未推进下一拍") for node_id in updated["reservoirs"])
    else:
        updated["remaining_inputs"].append({"tick": control["tick"], "value": 1, "kind": "tap"})
        updated["remaining_inputs"].sort(key=lambda p: p["tick"])
    updated["history"], updated["cycle"] = [], None
    return updated, events


def _signature(checkpoint):
    content = {"reservoirs": checkpoint["reservoirs"], "gate_open": checkpoint["gate_open"],
               "pending": checkpoint["pending"],
               "remaining_inputs": [{**p, "tick": p["tick"] - checkpoint["next_tick"]} for p in checkpoint["remaining_inputs"]]}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _cycle_observation(checkpoint, emitted):
    if checkpoint["remaining_inputs"] or not checkpoint["gate_open"]:
        checkpoint["history"], checkpoint["cycle"] = [], None
        return None
    signature = _signature(checkpoint)
    evidence = checkpoint["history"]
    entry = {"tick": checkpoint["next_tick"], "signature": signature, "emitted": emitted}
    detected = None
    if checkpoint["cycle"] is None:
        for index in range(len(evidence) - 1, -1, -1):
            old = evidence[index]
            if old["signature"] == signature and (emitted or any(e["emitted"] for e in evidence[index + 1:])):
                detected = {"period": entry["tick"] - old["tick"], "detected_at": entry["tick"], "first_seen_at": old["tick"],
                            "conditions": "固定捕获机器；门保持打开；没有待注入输入；完整存量与相对待传播队列重复；期间有非零响应。新输入或控制会清除认证。"}
                checkpoint["cycle"] = detected
                break
    checkpoint["history"] = (evidence + [entry])[-TICKS:]
    return detected


def advance(machine, checkpoint, ticks, controls=None):
    """Advance a true checkpoint; only newly processed frames are returned."""
    ids = validate_checkpoint(machine, checkpoint)
    if type(ticks) is not int or ticks < 0 or checkpoint["next_tick"] + ticks > TICKS:
        raise ValueError("advance exceeds the bounded 96-tick run")
    controls = deepcopy([] if controls is None else controls)
    if not isinstance(controls, list) or len(controls) > TICKS:
        raise ValueError("invalid controls")
    start, end = checkpoint["next_tick"], checkpoint["next_tick"] + ticks
    previous = start - 1
    for control in controls:
        if (not isinstance(control, dict) or set(control) != {"tick", "type"}
                or type(control["tick"]) is not int or not start <= control["tick"] <= end
                or control["tick"] < previous or control["type"] not in ("release", "tap")):
            raise ValueError("invalid advance control")
        previous = control["tick"]
    updated, frames, events = deepcopy(checkpoint), [], []
    outgoing = {node_id: [] for node_id in ids}
    for link in machine["links"]:
        outgoing[link["source"]].append(link)
    pending = {}
    for pulse in updated["pending"]:
        pending[(start + pulse["offset"], pulse["target"])] = pulse["value"]
    control_index = 0
    for tick in range(start, end):
        while control_index < len(controls) and controls[control_index]["tick"] == tick:
            updated, emitted_events = apply_control(machine, updated, controls[control_index])
            events.extend(emitted_events)
            control_index += 1
        arriving_inputs = [p for p in updated["remaining_inputs"] if p["tick"] == tick]
        updated["remaining_inputs"] = [p for p in updated["remaining_inputs"] if p["tick"] != tick]
        for pulse in arriving_inputs:
            key = (tick, machine["source"])
            pending[key] = pending.get(key, 0) + pulse["value"]
            label = "新敲击" if pulse["kind"] == "tap" else "输入脉冲"
            events.append(_event(tick, pulse["kind"], machine["source"], f"{label} {pulse['value']:+d}", value=pulse["value"]))
        values = {}
        for node in machine["nodes"]:
            node_id = node["id"]
            incoming = pending.pop((tick, node_id), 0)
            if node["kind"] == "reservoir":
                before = updated["reservoirs"][node_id]
                combined = before + incoming
                stored = _clip(combined, CAPACITY)
                if combined != stored:
                    events.append(_event(tick, "overflow", node_id, f"容量截断，丢弃 {combined - stored:+d}", discarded=combined - stored))
                value = _clip(stored) if updated["gate_open"] else 0
                updated["reservoirs"][node_id] = stored - value
                if incoming or value:
                    events.append(_event(tick, "reservoir", node_id, f"存量 {before} → {stored - value}", before=before, after=stored - value, incoming=incoming, emitted=value))
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
            kind = "output" if node_id == machine["output"] else "response"
            message = f"输出 {value:+d}" if kind == "output" else f"节点 {node_id} 响应 {value:+d}"
            events.append(_event(tick, kind, node_id, message, value=value))
            for link in outgoing[node_id]:
                when = tick + 1 + node.get("delay", 0) + int(link["relation"] == "reflects")
                sent = value if link["relation"] == "supports" else -value
                key = (when, link["target"])
                pending[key] = pending.get(key, 0) + sent
                if node["kind"] == "echo":
                    key = (when + 1, link["target"])
                    pending[key] = pending.get(key, 0) + (1 if sent > 0 else -1)
        updated["next_tick"] = tick + 1
        updated["pending"] = [{"offset": when - updated["next_tick"], "target": target, "value": value}
                              for (when, target), value in sorted(pending.items()) if value]
        pending = {(updated["next_tick"] + p["offset"], p["target"]): p["value"] for p in updated["pending"]}
        detected = _cycle_observation(updated, any(values.values()))
        if detected:
            events.append(_event(tick, "cycle", machine["output"], f"完整状态已重复，周期 {detected['period']} 拍", period=detected["period"]))
        frames.append({"tick": tick, "values": values, "reservoirs": deepcopy(updated["reservoirs"]), "gate_open": updated["gate_open"]})
    while control_index < len(controls):
        updated, emitted_events = apply_control(machine, updated, controls[control_index])
        events.extend(emitted_events)
        control_index += 1
    validate_checkpoint(machine, updated)
    return {"checkpoint": updated, "frames": frames, "events": events}
