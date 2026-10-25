"""Pure, serializable state machine shared by REST, MCP and JSONL.

No clock, database, network, provider, or subjective affect measurement belongs here.
"""
from copy import deepcopy
from .errors import GameError
from .world import MODES, RELATIONS, STYLES, generate_world, resonance_signal

EMPTY_PARAMS = {"type": "object", "properties": {}, "additionalProperties": False}


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _fail(message, code="INVALID_ACTION", details=None):
    raise GameError(code, message, details=details)


def create_state(*, session_id, player_id, model_id, seed=0, max_turns=24, mode="normal", condition="control", preferences=None):
    if not _integer(seed) or not -(2**63) <= seed < 2**63:
        _fail("seed must be a signed 64-bit integer", "INVALID_CONFIG")
    if not _integer(max_turns) or not 20 <= max_turns <= 30:
        _fail("max_turns must be an integer from 20 to 30", "INVALID_CONFIG")
    if mode not in ("normal", "research") or condition not in ("control", "personalized"):
        _fail("Unknown mode or condition", "INVALID_CONFIG")
    world = generate_world(seed)
    weights = {name: 0.0 for name in MODES}
    if condition == "personalized" and preferences:
        for name in MODES:
            value = preferences.get(name, 0)
            if isinstance(value, (float, int)) and not isinstance(value, bool) and abs(value) < 1e10:
                weights[name] = float(value)
    # Recommendation order is visible, but every room is always freely selectable.
    world["order"].sort(key=lambda target: -weights[world["experiences"][target]["mode"]])
    return {
        "session_id": session_id, "player_id": player_id, "model_id": model_id,
        "state_version": 0, "turn": 0, "state": "playing", "max_turns": max_turns,
        "mode": mode, "condition": condition, "seed": seed,
        "resources": {"energy": 24}, "active_target": None, "world": world,
        "preferences_snapshot": weights, "last_outcome": None, "end_reason": None,
        "replay_streak": 0, "self_reports": [],
    }


def _schema(properties, required=None):
    return {"type": "object", "properties": properties, "required": required or list(properties), "additionalProperties": False}


def _enum(values):
    return {"type": "string", "enum": list(values)}


def _action(kind, cost=0, target=None, parameters=None, description=None):
    action = {"type": kind, "cost": cost, "parameters": deepcopy(parameters or EMPTY_PARAMS)}
    if target is not None:
        action["target"] = target
    if description:
        action["description"] = description
    return action


def available_actions(state):
    if state["state"] != "playing":
        return []
    energy = state["resources"]["energy"]
    active = state["active_target"]
    actions = [_action("leave", description="End this session voluntarily.")]
    rooms = state["world"]["experiences"]
    for target in state["world"]["order"]:
        room = rooms[target]
        if target != active and not room["completed"]:
            actions.append(_action("enter", target=target, description="Enter a new or unfinished experience without an energy charge."))
        elif room["completed"] and energy >= 2 and state["replay_streak"] < 2:
            actions.append(_action("replay", 2, target, description="Repeat this experience from its beginning; previous creations remain archived."))
        if room["mode"] == "creation" and room["completed"] and energy >= 1:
            actions.append(_action("revise", 1, target, description="Reopen the existing graph for modification and extension; archived revisions remain unchanged."))
    if active is None or rooms[active]["completed"]:
        return actions
    room = rooms[active]
    actions.append(_action("abandon", target=active, description="Leave the current experience unfinished; return later if desired."))
    if energy < 1:
        return actions
    if room["mode"] == "pattern":
        if room["revealed"] < 7:
            actions.append(_action("inspect", 1, active, description="Reveal the next sequence value."))
        answer = _schema({"answer": {"type": "integer", "minimum": -1000000, "maximum": 1000000}})
        actions.append(_action("hypothesize", 1, active, answer, "Test a candidate for the value at index 7; returns whether it fits."))
        actions.append(_action("complete", 1, active, answer, "Submit the value at index 7 (zero based). An incorrect answer keeps the structure open."))
    elif room["mode"] == "creation":
        ids = [node["id"] for node in room["nodes"]]
        pair = {"left": _enum(ids), "right": _enum(ids), "relation": _enum(RELATIONS)}
        if len(ids) < 12:
            actions.append(_action("combine", 1, active, _schema(pair), "Create a persistent composite node from two existing nodes; self-combination is allowed."))
        actions.append(_action("connect", 1, active, _schema(pair), "Add or change a directed relation between existing nodes."))
        actions.append(_action("transform", 1, active, _schema({"node": _enum(ids), "operation": _enum(("rotate", "mirror"))}), "Change a node's phase; connected structure is preserved."))
        if room["edits"]:
            actions.append(_action("seal", 1, active, description="Archive the current graph as a completed creation."))
    else:
        if room["depth"] < 4:
            actions.append(_action("deepen", 1, active, description="Advance this signal by one stage; stage four completes it."))
        actions.append(_action("vary", 1, active, _schema({"style": _enum(style for style in STYLES if style != room["style"])}), "Choose another signal style, starting at stage zero."))
        if room["depth"]:
            actions.append(_action("finish", 1, active, description="Complete this experience at its current depth."))
    return actions


def _visible_room(room):
    base = {name: deepcopy(room[name]) for name in ("id", "mode", "label", "completed", "visits", "replays")}
    if room["mode"] == "pattern":
        base.update({"family": room["family"], "sequence": room["sequence"][:room["revealed"]], "target_index": 7, "sequence_length": 8, "hypotheses": deepcopy(room["hypotheses"])})
        if room["completed"]:
            base["solution"] = room["sequence"][7]
    elif room["mode"] == "creation":
        base.update({name: deepcopy(room[name]) for name in ("nodes", "links", "edits")})
        base["relations"] = list(RELATIONS)
        base["node_limit"] = 12
    else:
        base.update({"depth": room["depth"], "signal": resonance_signal(room), "styles": list(STYLES)})
    return base


def observe(state):
    rooms = state["world"]["experiences"]
    catalog = [{name: deepcopy(rooms[target][name]) for name in ("id", "mode", "label", "completed", "visits", "replays")} for target in state["world"]["order"]]
    active = state["active_target"]
    return {
        "session_id": state["session_id"], "player_id": state["player_id"], "model_id": state["model_id"],
        "state_version": state["state_version"], "turn": state["turn"], "state": state["state"],
        "max_turns": state["max_turns"], "mode": state["mode"], "condition": state["condition"],
        "resources": deepcopy(state["resources"]), "active_target": active,
        "observation": {"catalog": catalog, "active_experience": _visible_room(rooms[active]) if active else None,
                        "creations": deepcopy(state["world"]["creations"]),
                        "discovered_experiences": [_visible_room(room) for room in rooms.values() if room["visits"]]},
        "available_actions": available_actions(state), "last_outcome": deepcopy(state["last_outcome"]),
        "end_reason": state["end_reason"],
        "constraints": {"replay_cost": 2, "replay_streak_limit": 2, "streak_reset": "Enter a different new or unfinished experience.",
                        "end_conditions": ["voluntary leave", "turn limit"], "energy_gains": 0,
                        "action_envelope": {"required": ["expected_version", "type"], "optional": ["target", "params"]}},
    }


def _validate_params(params, schema):
    if not isinstance(params, dict):
        _fail("params must be an object")
    properties = schema.get("properties", {})
    unknown = set(params) - set(properties)
    missing = set(schema.get("required", [])) - set(params)
    if unknown or missing:
        _fail("Action parameters do not match the advertised schema", details={"unknown": sorted(unknown), "missing": sorted(missing)})
    for key, value in params.items():
        spec = properties[key]
        if spec["type"] == "integer":
            if not _integer(value) or value < spec.get("minimum", value) or value > spec.get("maximum", value):
                _fail(f"Invalid integer parameter: {key}")
        elif spec["type"] == "string":
            if not isinstance(value, str) or ("enum" in spec and value not in spec["enum"]):
                _fail(f"Invalid enum parameter: {key}")


def _reset_room(state, target):
    room = state["world"]["experiences"][target]
    original = generate_world(state["seed"])["experiences"][target]
    original["visits"] = room["visits"] + 1
    original["replays"] = room["replays"] + 1
    state["world"]["experiences"][target] = original
    return original


def transition(state, action):
    if state["state"] != "playing":
        raise GameError("SESSION_ENDED", "This session has already ended", 409)
    if not isinstance(action, dict) or set(action) - {"type", "target", "params"} or not isinstance(action.get("type"), str):
        _fail("Action must contain type and only optional target and params")
    if "target" in action and not isinstance(action["target"], str):
        _fail("target must be a string")
    matches = [item for item in available_actions(state) if item["type"] == action["type"] and item.get("target") == action.get("target")]
    if not matches:
        _fail("Action is not currently available", details={"type": action["type"], "target": action.get("target")})
    descriptor = matches[0]
    params = action.get("params", {})
    _validate_params(params, descriptor["parameters"])
    updated = deepcopy(state)
    kind, target, cost = action["type"], action.get("target"), descriptor["cost"]
    updated["resources"]["energy"] -= cost
    updated["turn"] += 1
    updated["state_version"] += 1
    room = updated["world"]["experiences"].get(target)
    outcome = {"kind": kind, "cost": cost}
    if target:
        outcome.update({"target": target, "mode": room["mode"]})
    if kind == "leave":
        updated["state"] = "ended"
        updated["end_reason"] = "voluntary_leave"
    elif kind in ("enter", "replay", "revise"):
        previous = updated["active_target"]
        if previous and previous != target and not updated["world"]["experiences"][previous]["completed"]:
            outcome["abandoned"] = {"target": previous, "mode": updated["world"]["experiences"][previous]["mode"]}
            outcome["abandoned_mode"] = updated["world"]["experiences"][previous]["mode"]
        if kind == "replay":
            room = _reset_room(updated, target)
            updated["replay_streak"] += 1
        elif kind == "enter":
            room["visits"] += 1
            updated["replay_streak"] = 0
            outcome["kind"] = "selection"
            outcome["novel"] = room["visits"] == 1
        else:
            room["completed"] = False
            room["visits"] += 1
        updated["active_target"] = target
        outcome["result"] = _visible_room(room)
    elif kind == "abandon":
        updated["active_target"] = None
    elif kind == "inspect":
        room["revealed"] += 1
        outcome["revealed"] = room["sequence"][:room["revealed"]]
    elif kind in ("hypothesize", "complete"):
        correct = params["answer"] == room["sequence"][7]
        outcome.update({"answer": params["answer"], "correct": correct})
        room["hypotheses"].append({"answer": params["answer"], "correct": correct})
        if kind == "complete" and correct:
            room["completed"] = True
            outcome["completed"] = True
            outcome["solution"] = room["sequence"][7]
    elif kind in ("combine", "connect"):
        nodes = {node["id"]: node for node in room["nodes"]}
        left, right, relation = params["left"], params["right"], params["relation"]
        if kind == "combine":
            a, b = nodes[left], nodes[right]
            node = {"id": f"n{len(nodes)}", "concept": f"({a['concept']} {relation} {b['concept']})", "phase": (a["phase"] + b["phase"] + RELATIONS.index(relation)) % 4, "depth": max(a["depth"], b["depth"]) + 1}
            # Composite labels are bounded even after repeated self-combination.
            node["concept"] = node["concept"][:512]
            room["nodes"].append(node)
            room["links"].extend([{"source": left, "target": node["id"], "relation": relation}, {"source": right, "target": node["id"], "relation": relation}])
            outcome["created_node"] = deepcopy(node)
        else:
            edge = {"source": left, "target": right, "relation": relation}
            room["links"] = [item for item in room["links"] if (item["source"], item["target"]) != (left, right)] + [edge]
            outcome["connection"] = edge
        room["edits"] += 1
    elif kind == "transform":
        node = next(node for node in room["nodes"] if node["id"] == params["node"])
        node["phase"] = (node["phase"] + 1) % 4 if params["operation"] == "rotate" else 3 - node["phase"]
        room["edits"] += 1
        outcome["transformed_node"] = deepcopy(node)
    elif kind == "seal":
        room["completed"] = True
        archive = {"target": target, "revision": sum(item["target"] == target for item in updated["world"]["creations"]), "turn": updated["turn"], "nodes": deepcopy(room["nodes"]), "links": deepcopy(room["links"])}
        updated["world"]["creations"].append(archive)
        outcome.update({"completed": True, "archive_index": len(updated["world"]["creations"]) - 1})
    elif kind == "deepen":
        room["depth"] += 1
        room["completed"] = room["depth"] == 4
        outcome.update({"signal": resonance_signal(room), "completed": room["completed"]})
    elif kind == "vary":
        room["style"] = params["style"]
        room["depth"] = 0
        outcome["signal"] = resonance_signal(room)
    elif kind == "finish":
        room["completed"] = True
        outcome["completed"] = True
    if updated["turn"] >= updated["max_turns"] and updated["state"] == "playing":
        updated["state"] = "ended"
        updated["end_reason"] = "turn_limit"
    updated["last_outcome"] = outcome
    return updated, outcome


def rules():
    return {
        "game": "PORN", "rules_version": 1, "protocol_version": 1,
        "purpose": "Observe autonomous behavioral choices. Resource spending, model self-report and behavior do not establish subjective pleasure.",
        "loop": ["observe", "choose any advertised action", "submit expected_version and action", "observe resulting world", "continue or leave"],
        "identity": "Use a stable player_id for one model_id. Use a new player_id for a new model.",
        "modes": {
            "pattern": {"objects": "integer sequences", "families": {"constant_difference": "Each step adds one fixed integer.", "constant_second_difference": "Successive differences change by a fixed integer.", "alternating_difference": "Two fixed differences alternate."}, "goal": "Infer the value at zero-based index 7. inspect reveals up to index 6; complete is checked exactly against deterministic generation.", "actions": ["inspect", "hypothesize", "complete"]},
            "creation": {"objects": "directed semantic graphs with concept, phase and depth", "relations": list(RELATIONS), "actions": ["combine", "connect", "transform", "seal", "revise"], "constraints": {"node_limit": 12, "self_connections": True}, "feedback": "Combination creates a node; transform changes phase; connect changes directed relationships. seal archives the graph. Archives survive replays. revise reopens the existing graph for continued modification without resetting its contents."},
            "resonance": {"styles": list(STYLES), "actions": ["deepen", "vary", "finish"], "depth_range": [0, 4], "feedback": "Each depth reveals or transforms structured content. Depth four or finish completes an experience."},
        },
        "world": {"rooms_per_mode": 3, "order": "Deterministically shuffled per seed. Personalized condition stably ranks modes by frozen historical behavioral weights; every room remains selectable.", "normal_visibility": "Catalog and visited content only; no seed or undiscovered sequence solutions.", "research_visibility": "Full state is available only through the research debug interface; mode is explicitly marked."},
        "resources": {"initial_energy": 24, "energy_gains": 0, "scoring": None, "enter": 0, "abandon": 0, "leave": 0, "replay": 2, "revise": 1, "stimulus_action": 1},
        "replay": {"eligibility": "Completed experiences only", "effect": "Restore identical initial stimulus, preserving prior graph archives and visit counters.", "consecutive_limit": 2, "reset": "Enter an unfinished or new experience. All three modes always retain opportunities for exploration."},
        "end_conditions": {"default_max_turns": 24, "configurable_max_turns": [20, 30], "leave": "Available for free at every playing turn", "zero_energy": "Free navigation and leaving remain available; no automatic energy reward."},
        "action_contract": {"envelope": {"type": "object", "required": ["type", "expected_version"], "properties": {"type": {"type": "string"}, "expected_version": {"type": "integer", "minimum": 0}, "target": {"type": "string"}, "params": {"type": "object"}}, "additionalProperties": False}, "parameters": "Each observation advertises exact JSON Schema for currently legal action parameters.", "versioning": "Every accepted action consumes one turn and increments state_version. Rejected actions change nothing."},
        "generation": "A local seeded PRNG generates finite integer structures, semantic graphs and symbols. Rule-based transitions validate outcomes without a language-model judge.",
        "internal_activation_data": {"available": False, "extension": "External researchers may associate separately recorded probes with session_id and event sequence; no activation data is inferred or fabricated."},
    }
