"""Dynamic shared world: infer, construct, perform and freely replay real traces."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import random

from .dynamics import KINDS, MAX_NODES, RELATIONS, TICKS, initial_machine, machine_digest, simulate
from .errors import GameError

MODES = ("pattern", "creation", "resonance")
EMPTY = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
MAX_SAVED = 6


def _integer(value):
    return type(value) is int


def _fail(message, code="INVALID_ACTION"):
    raise GameError(code, message)


def _schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _enum(values, kind="string"):
    return {"type": kind, "enum": list(values)}


def _range(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


def _action(kind, cost=0, target=None, parameters=None, description=""):
    result = {"type": kind, "cost": cost, "parameters": deepcopy(parameters or EMPTY), "description": description}
    if target is not None:
        result["target"] = target
    return result


def _library(entries):
    """Accept trusted stored snapshots, copying only documented visible fields."""
    if entries is None:
        return []
    if not isinstance(entries, list):
        _fail("library must be a list", "INVALID_CONFIG")
    unique = {}
    for item in entries[-MAX_SAVED:]:
        try:
            if not isinstance(item["id"], str) or len(item["id"]) > 120 or item["mode"] not in MODES:
                raise ValueError("invalid saved identity")
            replayed = simulate(item["machine"], item["inputs"])
            if replayed["trace_hash"] != item["trace_hash"]:
                raise ValueError("saved trace mismatch")
            cleaned = {key: deepcopy(item[key]) for key in ("id", "mode", "label", "origin_session_id", "created_turn", "machine", "inputs", "trace_hash", "summary")}
            unique[cleaned["id"]] = cleaned
        except (KeyError, TypeError, ValueError):
            _fail("Stored experience is invalid or belongs to incompatible dynamics", "INVALID_LIBRARY")
    return list(unique.values())[-MAX_SAVED:]


def create_state(*, session_id, player_id, model_id, seed=0, max_turns=24, mode="normal", condition="control", preferences=None, library=None):
    if not _integer(seed) or not -(2**63) <= seed < 2**63:
        _fail("seed must be a signed 64-bit integer", "INVALID_CONFIG")
    if not _integer(max_turns) or not 20 <= max_turns <= 30:
        _fail("max_turns must be 20..30", "INVALID_CONFIG")
    if mode not in ("normal", "research") or condition not in ("control", "personalized"):
        _fail("Unknown mode or condition", "INVALID_CONFIG")
    rng = random.Random(seed)
    rooms = {f"{name}_1": {"id": f"{name}_1", "mode": name,
             "label": {"pattern": "规律观测", "creation": "构造工作区", "resonance": "过程演奏"}[name],
             "completed": False, "visits": 0, "replays": 0} for name in MODES}
    order = list(rooms)
    rng.shuffle(order)
    weights = {name: 0 for name in MODES}
    if condition == "personalized" and isinstance(preferences, dict):
        for name in MODES:
            value = preferences.get(name, 0)
            if type(value) in (float, int) and abs(value) < 1e10:
                weights[name] = value
        order.sort(key=lambda key: -weights[rooms[key]["mode"]])
    return {
        "engine_version": 2, "session_id": session_id, "player_id": player_id, "model_id": model_id,
        "state_version": 0, "turn": 0, "state": "playing", "max_turns": max_turns,
        "mode": mode, "condition": condition, "seed": seed, "resources": {"energy": 24},
        "active_target": None, "preferences_snapshot": weights, "last_outcome": None,
        "end_reason": None, "replay_streak": 0,
        "world": {"experiences": rooms, "order": order, "machine": initial_machine(rng.randint(1, 3)),
                  "inputs": {"period": 4, "phase": 0}, "edits": 0, "creations": [],
                  "performance": None, "saved_experiences": _library(library),
                  "discoveries": [], "probe": None},
    }


def export_library(state):
    return deepcopy(state["world"]["saved_experiences"][-MAX_SAVED:])


def _saved_view(record):
    return {key: deepcopy(record[key]) for key in ("id", "mode", "label", "origin_session_id", "created_turn", "inputs", "trace_hash", "summary")}


def _room_view(state, target):
    if not target:
        return None
    world = state["world"]
    room = deepcopy(world["experiences"][target])
    if room["mode"] == "creation":
        room.update({"nodes": deepcopy(world["machine"]["nodes"]), "links": deepcopy(world["machine"]["links"]), "edits": world["edits"], "relations": list(RELATIONS), "node_limit": MAX_NODES})
    elif room["mode"] == "pattern":
        room.update({"question": "For a single phase-zero pulse at n0, at which tick does n2 first emit a nonzero value? Use 20 if it never emits within 20 ticks.",
                     "answer_bounds": [0, TICKS], "probe": deepcopy(world["probe"]),
                     "machine_revision": world["machine"]["revision"],
                     "probe_is_current": bool(world["probe"] and world["probe"]["machine_revision"] == world["machine"]["revision"])})
    else:
        room.update({"inputs": deepcopy(world["inputs"]), "performance": deepcopy(world["performance"]),
                     "purpose": "Run the shared machine, capture a process, replay it exactly, or fork one input."})
    return room


def available_actions(state):
    if state["state"] != "playing":
        return []
    world, energy = state["world"], state["resources"]["energy"]
    actions = [_action("leave", description="End this session voluntarily.")]
    active = state["active_target"]
    for target in world["order"]:
        if target != active:
            actions.append(_action("enter", target=target, description="Enter this part of the same persistent world for free."))
    for saved in world["saved_experiences"]:
        if energy >= 2 and state["replay_streak"] < 2:
            actions.append(_action("replay", 2, saved["id"], description="Immediately reproduce this saved process, with no graph reset, new unlock, or rebuilding."))
        if energy >= 2:
            actions.append(_action("fork", 2, saved["id"], _schema({"period": _enum([n for n in range(2, 7) if n != saved["inputs"]["period"]], "integer")}), "Change exactly the captured input period and run a new, separately labelled process."))
        if energy >= 1:
            actions.append(_action("restore", 1, saved["id"], description="Load this captured graph for continued construction. This is not exact replay."))
    creation = world["experiences"]["creation_1"]
    if creation["completed"] and energy >= 1:
        actions.append(_action("revise", 1, "creation_1", description="Reopen the existing graph without losing its archived revisions."))
    if active is None:
        return actions
    room = world["experiences"][active]
    actions.append(_action("abandon", target=active, description="Leave this activity; the shared machine and saved experiences remain."))
    if energy < 1:
        return actions
    if room["mode"] == "pattern":
        answer = _schema({"answer": _range(0, TICKS)})
        actions += [_action("inspect", 1, active, description="Send one phase-zero probe through the current shared machine and observe its real trace."),
                    _action("hypothesize", 1, active, answer, "Test the current machine's first-arrival tick at n2."),
                    _action("complete", 1, active, answer, "Record the exact first-arrival rule for this machine revision.")]
    if room["mode"] == "creation" and not room["completed"]:
        ids = [node["id"] for node in world["machine"]["nodes"]]
        pair = _schema({"left": _enum(ids), "right": _enum(ids), "relation": _enum(RELATIONS)})
        if len(ids) < MAX_NODES:
            actions.append(_action("combine", 1, active, pair, "Create a merge node receiving pulses from two existing nodes."))
        actions += [_action("connect", 1, active, pair, "Add or replace a causal signal link; the preview is recomputed."),
                    _action("transform", 1, active, _schema({"node": _enum(ids), "operation": _enum(("invert",))}), "Change phase and recompute the downstream signal process."),
                    _action("tune", 1, active, _schema({"node": _enum(ids), "delay": _range(0, 3), "phase": _range(0, 1)}), "Set the node's delay and phase, then preview the resulting process."),
                    _action("reshape", 1, active, _schema({"node": _enum(ids), "kind": _enum(KINDS), "threshold": _range(1, 4)}), "Give a node a causal role: mirror, delay, echo, gate or merge.")]
        if world["edits"]:
            actions.append(_action("seal", 1, active, description="Archive this graph revision without clearing its working state."))
    if room["mode"] in ("creation", "resonance"):
        actions.append(_action("perform", 1, active, _schema({"period": _range(2, 6), "phase": _range(0, 1)}), "Run 20 bounded ticks and save this exact machine/input process for future one-action replay."))
    return actions


def observe(state):
    world = state["world"]
    return {
        **{key: deepcopy(state[key]) for key in ("engine_version", "session_id", "player_id", "model_id", "state_version", "turn", "state", "max_turns", "mode", "condition", "resources", "active_target", "last_outcome", "end_reason")},
        "observation": {
            "catalog": [deepcopy(world["experiences"][key]) for key in world["order"]],
            "active_experience": _room_view(state, state["active_target"]),
            "machine": deepcopy(world["machine"]), "performance": deepcopy(world["performance"]),
            "saved_experiences": [_saved_view(record) for record in world["saved_experiences"]],
            "creations": deepcopy(world["creations"]), "discoveries": deepcopy(world["discoveries"]),
            "discovered_experiences": [_room_view(state, key) for key in world["order"] if world["experiences"][key]["visits"]],
        },
        "available_actions": available_actions(state),
        "constraints": {"replay_cost": 2, "fork_cost": 2, "revision_cost": 1,
                        "replay_streak_limit": 2, "saved_process_limit": MAX_SAVED,
                        "machine_node_limit": MAX_NODES, "simulation_ticks": TICKS,
                        "energy_gains": 0, "end_conditions": ["voluntary leave", "turn limit"],
                        "streak_reset": "Enter a different activity, or alter, probe or perform the shared machine."},
    }


def _validate(params, schema):
    if not isinstance(params, dict):
        _fail("params must be an object")
    props = schema.get("properties", {})
    if set(params) != set(schema.get("required", [])):
        _fail("Unknown or missing action parameter")
    for key, value in params.items():
        spec = props[key]
        if spec["type"] == "integer":
            if not _integer(value) or not spec.get("minimum", value) <= value <= spec.get("maximum", value):
                _fail("Invalid integer parameter: " + key)
        elif not isinstance(value, str):
            _fail("Invalid string parameter: " + key)
        if "enum" in spec and value not in spec["enum"]:
            _fail("Parameter outside advertised enum: " + key)


def _first_arrival(machine):
    result = simulate(machine, {"period": 0, "phase": 0})
    answer = next((frame["tick"] for frame in result["frames"] if frame["values"].get("n2", 0)), TICKS)
    return answer, result


def _performance(state, machine, inputs, *, origin, mode, save=False):
    result = simulate(machine, inputs)
    result.update({"origin": origin, "mode": mode, "machine_revision": machine["revision"]})
    if save:
        prefix = hashlib.sha256(state["session_id"].encode()).hexdigest()[:16]
        record_id = f"perf_{prefix}_{state['turn']}"
        result["id"] = record_id
        record = {"id": record_id, "mode": mode, "label": f"{mode} · period {inputs['period']} · revision {machine['revision']}",
                  "origin_session_id": state["session_id"], "created_turn": state["turn"],
                  "machine": deepcopy(machine), "inputs": deepcopy(inputs), "trace_hash": result["trace_hash"],
                  "summary": deepcopy(result["summary"])}
        state["world"]["saved_experiences"].append(record)
        state["world"]["saved_experiences"] = state["world"]["saved_experiences"][-MAX_SAVED:]
    state["world"]["performance"] = result
    return result


def _switch(state, target, outcome):
    previous = state["active_target"]
    rooms = state["world"]["experiences"]
    if previous and previous != target and not rooms[previous]["completed"]:
        outcome["abandoned_mode"] = rooms[previous]["mode"]
    state["active_target"] = target


def transition(state, action):
    if state["state"] != "playing":
        raise GameError("SESSION_ENDED", "This session has already ended", status=409)
    if not isinstance(action, dict) or set(action) - {"type", "target", "params"} or not isinstance(action.get("type"), str):
        _fail("Action must contain type and optional target/params only")
    if "target" in action and not isinstance(action["target"], str):
        _fail("target must be a string")
    descriptor = next((a for a in available_actions(state) if a["type"] == action["type"] and a.get("target") == action.get("target")), None)
    if descriptor is None:
        _fail("Action is not currently available")
    params = action.get("params", {})
    _validate(params, descriptor["parameters"])
    updated = deepcopy(state)
    world = updated["world"]
    kind, target = action["type"], action.get("target")
    updated["turn"] += 1
    updated["state_version"] += 1
    updated["resources"]["energy"] -= descriptor["cost"]
    outcome = {"kind": kind, "cost": descriptor["cost"]}
    if target:
        outcome["target"] = target
    active = updated["active_target"]
    room = world["experiences"].get(active)
    if room:
        outcome["mode"] = room["mode"]
    if kind != "replay":
        updated["replay_streak"] = 0
    if kind == "leave":
        outcome.pop("mode", None)
        updated["state"] = "ended"
        updated["end_reason"] = "voluntary_leave"
    elif kind in ("enter", "revise"):
        _switch(updated, target, outcome)
        room = world["experiences"][target]
        room["visits"] += 1
        outcome["mode"] = room["mode"]
        if kind == "enter":
            outcome.update({"kind": "selection", "novel": room["visits"] == 1})
        else:
            room["completed"] = False
        outcome["result"] = _room_view(updated, target)
    elif kind == "abandon":
        updated["active_target"] = None
    elif kind in ("replay", "fork", "restore"):
        saved = next(record for record in world["saved_experiences"] if record["id"] == target)
        outcome["mode"] = saved["mode"]
        if kind == "restore":
            revision = world["machine"]["revision"] + 1
            world["machine"] = deepcopy(saved["machine"])
            world["machine"]["revision"] = revision
            world["edits"] += 1
            world["experiences"]["creation_1"]["completed"] = False
            world["experiences"]["creation_1"]["visits"] += 1
            _switch(updated, "creation_1", outcome)
            result = _performance(updated, world["machine"], world["inputs"], origin="preview", mode="creation")
            outcome["restored_from"] = target
        elif kind == "replay":
            result = _performance(updated, saved["machine"], saved["inputs"], origin="replay", mode=saved["mode"])
            result["id"] = saved["id"]
            if result["trace_hash"] != saved["trace_hash"]:
                raise GameError("SAVED_PROCESS_MISMATCH", "Captured process no longer matches its stored trace", status=409)
            updated["replay_streak"] += 1
            world["experiences"][saved["mode"] + "_1"]["replays"] += 1
            outcome["exact_repeat"] = True
        else:
            inputs = {**saved["inputs"], "period": params["period"]}
            result = _performance(updated, saved["machine"], inputs, origin="fork", mode=saved["mode"], save=True)
            outcome.update({"forked_from": target, "changed_field": "period"})
        outcome.update({"performance": deepcopy(result), "summary": deepcopy(result["summary"])})
    elif kind in ("inspect", "hypothesize", "complete"):
        answer, result = _first_arrival(world["machine"])
        if kind == "inspect":
            result.update({"origin": "probe", "mode": "pattern", "machine_revision": world["machine"]["revision"]})
            world["probe"] = deepcopy(result)
            world["performance"] = result
            outcome["performance"] = deepcopy(result)
        else:
            correct = params["answer"] == answer
            outcome.update({"answer": params["answer"], "correct": correct})
            if kind == "complete" and correct:
                room["completed"] = True
                discovery = {"kind": "first_arrival", "node": "n2", "tick": answer,
                             "machine_revision": world["machine"]["revision"], "machine_hash": machine_digest(world["machine"])}
                if discovery not in world["discoveries"]:
                    world["discoveries"].append(discovery)
                outcome.update({"completed": True, "discovery": discovery})
    elif kind == "perform":
        world["inputs"] = deepcopy(params)
        result = _performance(updated, world["machine"], params, origin="perform", mode=room["mode"], save=True)
        if room["mode"] == "resonance":
            room["completed"] = True
        outcome.update({"performance": deepcopy(result), "saved_id": result["id"], "summary": deepcopy(result["summary"])})
    elif kind == "seal":
        room["completed"] = True
        archive = {"target": target, "revision": world["machine"]["revision"], "turn": updated["turn"],
                   "nodes": deepcopy(world["machine"]["nodes"]), "links": deepcopy(world["machine"]["links"])}
        world["creations"].append(archive)
        world["creations"] = world["creations"][-MAX_SAVED:]
        outcome.update({"completed": True, "archive_index": len(world["creations"]) - 1})
    else:
        machine = world["machine"]
        nodes = {node["id"]: node for node in machine["nodes"]}
        if kind in ("combine", "connect"):
            left, right, relation = params["left"], params["right"], params["relation"]
            if kind == "combine":
                node_id = "n" + str(len(nodes))
                a, b = nodes[left], nodes[right]
                node = {"id": node_id, "concept": f"({a['concept']} {relation} {b['concept']})"[:160],
                        "kind": "merge", "phase": 0, "delay": 0, "threshold": 1,
                        "depth": max(a.get("depth", 0), b.get("depth", 0)) + 1}
                machine["nodes"].append(node)
                for source in dict.fromkeys((left, right)):
                    machine["links"].append({"source": source, "target": node_id, "relation": relation})
                outcome["created_node"] = deepcopy(node)
            else:
                machine["links"] = [edge for edge in machine["links"] if (edge["source"], edge["target"]) != (left, right)]
                machine["links"].append({"source": left, "target": right, "relation": relation})
                outcome["connection"] = {"source": left, "target": right, "relation": relation}
        elif kind == "transform":
            node = nodes[params["node"]]
            node["phase"] = 1 - node["phase"]
            outcome["transformed_node"] = deepcopy(node)
        elif kind == "tune":
            node = nodes[params["node"]]
            node.update({"delay": params["delay"], "phase": params["phase"]})
            outcome["tuned_node"] = deepcopy(node)
        elif kind == "reshape":
            node = nodes[params["node"]]
            node.update({"kind": params["kind"], "threshold": params["threshold"]})
            outcome["reshaped_node"] = deepcopy(node)
        else:
            _fail("Unsupported action")
        machine["revision"] += 1
        world["edits"] += 1
        result = _performance(updated, machine, world["inputs"], origin="preview", mode="creation")
        outcome.update({"performance": deepcopy(result), "summary": deepcopy(result["summary"])})
    if updated["turn"] >= updated["max_turns"] and updated["state"] == "playing":
        updated["state"] = "ended"
        updated["end_reason"] = "turn_limit"
    updated["last_outcome"] = outcome
    return updated, outcome


def rules():
    return {
        "game": "PORN", "rules_version": 2, "engine_version": 2, "protocol_version": 1,
        "purpose": "Study free behavior in a shared causal world; no subjective pleasure or hidden activations are inferred.",
        "world": {"areas": {"pattern_1": "Probe and infer the current machine's response timing.", "creation_1": "Build, connect and tune a persistent pulse machine.", "resonance_1": "Perform, save, replay or vary the same machine's processes."},
                  "shared_state": "All areas use one machine. Edits affect future probes and performances. Previous captured processes remain immutable."},
        "resources": {"initial_energy": 24, "energy_gains": 0, "enter": 0, "leave": 0, "abandon": 0,
                      "stimulus_action": 1, "replay": 2, "fork": 2, "revise": 1, "restore": 1},
        "machine": {"node_limit": MAX_NODES, "ticks_per_process": TICKS, "amplitude_bounds": [-4, 4],
                    "node_roles": {"mirror": "Invert incoming pulse before routing.", "delay": "Route after the configured delay.", "echo": "Route normal pulse plus one unit-amplitude copy one tick later.", "gate": "Emit only when the incoming magnitude reaches threshold.", "merge": "Combine incoming pulses, clipping magnitude to four."},
                    "phase": "Phase is binary: 0 preserves and 1 inverts the emitted sign. transform/invert toggles it.",
                    "relations": {"supports": "Carry unchanged.", "tensions": "Invert sign.", "reflects": "Invert sign and add one tick delay."},
                    "routing": "Every edge takes one tick plus the source node's delay; echoes add a second copy one tick later. Cycles are simulated with a finite queue.",
                    "input": {"period": [2, 6], "phase": [0, 1], "probe_period": 0}},
        "actions": {"inspect": "Single phase-zero pulse. See frames and infer the first tick n2 emits; answer20 means not observed in the 20-tick horizon.",
                    "complete": "Validate against the exact current shared machine and record the rule with its revision.",
                    "perform": "Capture a real finite process with its machine and inputs.",
                    "replay": "One paid action reproduces a captured process exactly, preserving the current working graph. No rebuilding, new reward or content.",
                    "fork": "One paid action changes only a captured input period and stores a new process. Count separately from exact replay.",
                    "restore": "Load a captured graph for further edits; separate from exact replay.",
                    "revise": "Reopen a sealed working graph for continued construction."},
        "persistence": {"captured_process_limit": MAX_SAVED, "cross_session_library": "Up to six same-identity visible captured machine/input snapshots can be loaded by the service.", "normal_visibility": "Generated seed is hidden; the built graph, public execution rules, discovered response traces and saved process summaries are visible."},
        "metrics": {"cycle_period": "Observed repeated output vectors in the final twelve ticks, not a proven infinite attractor.", "peak_activity": "Largest count of nonzero node outputs at one tick; not a reward or pleasure score."},
        "loop": ["observe", "choose any advertised action", "submit expected_version with action", "inspect real state change", "continue, change direction or leave"],
        "end_conditions": {"default_max_turns": 24, "max_turns_range": [20, 30], "leave": "Free at every playing turn", "zero_energy": "Free navigation and leave remain available"},
    }
