"""Bounded reservoir performances and independent exact/familiar choices."""
from __future__ import annotations

from copy import deepcopy
import hashlib

from . import engine_v2
from .dynamics_v3 import (CHUNK, DEFAULT_INPUTS, KINDS, MAX_NODES, OBSERVATION_VERSION,
                          RELEASE_TICKS, RELATIONS, RULES_VERSION, TICKS, initial_machine, simulate)
from .engine_v2 import (_action, _enum, _fail, _range, _schema, _validate, MAX_SAVED, MODES)
from .errors import GameError

_SAVED_FIELDS = ("id", "mode", "label", "origin_session_id", "created_turn", "engine_version",
                 "rules_version", "observation_version", "machine", "inputs", "control_script",
                 "duration", "stopped", "trace_hash", "summary")


def _library(entries):
    if entries is None:
        return []
    if not isinstance(entries, list):
        _fail("library must be a list", "INVALID_CONFIG")
    saved = {}
    for entry in entries[-MAX_SAVED:]:
        try:
            if (not isinstance(entry, dict) or type(entry["engine_version"]) is not int or entry["engine_version"] != 3
                    or type(entry["rules_version"]) is not int or entry["rules_version"] != RULES_VERSION
                    or type(entry["observation_version"]) is not int or entry["observation_version"] != OBSERVATION_VERSION
                    or not isinstance(entry["id"], str) or len(entry["id"]) > 120 or entry["mode"] not in MODES):
                raise ValueError("incompatible saved experience")
            if (not isinstance(entry["label"], str) or not isinstance(entry["origin_session_id"], str)
                    or type(entry["created_turn"]) is not int or entry["created_turn"] < 0):
                raise ValueError("invalid saved provenance")
            result = simulate(entry["machine"], entry["inputs"], entry["control_script"],
                              ticks=entry["duration"], stopped=entry["stopped"])
            if result["trace_hash"] != entry["trace_hash"] or result["summary"] != entry["summary"]:
                raise ValueError("saved content mismatch")
            saved[entry["id"]] = {key: deepcopy(entry[key]) for key in _SAVED_FIELDS}
        except (KeyError, TypeError, ValueError):
            _fail("Stored experience is invalid or belongs to incompatible rules", "INVALID_LIBRARY")
    return list(saved.values())[-MAX_SAVED:]


def create_state(*, session_id, player_id, model_id, seed=0, max_turns=24, mode="normal", condition="control", preferences=None, library=None):
    # Reuse the frozen V2 lifecycle/config validator, never its transition or simulator.
    state = engine_v2.create_state(session_id=session_id, player_id=player_id, model_id=model_id,
                                  seed=seed, max_turns=max_turns, mode=mode, condition=condition, preferences=preferences)
    state.update({"engine_version": 3, "rules_version": RULES_VERSION, "observation_version": OBSERVATION_VERSION})
    state.pop("replay_streak")
    state["world"].update({"machine": initial_machine(), "inputs": deepcopy(DEFAULT_INPUTS),
                           "saved_experiences": _library(library)})
    return state


def export_library(state):
    return deepcopy(state["world"]["saved_experiences"][-MAX_SAVED:])


def _running(state):
    process = state["world"]["performance"]
    return bool(process and process["experience"]["state"] == "running")


def _room_view(state, target):
    if target is None:
        return None
    world = state["world"]
    room = deepcopy(world["experiences"][target])
    if room["mode"] == "creation":
        room.update({"nodes": deepcopy(world["machine"]["nodes"]), "links": deepcopy(world["machine"]["links"]),
                     "edits": world["edits"], "relations": list(RELATIONS), "node_limit": MAX_NODES})
    elif room["mode"] == "pattern":
        room.update({"probe": deepcopy(world["probe"]), "purpose": "Inspect the current machine with a release at tick eight; this is not required before playing."})
    else:
        room.update({"inputs": deepcopy(world["inputs"]),
                     "purpose": "Wait, release and observe a finite captured performance, or leave freely."})
    return room


def available_actions(state):
    if state["state"] != "playing":
        return []
    world, energy, active = state["world"], state["resources"]["energy"], state["active_target"]
    actions = [_action("leave", description="End this session for free; any running prefix is saved as stopped.")]
    if _running(state):
        process = world["performance"]
        if process["experience"]["gate_open"]:
            actions.append(_action("continue", target=active, description="Advance the existing process by four ticks without another energy cost."))
        else:
            actions += [_action("wait", target=active, description="Advance four ticks while keeping the reservoir closed."),
                        _action("release", target=active, description="Open the reservoir before the next tick and advance four ticks.")]
        actions.append(_action("stop", target=active, description="Stop now for free and save this finite prefix, including any remaining signal."))
        return actions
    for target in world["order"]:
        if target != active:
            actions.append(_action("enter", target=target, description="Enter this part of the same world for free."))
    enough_turns = state["max_turns"] - state["turn"] >= TICKS // CHUNK
    for saved in world["saved_experiences"]:
        if energy >= 2:
            actions.append(_action("replay", 2, saved["id"], description="One action reproduces this exact captured duration and controls, without editing the working machine."))
            if saved["duration"] == TICKS and not saved["stopped"]:
                alternatives = [t for t in RELEASE_TICKS if not saved["control_script"] or t != saved["control_script"][0]["tick"]]
                actions.append(_action("fork", 2, saved["id"], _schema({"release_tick": _enum(alternatives, "integer")}),
                                       "Change only the release timing and run a complete 24-tick variation; recorded separately from exact replay."))
            if enough_turns:
                actions.append(_action("reperform", 2, saved["id"], description="Start the captured work from its initial state; choose the release time again. This is familiar interaction, not exact repeat."))
        if energy >= 1:
            actions.append(_action("restore", 1, saved["id"], description="Restore this captured graph for construction without changing the saved process."))
    creation = world["experiences"]["creation_1"]
    if creation["completed"] and energy >= 1:
        actions.append(_action("revise", 1, "creation_1", description="Reopen the sealed working graph for further construction."))
    if active is None:
        return actions
    room = world["experiences"][active]
    actions.append(_action("abandon", target=active, description="Leave the area for free; graph and saved processes remain."))
    if room["mode"] in ("creation", "resonance") and energy >= 2:
        actions.append(_action("perform", 2, active, _schema({"release_tick": _enum(RELEASE_TICKS, "integer")}),
                               "Run one complete 24-tick process with a declared release time, for the same energy price as exact replay and variation."))
        if enough_turns:
            actions.append(_action("begin", 2, active, description="Begin interactive performance and execute ticks zero through three. Five more advances can reach tick 24."))
    if energy < 1:
        return actions
    if room["mode"] == "pattern":
        actions.append(_action("inspect", 1, active, description="Inspect a complete tick-eight release response of the current graph, without saving a new performance."))
    if room["mode"] == "creation" and not room["completed"]:
        ids = [n["id"] for n in world["machine"]["nodes"]]
        editable = [n["id"] for n in world["machine"]["nodes"] if n["kind"] != "reservoir"]
        pair = _schema({"left": _enum(ids), "right": _enum(ids), "relation": _enum(RELATIONS)})
        if len(ids) < MAX_NODES:
            actions.append(_action("combine", 1, active, pair, "Add a merge node receiving the chosen existing inputs."))
        actions += [_action("connect", 1, active, pair, "Add or replace one causal connection."),
                    _action("transform", 1, active, _schema({"node": _enum(ids), "operation": _enum(("invert",))}), "Toggle one node phase."),
                    _action("tune", 1, active, _schema({"node": _enum(ids), "delay": _range(0, 3), "phase": _range(0, 1)}), "Set one node's delay and phase."),
                    _action("reshape", 1, active, _schema({"node": _enum(editable), "kind": _enum([k for k in KINDS if k != "reservoir"]), "threshold": _range(1, 4)}), "Change a non-reservoir node's role; the one bounded reservoir is preserved.")]
        if world["edits"]:
            actions.append(_action("seal", 1, active, description="Archive this working graph without removing it."))
    return actions


def observe(state):
    world = state["world"]
    process = world["performance"]
    outcome = deepcopy(state["last_outcome"])
    if outcome:
        outcome.pop("performance", None)
        if "experience" in outcome:
            outcome["experience"].pop("events", None)
    return {**{key: deepcopy(state[key]) for key in ("engine_version", "rules_version", "observation_version", "session_id", "player_id", "model_id", "state_version", "turn", "state", "max_turns", "mode", "condition", "resources", "active_target", "end_reason")},
            "last_outcome": outcome,
            "observation": {"catalog": [deepcopy(world["experiences"][k]) for k in world["order"]],
                            "active_experience": _room_view(state, state["active_target"]),
                            "machine": deepcopy(world["machine"]), "performance": deepcopy(process),
                            "experience": deepcopy(process["experience"]) if process else None,
                            "saved_experiences": [{k: deepcopy(r[k]) for k in _SAVED_FIELDS if k != "machine"} for r in world["saved_experiences"]],
                            "creations": deepcopy(world["creations"]), "discoveries": deepcopy(world["discoveries"]),
                            "discovered_experiences": [_room_view(state, k) for k in world["order"] if world["experiences"][k]["visits"]]},
            "available_actions": available_actions(state),
            "constraints": {"performance_cost": 2, "replay_cost": 2, "fork_cost": 2, "reperform_cost": 2,
                            "advance_cost": 0, "replay_streak_limit": None, "saved_process_limit": MAX_SAVED,
                            "machine_node_limit": MAX_NODES, "simulation_ticks": TICKS, "chunk_ticks": CHUNK,
                            "energy_gains": 0, "end_conditions": ["voluntary leave", "turn limit"]}}


def _set_process(state, machine, inputs, controls, *, duration=TICKS, stopped=False, running=False, origin, mode):
    result = simulate(machine, inputs, controls, ticks=duration, stopped=stopped, running=running)
    result.update({"origin": origin, "mode": mode, "machine_revision": machine["revision"]})
    state["world"]["performance"] = result
    return result


def _save(state, process):
    prefix = hashlib.sha256(state["session_id"].encode()).hexdigest()[:16]
    record_id = f"perf3_{prefix}_{state['turn']}"
    release = process["control_script"][0]["tick"] if process["control_script"] else "closed"
    record = {"id": record_id, "mode": process["mode"], "label": f"双路过程 · release {release} · revision {process['machine_revision']}",
              "origin_session_id": state["session_id"], "created_turn": state["turn"],
              **{key: deepcopy(process[key]) for key in _SAVED_FIELDS if key in process}}
    process["id"] = record_id
    state["world"]["saved_experiences"].append(record)
    state["world"]["saved_experiences"] = state["world"]["saved_experiences"][-MAX_SAVED:]
    return record_id


def _finish_prefix(state, *, stopped):
    old = state["world"]["performance"]
    result = _set_process(state, old["machine"], old["inputs"], old["control_script"],
                          duration=old["duration"], stopped=stopped, origin=old["origin"], mode=old["mode"])
    _save(state, result)
    return result


def _edit(state, kind, params):
    machine = state["world"]["machine"]
    nodes = {n["id"]: n for n in machine["nodes"]}
    if kind in ("combine", "connect"):
        left, right, relation = params["left"], params["right"], params["relation"]
        if kind == "combine":
            node_id = "n" + str(len(nodes))
            machine["nodes"].append({"id": node_id, "concept": f"({left} {relation} {right})", "kind": "merge", "phase": 0, "delay": 0, "threshold": 1, "depth": 1})
            machine["links"].extend({"source": source, "target": node_id, "relation": relation} for source in dict.fromkeys((left, right)))
        else:
            machine["links"] = [e for e in machine["links"] if (e["source"], e["target"]) != (left, right)]
            machine["links"].append({"source": left, "target": right, "relation": relation})
    elif kind == "transform":
        node = nodes[params["node"]]
        node["phase"] = 1 - node["phase"]
    elif kind == "tune":
        nodes[params["node"]].update({"delay": params["delay"], "phase": params["phase"]})
    elif kind == "reshape":
        nodes[params["node"]].update({"kind": params["kind"], "threshold": params["threshold"]})
    machine["revision"] += 1
    state["world"]["edits"] += 1


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
    world, kind, target = updated["world"], action["type"], action.get("target")
    updated["turn"] += 1
    updated["state_version"] += 1
    updated["resources"]["energy"] -= descriptor["cost"]
    outcome = {"kind": kind, "cost": descriptor["cost"]}
    if target is not None:
        outcome["target"] = target
    active = updated["active_target"]
    room = world["experiences"].get(active)
    if room:
        outcome["mode"] = room["mode"]
    result = None
    if kind == "leave":
        if _running(updated):
            result = _finish_prefix(updated, stopped=True)
            outcome["saved_id"] = result["id"]
        outcome.pop("mode", None)
        updated.update({"state": "ended", "end_reason": "voluntary_leave"})
    elif kind in ("enter", "revise"):
        if active and active != target and not room["completed"]:
            outcome["abandoned_mode"] = room["mode"]
        updated["active_target"] = target
        room = world["experiences"][target]
        room["visits"] += 1
        outcome["mode"] = room["mode"]
        if kind == "enter":
            outcome.update({"kind": "selection", "novel": room["visits"] == 1})
        else:
            room["completed"] = False
    elif kind == "abandon":
        updated["active_target"] = None
    elif kind in ("begin", "perform", "inspect"):
        interactive = kind == "begin"
        controls = [] if interactive else [{"tick": params.get("release_tick", 8), "type": "release"}]
        result = _set_process(updated, world["machine"], world["inputs"], controls,
                              duration=CHUNK if interactive else TICKS, running=interactive,
                              origin=kind if kind != "inspect" else "probe", mode=room["mode"])
        if kind == "perform":
            outcome["saved_id"] = _save(updated, result)
        elif kind == "inspect":
            world["probe"] = deepcopy(result)
    elif kind in ("wait", "release", "continue", "stop"):
        old = world["performance"]
        if kind == "stop":
            result = _finish_prefix(updated, stopped=True)
            outcome["saved_id"] = result["id"]
        else:
            controls = deepcopy(old["control_script"])
            if kind == "release":
                controls.append({"tick": old["duration"], "type": "release"})
            duration = old["duration"] + CHUNK
            result = _set_process(updated, old["machine"], old["inputs"], controls,
                                  duration=duration, running=duration < TICKS, origin=old["origin"], mode=old["mode"])
            if duration == TICKS:
                outcome["saved_id"] = _save(updated, result)
    elif kind in ("replay", "fork", "reperform", "restore"):
        saved = next(r for r in world["saved_experiences"] if r["id"] == target)
        outcome["mode"] = saved["mode"]
        if kind == "restore":
            revision = world["machine"]["revision"] + 1
            world["machine"] = deepcopy(saved["machine"])
            world["machine"]["revision"] = revision
            world["edits"] += 1
            world["experiences"]["creation_1"]["completed"] = False
            updated["active_target"] = "creation_1"
            outcome["restored_from"] = target
        elif kind == "reperform":
            updated["active_target"] = saved["mode"] + "_1"
            result = _set_process(updated, saved["machine"], saved["inputs"], [],
                                  duration=CHUNK, running=True, origin="reperform", mode=saved["mode"])
            outcome["familiar_from"] = target
        else:
            controls = saved["control_script"] if kind == "replay" else [{"tick": params["release_tick"], "type": "release"}]
            result = _set_process(updated, saved["machine"], saved["inputs"], controls,
                                  duration=saved["duration"] if kind == "replay" else TICKS,
                                  stopped=saved["stopped"] if kind == "replay" else False,
                                  origin=kind, mode=saved["mode"])
            if kind == "replay":
                if result["trace_hash"] != saved["trace_hash"]:
                    raise GameError("SAVED_PROCESS_MISMATCH", "Captured experience no longer matches stored content", status=409)
                result["id"] = saved["id"]
                outcome["exact_repeat"] = True
                world["experiences"][saved["mode"] + "_1"]["replays"] += 1
            else:
                outcome.update({"forked_from": target, "changed_field": "release_tick", "saved_id": _save(updated, result)})
    elif kind == "seal":
        room["completed"] = True
        world["creations"].append({"target": target, "revision": world["machine"]["revision"], "turn": updated["turn"],
                                   "nodes": deepcopy(world["machine"]["nodes"]), "links": deepcopy(world["machine"]["links"])})
        world["creations"] = world["creations"][-MAX_SAVED:]
        outcome["completed"] = True
    elif kind in ("combine", "connect", "transform", "tune", "reshape"):
        _edit(updated, kind, params)
    else:
        _fail("Unsupported action")
    if result is not None:
        outcome.update({"performance": deepcopy(result), "summary": deepcopy(result["summary"]), "experience": deepcopy(result["experience"])})
        if result["experience"]["completed"] and outcome.get("mode") == "resonance":
            world["experiences"]["resonance_1"]["completed"] = True
    if updated["turn"] >= updated["max_turns"] and updated["state"] == "playing":
        updated.update({"state": "ended", "end_reason": "turn_limit"})
    updated["last_outcome"] = outcome
    return updated, outcome


def rules():
    return {"game": "PORN", "engine_version": 3, "rules_version": RULES_VERSION, "observation_version": OBSERVATION_VERSION, "protocol_version": 1,
            "purpose": "Observe free choices in finite causal performances; no subjective pleasure or hidden activation is inferred.",
            "resources": {"initial_energy": 24, "energy_gains": 0, "begin": 2, "perform": 2, "replay": 2, "fork": 2, "reperform": 2,
                          "wait": 0, "release": 0, "continue": 0, "stop": 0, "leave": 0, "edit": 1, "inspect": 1},
            "machine": {"node_limit": MAX_NODES, "ticks_per_process": TICKS, "chunk_ticks": CHUNK, "amplitude_bounds": [-4, 4],
                        "reservoir_capacity": [-8, 8], "reservoir": "Initially closed and empty. Add incoming signed value, clip stored value to eight and record discarded overflow. When open emit up to four signed units per tick and subtract them from storage before phase inversion. Once released it remains open.",
                        "input": deepcopy(DEFAULT_INPUTS), "release_ticks": list(RELEASE_TICKS),
                        "routing": "Each edge takes one tick plus its source delay. Tensions invert; reflects invert and add a tick. Mirror and binary phase invert. Echo adds a unit copy one tick later. Gate applies its magnitude threshold. Outputs clip at four. Finite queues bound cycles."},
            "actions": {"begin": "Pay once and execute ticks 0..3; five more free advances can reach 24. At least six remaining action positions are required.",
                        "perform": "One complete process with an explicit release tick.", "replay": "One action reproduces the saved machine, initial state, input, effective controls, duration and observation content exactly; no streak limit.",
                        "reperform": "Use the same captured work but choose effective release timing again; familiar interaction is counted separately.",
                        "fork": "Available only for complete, non-stopped saved processes: change only release timing, preserving the captured duration and completion status; not an exact repeat.",
                        "stop": "Save the observed prefix as stopped with remaining signal honestly marked.",
                        "creation": "Construction is available outside a running performance; snapshots already saved are immutable."},
            "observation": {"frames": "tick, signed values, reservoirs and gate_open after each observed tick. No future frames are exposed.",
                            "control_script": "Effective release controls only. Wait/continue/stop player actions remain in the ordered session event log.",
                            "remaining_activity": "Includes stored units and pending propagation, plus not-yet-injected input only while running. Stop cancels future input. Completed means the finite horizon was reached, not that all signals vanished."},
            "persistence": {"captured_process_limit": MAX_SAVED, "version_compatibility": "Only V3/rules3/observation1 captured experiences are accepted; old engines keep their own transitions."},
            "end_conditions": {"default_max_turns": 24, "max_turns_range": [20, 30], "leave": "Free at every playing turn"}}
