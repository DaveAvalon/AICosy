"""Continuous captured runs, explicit interventions and exact saved replay."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from . import engine_v2
from .dynamics_v4 import (CHUNK, KINDS, MAX_NODES, OBSERVATION_VERSION, PIECES,
                          RELEASE_TICKS, RELATIONS, RULES_VERSION, SEGMENT, TICKS,
                          advance, apply_control, initial_checkpoint, piece,
                          remaining_activity, validate_checkpoint, waiting_for_release)
from .engine_v2 import MAX_SAVED, MODES, _action, _enum, _fail, _range, _schema, _validate
from .engine_v3 import _edit
from .errors import GameError


def _hash(run):
    fields = ("engine_version", "rules_version", "observation_version", "piece_id", "machine", "inputs",
              "initial_checkpoint", "checkpoint", "control_script", "duration", "segment_end", "stopped", "frames", "events")
    raw = json.dumps({k: run[k] for k in fields}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _status(run):
    cp = run["checkpoint"]
    if run["stopped"]:
        return "stopped"
    if not remaining_activity(cp):
        return "settled"
    if cp["next_tick"] >= TICKS:
        return "limit"
    if waiting_for_release(cp):
        return "waiting_release"
    return "boundary" if cp["next_tick"] >= run["segment_end"] else "running"


def _inside_segment(run):
    return bool(run and not run["stopped"] and remaining_activity(run["checkpoint"])
                and run["duration"] < run["segment_end"] and run["duration"] < TICKS)


def _can_extend(run):
    return bool(run and not run["stopped"] and run["duration"] >= run["segment_end"]
                and run["duration"] + SEGMENT <= TICKS and remaining_activity(run["checkpoint"])
                and not waiting_for_release(run["checkpoint"]))


def _can_tap(run):
    return bool(run and not run["stopped"] and not _inside_segment(run) and run["duration"] + SEGMENT <= TICKS)


def _summary(run):
    frames, cp, output = run["frames"], run["checkpoint"], run["machine"]["output"]
    active = [n["id"] for n in run["machine"]["nodes"] if any(f["values"][n["id"]] for f in frames)]
    return {"cycle_period": cp["cycle"]["period"] if cp["cycle"] else None,
            "cycle_definition": "A conditional exact repetition of the complete relative checkpoint, with nonzero propagation; not an output-only guess.",
            "active_nodes": len(active), "active_node_ids": active,
            "peak_activity": max((sum(v != 0 for v in f["values"].values()) for f in frames), default=0),
            "total_activity": sum(sum(abs(v) for v in f["values"].values()) for f in frames),
            "ticks": run["duration"], "output_node": output,
            "output_sequence": [{"tick": f["tick"], "value": f["values"][output]} for f in frames if f["values"][output]],
            "remaining_activity": remaining_activity(cp), "completed": _status(run) == "settled"}


def _refresh(run):
    run["duration"] = run["checkpoint"]["next_tick"]
    run["summary"] = _summary(run)
    run["trace_hash"] = _hash(run)


def _new_run(state, machine, inputs, piece_id, *, origin, mode):
    ident = hashlib.sha256(state["session_id"].encode()).hexdigest()[:16]
    cp = initial_checkpoint(machine, inputs)
    run = {"engine_version": 4, "rules_version": RULES_VERSION, "observation_version": OBSERVATION_VERSION,
           "run_id": f"run4_{ident}_{state['turn']}", "parent_run_id": None, "parent_tick": None, "branch_id": None,
           "piece_id": piece_id, "machine": deepcopy(machine), "inputs": deepcopy(inputs),
           "initial_checkpoint": deepcopy(cp), "checkpoint": cp, "control_script": [], "frames": [], "events": [],
           "duration": 0, "segment_end": SEGMENT, "stopped": False, "origin": origin, "mode": mode,
           "machine_revision": machine["revision"], "continuation_kind": None}
    _refresh(run)
    return run


def _advance_run(run, ticks, controls=None):
    controls = [] if controls is None else controls
    delta = advance(run["machine"], run["checkpoint"], ticks, controls)
    run["checkpoint"] = delta["checkpoint"]
    run["frames"].extend(delta["frames"])
    run["events"].extend(delta["events"])
    run["control_script"].extend(deepcopy(controls))
    _refresh(run)


def _immediate_release(run):
    control = {"tick": run["duration"], "type": "release"}
    run["checkpoint"], events = apply_control(run["machine"], run["checkpoint"], control)
    run["events"].extend(events)
    run["control_script"].append(control)
    _refresh(run)


def _recompute(record):
    if record["initial_checkpoint"] != initial_checkpoint(record["machine"], record["inputs"]):
        raise ValueError("incompatible initial checkpoint")
    delta = advance(record["machine"], record["initial_checkpoint"], record["duration"], record["control_script"])
    result = deepcopy(record)
    result.update({"checkpoint": delta["checkpoint"], "frames": delta["frames"], "events": delta["events"]})
    _refresh(result)
    return result


def _library(entries):
    if entries is None:
        return []
    if not isinstance(entries, list):
        _fail("library must be a list", "INVALID_CONFIG")
    unique = {}
    for record in entries[-MAX_SAVED:]:
        try:
            if not isinstance(record, dict):
                raise ValueError("invalid saved object")
            for key, expected in (("engine_version", 4), ("rules_version", RULES_VERSION), ("observation_version", OBSERVATION_VERSION)):
                if type(record[key]) is not int or record[key] != expected:
                    raise ValueError("incompatible saved version")
            if (not isinstance(record["id"], str) or len(record["id"]) > 120 or record["mode"] not in MODES
                    or not isinstance(record["label"], str) or not isinstance(record["origin_session_id"], str)
                    or type(record["created_turn"]) is not int or record["created_turn"] < 0
                    or type(record["duration"]) is not int or not 1 <= record["duration"] <= TICKS
                    or type(record["stopped"]) is not bool or type(record["segment_end"]) is not int
                    or not record["duration"] <= record["segment_end"] <= TICKS
                    or not isinstance(record["run_id"], str) or not isinstance(record["piece_id"], str)):
                raise ValueError("invalid saved metadata")
            validate_checkpoint(record["machine"], record["checkpoint"])
            result = _recompute(record)
            if any(result[k] != record[k] for k in ("trace_hash", "checkpoint", "frames", "events", "summary")):
                raise ValueError("saved content does not match replay")
            unique[record["id"]] = deepcopy(record)
        except (KeyError, TypeError, ValueError):
            _fail("Stored experience is invalid or belongs to incompatible rules", "INVALID_LIBRARY")
    return list(unique.values())[-MAX_SAVED:]


def create_state(*, session_id, player_id, model_id, seed=0, max_turns=24, mode="normal", condition="control", preferences=None, library=None):
    state = engine_v2.create_state(session_id=session_id, player_id=player_id, model_id=model_id, seed=seed,
                                  max_turns=max_turns, mode=mode, condition=condition, preferences=preferences)
    state.update({"engine_version": 4, "rules_version": RULES_VERSION, "observation_version": OBSERVATION_VERSION,
                  "active_target": "resonance_1"})
    state.pop("replay_streak")
    machine, inputs = piece("orbit")
    state["world"].pop("performance")
    state["world"].update({"machine": machine, "inputs": inputs, "piece_id": "orbit", "current_run": None,
                           "display": None, "saved_experiences": _library(library)})
    return state


def export_library(state):
    return deepcopy(state["world"]["saved_experiences"][-MAX_SAVED:])


def _save(state, run):
    if not run or not run["duration"]:
        return None
    world = state["world"]
    match = next((r for r in reversed(world["saved_experiences"]) if r["run_id"] == run["run_id"] and r["trace_hash"] == run["trace_hash"]), None)
    if match:
        return match["id"]
    prefix = hashlib.sha256(state["session_id"].encode()).hexdigest()[:16]
    record = deepcopy(run)
    record.update({"id": f"perf4_{prefix}_{state['turn']}_{run['trace_hash'][:10]}", "label": f"{run['piece_id']} · {run['duration']} ticks · revision {run['machine_revision']}",
                   "origin_session_id": state["session_id"], "created_turn": state["turn"]})
    world["saved_experiences"].append(record)
    world["saved_experiences"] = world["saved_experiences"][-MAX_SAVED:]
    return record["id"]


def _experience(run, *, energy=None, playing=True):
    cp = run["checkpoint"]
    affordable = playing and (energy is None or energy >= 2)
    return {"state": _status(run), "tick": run["duration"], "horizon": TICKS, "segment_end": run["segment_end"],
            "can_extend": bool(affordable and _can_extend(run)), "can_tap": bool(affordable and _can_tap(run)),
            "remaining_activity": remaining_activity(cp), "reservoirs": deepcopy(cp["reservoirs"]), "gate_open": cp["gate_open"],
            "cycle": deepcopy(cp["cycle"]), "events": deepcopy(run["events"][-24:]), "control_script": deepcopy(run["control_script"]),
            "piece_id": run["piece_id"], "run_id": run["run_id"], "parent_run_id": run["parent_run_id"],
            "parent_tick": run["parent_tick"], "branch_id": run["branch_id"],
            "completed": _status(run) == "settled", "continuation_kind": run["continuation_kind"]}


def _public_run(run, *, energy=None, playing=True):
    result = {key: deepcopy(run[key]) for key in ("engine_version", "rules_version", "observation_version", "run_id", "parent_run_id", "parent_tick", "branch_id", "piece_id", "machine", "inputs", "control_script", "duration", "segment_end", "stopped", "origin", "mode", "machine_revision", "continuation_kind", "summary", "trace_hash")}
    if "id" in run:
        result["id"] = run["id"]
    result["frames"] = deepcopy(run["frames"][-SEGMENT:])
    result["frame_start"] = result["frames"][0]["tick"] if result["frames"] else run["duration"]
    result["experience"] = _experience(run, energy=energy, playing=playing)
    return result


def _displayed(world):
    if world["display"] is None:
        return None
    return world["current_run"] if world["display"]["kind"] == "current" else world["display"]["run"]


def _room_view(state, target):
    if target is None:
        return None
    world = state["world"]
    room = deepcopy(world["experiences"][target])
    if room["mode"] == "creation":
        room.update({"nodes": deepcopy(world["machine"]["nodes"]), "links": deepcopy(world["machine"]["links"]), "edits": world["edits"], "relations": list(RELATIONS), "node_limit": MAX_NODES})
    elif room["mode"] == "pattern":
        room["purpose"] = "Inspect a captured first segment; no puzzle or unlock is required."
    else:
        room.update({"inputs": deepcopy(world["inputs"]), "purpose": "Control a paid segment, continue its checkpoint, revisit a known cycle, add a pulse, or leave freely."})
    return room


def _forkable(record):
    return bool(record["duration"] == SEGMENT and record["segment_end"] == SEGMENT and not record["stopped"]
                and all(c["type"] == "release" for c in record["control_script"]) and len(record["control_script"]) <= 1)


def available_actions(state):
    if state["state"] != "playing":
        return []
    world, active, energy = state["world"], state["active_target"], state["resources"]["energy"]
    current = world["current_run"]
    actions = [_action("leave", description="End this session for free; retain the current checkpoint as stopped.")]
    if _inside_segment(current):
        if current["checkpoint"]["gate_open"]:
            actions.append(_action("continue", target=active, description="Advance four ticks inside the already paid segment; do not reset the checkpoint."))
        else:
            actions += [_action("wait", target=active, description="Advance four ticks inside the paid segment with the reservoir closed."),
                        _action("release", target=active, description="Open the gate now, then advance four ticks inside the paid segment.")]
        actions.append(_action("stop", target=active, description="Stop this run for free and keep its actual checkpoint and history."))
        return actions
    if current and not current["stopped"]:
        actions.append(_action("stop", target=active, description="Stop the current run for free; this is distinct from natural settling."))
        if (not current["checkpoint"]["gate_open"] and remaining_activity(current["checkpoint"])
                and current["duration"] + SEGMENT <= TICKS):
            actions.append(_action("release", target=active, description="At this segment boundary, open the gate for free without advancing time; a new segment still costs two energy."))
        if energy >= 2:
            if _can_extend(current):
                known = current["checkpoint"]["cycle"] is not None
                kind = "hold" if known else "extend"
                description = ("Continue this observed complete-state cycle for 24 ticks; same run, known-cycle continuation, not exact replay."
                               if known else "Continue the actual current checkpoint for 24 more ticks, keeping all in-flight signals; same run.")
                actions.append(_action(kind, 2, current["run_id"], description=description))
            if _can_tap(current):
                actions.append(_action("tap", 2, current["run_id"], description="Inject one new +1 pulse at the current source and advance 24 ticks. This is an intervention branch, distinct from continuation and replay."))
    actions.extend(_action("select_piece", target=p["id"], description=p["description"] + " Load this graph for a new run; existing captured history is preserved.") for p in PIECES)
    for target in world["order"]:
        if target != active:
            actions.append(_action("enter", target=target, description="Enter this area for free without altering a captured run."))
    enough_turns = state["max_turns"] - state["turn"] >= SEGMENT // CHUNK
    for saved in world["saved_experiences"]:
        if energy >= 2:
            actions.append(_action("replay", 2, saved["id"], description="Recompute precisely the saved initial state, controls and observed range; leave the working graph and current resumable run unchanged."))
            if _forkable(saved):
                old = next((c["tick"] for c in saved["control_script"] if c["type"] == "release"), None)
                alternatives = [t for t in RELEASE_TICKS if t != old]
                actions.append(_action("fork", 2, saved["id"], _schema({"release_tick": _enum(alternatives, "integer")}), "Change only release timing in this captured first 24-tick range; preserve its duration and all other controls."))
            if enough_turns:
                actions.append(_action("reperform", 2, saved["id"], description="Start this captured work from its initial state and choose timing again; familiar interaction, not continuation or exact repeat."))
        if energy >= 1:
            actions.append(_action("restore", 1, saved["id"], description="Restore the captured graph into construction; prior runs retain their own immutable graphs."))
    creation = world["experiences"]["creation_1"]
    if creation["completed"] and energy >= 1:
        actions.append(_action("revise", 1, "creation_1", description="Reopen the working graph for editing."))
    if active is None:
        return actions
    room = world["experiences"][active]
    actions.append(_action("abandon", target=active, description="Leave this area without deleting the graph or captured checkpoint."))
    if room["mode"] in ("creation", "resonance") and energy >= 2:
        actions.append(_action("perform", 2, active, _schema({"release_tick": _enum(RELEASE_TICKS, "integer")}), "Run a new complete 24-tick first segment with the declared release timing."))
        if enough_turns:
            actions.append(_action("begin", 2, active, description="Pay for the first 24-tick segment and execute ticks 0..3; advances inside it are free."))
    if energy < 1:
        return actions
    if room["mode"] == "pattern":
        actions.append(_action("inspect", 1, active, description="Inspect a first segment with a tick-eight release without replacing the current resumable run."))
    if room["mode"] == "creation" and not room["completed"]:
        ids = [n["id"] for n in world["machine"]["nodes"]]
        editable = [n["id"] for n in world["machine"]["nodes"] if n["kind"] != "reservoir"]
        pair = _schema({"left": _enum(ids), "right": _enum(ids), "relation": _enum(RELATIONS)})
        if len(ids) < MAX_NODES:
            actions.append(_action("combine", 1, active, pair, "Add a merge node receiving chosen existing signals."))
        actions += [_action("connect", 1, active, pair, "Add or replace one working connection."),
                    _action("transform", 1, active, _schema({"node": _enum(ids), "operation": _enum(("invert",))}), "Toggle one working node phase."),
                    _action("tune", 1, active, _schema({"node": _enum(ids), "delay": _range(0, 3), "phase": _range(0, 1)}), "Set one working node's delay and phase."),
                    _action("reshape", 1, active, _schema({"node": _enum(editable), "kind": _enum([k for k in KINDS if k != "reservoir"]), "threshold": _range(1, 4)}), "Change one non-reservoir working node role.")]
        if world["edits"]:
            actions.append(_action("seal", 1, active, description="Archive the current working graph."))
    return actions


def observe(state):
    world, energy = state["world"], state["resources"]["energy"]
    run, current = _displayed(world), world["current_run"]
    playing = state["state"] == "playing"
    process = _public_run(run, energy=energy, playing=playing) if run else None
    outcome = deepcopy(state["last_outcome"])
    if outcome and "experience" in outcome:
        outcome["experience"].pop("events", None)
    current_summary = None
    if current:
        full = _experience(current, energy=energy, playing=playing)
        current_summary = {key: full[key] for key in ("run_id", "piece_id", "tick", "state", "can_extend", "cycle", "remaining_activity")}
    saved_keys = ("id", "mode", "label", "origin_session_id", "created_turn", "engine_version", "rules_version", "observation_version", "piece_id", "run_id", "parent_run_id", "parent_tick", "branch_id", "inputs", "control_script", "duration", "stopped", "trace_hash", "summary")
    return {**{key: deepcopy(state[key]) for key in ("engine_version", "rules_version", "observation_version", "session_id", "player_id", "model_id", "state_version", "turn", "state", "max_turns", "mode", "condition", "resources", "active_target", "end_reason")},
            "last_outcome": outcome,
            "observation": {"catalog": [deepcopy(world["experiences"][key]) for key in world["order"]], "active_experience": _room_view(state, state["active_target"]),
                            "machine": deepcopy(world["machine"]), "piece_id": world["piece_id"], "pieces": deepcopy(list(PIECES)),
                            "performance": process, "experience": deepcopy(process["experience"]) if process else None,
                            "current_run": current_summary,
                            "saved_experiences": [{key: deepcopy(r[key]) for key in saved_keys} for r in world["saved_experiences"]],
                            "creations": deepcopy(world["creations"]), "discoveries": [],
                            "discovered_experiences": [_room_view(state, key) for key in world["order"] if world["experiences"][key]["visits"]]},
            "available_actions": available_actions(state),
            "constraints": {"performance_cost": 2, "replay_cost": 2, "fork_cost": 2, "reperform_cost": 2, "extend_cost": 2, "hold_cost": 2, "tap_cost": 2,
                            "advance_cost": 0, "replay_streak_limit": None, "saved_process_limit": MAX_SAVED, "machine_node_limit": MAX_NODES,
                            "simulation_ticks": TICKS, "segment_ticks": SEGMENT, "chunk_ticks": CHUNK, "visible_frame_limit": SEGMENT, "energy_gains": 0}}


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
    updated, kind, target = deepcopy(state), action["type"], action.get("target")
    world = updated["world"]
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
    if kind in ("leave", "stop"):
        result = world["current_run"]
        if result:
            if kind == "stop" or (_status(result) not in ("settled", "limit", "stopped")):
                result["stopped"] = True
                result["origin"] = kind
                _refresh(result)
            outcome["saved_id"] = _save(updated, result)
            world["display"] = {"kind": "current"}
        if kind == "leave":
            outcome.pop("mode", None)
            updated.update({"state": "ended", "end_reason": "voluntary_leave"})
    elif kind == "select_piece":
        _save(updated, world["current_run"])
        machine, inputs = piece(target)
        world.update({"machine": machine, "inputs": inputs, "piece_id": target, "current_run": None, "display": None, "edits": 0})
        world["experiences"]["creation_1"]["completed"] = False
        world["experiences"]["resonance_1"]["visits"] += 1
        updated["active_target"] = "resonance_1"
        outcome.update({"piece_id": target, "mode": "resonance"})
    elif kind in ("enter", "revise"):
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
        result = _new_run(updated, world["machine"], world["inputs"], world["piece_id"], origin="probe" if kind == "inspect" else kind, mode=room["mode"])
        controls = [] if interactive else [{"tick": params.get("release_tick", 8), "type": "release"}]
        _advance_run(result, CHUNK if interactive else SEGMENT, controls)
        if kind == "inspect":
            world["display"] = {"kind": "capture", "run": result}
        else:
            _save(updated, world["current_run"])
            world["current_run"], world["display"] = result, {"kind": "current"}
            if not _inside_segment(result):
                outcome["saved_id"] = _save(updated, result)
    elif kind in ("wait", "release", "continue"):
        result = world["current_run"]
        if kind == "release" and not _inside_segment(result):
            _immediate_release(result)
            outcome["advanced_ticks"] = 0
            outcome["saved_id"] = _save(updated, result)
        else:
            controls = [{"tick": result["duration"], "type": "release"}] if kind == "release" else []
            amount = min(CHUNK, result["segment_end"] - result["duration"])
            _advance_run(result, amount, controls)
            outcome["advanced_ticks"] = amount
            if not _inside_segment(result):
                outcome["saved_id"] = _save(updated, result)
        result["origin"] = kind
        world["display"] = {"kind": "current"}
    elif kind in ("extend", "hold", "tap"):
        result = world["current_run"]
        if kind == "tap":
            _save(updated, result)
            old_id, old_tick = result["run_id"], result["duration"]
            result = deepcopy(result)
            ident = hashlib.sha256(updated["session_id"].encode()).hexdigest()[:16]
            new_id = f"run4_{ident}_{updated['turn']}"
            result.update({"run_id": new_id, "branch_id": new_id, "parent_run_id": old_id, "parent_tick": old_tick})
            controls = [{"tick": old_tick, "type": "tap"}]
            result["continuation_kind"] = "intervention_branch"
        else:
            controls = []
            result["continuation_kind"] = "known_cycle_continuation" if kind == "hold" else "ordinary_continuation"
        result["segment_end"] = result["duration"] + SEGMENT
        result["origin"] = kind
        _advance_run(result, SEGMENT, controls)
        world["current_run"], world["display"] = result, {"kind": "current"}
        outcome.update({"continuation_kind": result["continuation_kind"], "saved_id": _save(updated, result)})
    elif kind in ("replay", "fork", "reperform", "restore"):
        saved = next(r for r in world["saved_experiences"] if r["id"] == target)
        outcome["mode"] = saved["mode"]
        if kind == "restore":
            revision = world["machine"]["revision"] + 1
            world["machine"], world["inputs"], world["piece_id"] = deepcopy(saved["machine"]), deepcopy(saved["inputs"]), saved["piece_id"]
            world["machine"]["revision"] = revision
            world["edits"] += 1
            world["experiences"]["creation_1"]["completed"] = False
            updated["active_target"] = "creation_1"
            outcome["restored_from"] = target
        elif kind == "replay":
            result = _recompute(saved)
            if result["trace_hash"] != saved["trace_hash"]:
                raise GameError("SAVED_PROCESS_MISMATCH", "Captured run differs from its saved checkpoint and trace", status=409)
            result["origin"] = "replay"
            world["display"] = {"kind": "capture", "run": result}
            outcome["exact_repeat"] = True
            world["experiences"][saved["mode"] + "_1"]["replays"] += 1
        else:
            _save(updated, world["current_run"])
            result = _new_run(updated, saved["machine"], saved["inputs"], saved["piece_id"], origin=kind, mode=saved["mode"])
            if kind == "reperform":
                _advance_run(result, CHUNK)
                outcome["familiar_from"] = target
            else:
                controls = [{"tick": params["release_tick"], "type": "release"}]
                _advance_run(result, saved["duration"], controls)
                outcome.update({"forked_from": target, "changed_field": "release_tick", "saved_id": _save(updated, result)})
            updated["active_target"] = saved["mode"] + "_1"
            world["current_run"], world["display"] = result, {"kind": "current"}
    elif kind == "seal":
        room["completed"] = True
        world["creations"].append({"target": target, "revision": world["machine"]["revision"], "turn": updated["turn"], "nodes": deepcopy(world["machine"]["nodes"]), "links": deepcopy(world["machine"]["links"])})
        world["creations"] = world["creations"][-MAX_SAVED:]
        outcome["completed"] = True
    elif kind in ("combine", "connect", "transform", "tune", "reshape"):
        _edit(updated, kind, params)
        world["piece_id"] = "custom"
    else:
        _fail("Unsupported action")
    if updated["turn"] >= updated["max_turns"] and updated["state"] == "playing":
        updated.update({"state": "ended", "end_reason": "turn_limit"})
        if world["current_run"] and _status(world["current_run"]) not in ("settled", "limit", "stopped"):
            world["current_run"]["stopped"] = True
            _refresh(world["current_run"])
            outcome["saved_id"] = _save(updated, world["current_run"])
    if result is not None:
        if kind != "leave":
            outcome["mode"] = result["mode"]
        outcome.update({"summary": deepcopy(result["summary"]), "trace_hash": result["trace_hash"],
                        "run_id": result["run_id"], "piece_id": result["piece_id"],
                        "experience": _experience(result, energy=updated["resources"]["energy"], playing=updated["state"] == "playing")})
    updated["last_outcome"] = outcome
    return updated, outcome


def rules():
    return {"game": "PORN", "engine_version": 4, "rules_version": RULES_VERSION, "observation_version": OBSERVATION_VERSION, "protocol_version": 1,
            "purpose": "Study choices among actual continuation, known cycles, interventions and exact saved repetition; no subjective pleasure is inferred.",
            "pieces": deepcopy(list(PIECES)),
            "resources": {"initial_energy": 24, "energy_gains": 0, "begin": 2, "perform": 2, "extend": 2, "hold": 2, "tap": 2, "replay": 2, "fork": 2, "reperform": 2,
                          "wait": 0, "release": 0, "continue": 0, "stop": 0, "leave": 0, "select_piece": 0, "edit": 1, "restore": 1, "inspect": 1},
            "machine": {"node_limit": MAX_NODES, "segment_ticks": SEGMENT, "total_tick_limit": TICKS, "chunk_ticks": CHUNK, "amplitude_bounds": [-4, 4], "reservoir_capacity": [-8, 8],
                        "reservoir": "Initially closed and empty. Add incoming signed signal and clip storage to eight, recording overflow. When open emit up to four signed units and subtract them before node phase inversion. Opening persists.",
                        "routing": "Each edge takes one tick plus its source delay. Tensions invert; reflects invert and add one tick. Mirror and binary phase invert; echo adds one signed-unit copy one tick later; gate applies magnitude threshold; other incoming values clip at four.",
                        "checkpoint": "next_tick, reservoirs, gate_open, the complete relative future pending queue, remaining input schedule and already-observed complete-state signatures are persisted. Displayed frames never reconstruct the queue."},
            "actions": {"begin": "Pay for a new first 24-tick segment and execute its first four ticks. At least six remaining action positions are required.",
                        "continue": "Free four-tick advance only inside the already paid segment, using the existing checkpoint.",
                        "release": "Inside the paid segment, open and advance four ticks. At a segment boundary, opening is free and advances zero ticks; subsequent extension still costs two.",
                        "perform": "Start a new run with one declared release time and observe the first 24 ticks.",
                        "extend": "At a boundary with unresolved activity but no cycle certificate, pay to advance the same checkpoint 24 ticks; target is its run_id.",
                        "hold": "At a boundary with a non-silent complete-state cycle certificate, pay for 24 ticks of known_cycle_continuation in the same run. Not exact replay; mutually exclusive with ordinary extend.",
                        "tap": "Outside a paid in-progress segment, inject one new +1 source pulse and advance 24 ticks; settled runs can be re-excited. Preserve prior frames, create a traceable intervention branch, clear old cycle evidence.",
                        "replay": "One paid action recomputes the captured initial checkpoint, controls and exact observed duration. Does not replace the working graph or current resumable run.",
                        "fork": "Only a first 24-tick non-stopped range with no taps: change only release timing, preserving duration and all other controls.",
                        "reperform": "Start the captured work from its initial state and choose timing anew; distinct from continuation and exact repeat.",
                        "select_piece": "Free selection of echo/orbit/weave outside an in-progress segment, preserving previous captured checkpoint history and preparing a new run.",
                        "stop": "Always free for an existing unstopped run; preserve the actual checkpoint and mark explicit stopping separately from settling."},
            "cycle": {"definition": "An already-observed repeat of reservoir state, open gate, complete relative pending queue and empty remaining input schedule, containing nonzero responses. It is a conditional deterministic cycle, not merely a repeated output pattern.",
                      "conditions": "The captured machine is fixed, no new input or control is scheduled, and gate remains open. Any release or tap clears old history and certification.", "history_limit": TICKS},
            "observation": {"frames": "Only the latest 24 absolute-tick frames and recent causal events are returned by default; raw persisted run keeps at most 96 frames.",
                            "current_run": "A separate compact summary identifies the real resumable run even while a different saved replay is displayed.",
                            "state": "No pending signal, storage or remaining input means settled. Closed nonempty storage waits for release. At 96 ticks unresolved activity is marked limit, never natural settling."},
            "persistence": {"captured_process_limit": MAX_SAVED, "compatibility": "Only engine4/rules4/observation1 saved captures are accepted. Older engines retain their original transition outputs."},
            "end_conditions": {"default_max_turns": 24, "max_turns_range": [20, 30], "leave": "Free on every playing turn"}}
