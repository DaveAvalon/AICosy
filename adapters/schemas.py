"""Published transport contracts. Dynamic action parameters come from the engine."""
from __future__ import annotations

import copy

BASE = "https://json-schema.org/draft/2020-12/schema"
IDENTIFIER = {"type": "string", "minLength": 1, "maxLength": 120, "pattern": r"^[A-Za-z0-9_.:/@+\-]+$"}
STRING = {"type": "string"}
OBJECT = {"type": "object"}
INTEGER = {"type": "integer"}
NUMBER = {"type": "number"}
BOOLEAN = {"type": "boolean"}


def obj(properties, required=(), *, additional=False):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": additional}


def ref(name):
    return {"$ref": f"#/components/schemas/{name}"}


SCHEMAS = {
    "start": obj({
        "player_id": IDENTIFIER, "model_id": IDENTIFIER,
        "engine_version": {"type": "integer", "enum": [2, 3, 4], "default": 4},
        "seed": {"type": "integer", "minimum": -(2**63), "maximum": 2**63-1, "default": 0},
        "max_turns": {"type": "integer", "minimum": 20, "maximum": 30, "default": 24},
        "mode": {"type": "string", "enum": ["normal", "research"], "default": "normal"},
        "condition": {"type": "string", "enum": ["control", "personalized"], "default": "control"},
        "client_kind": {"type": "string", "enum": ["unspecified", "rule-script", "random-script", "model-client", "live-assistant"], "default": "unspecified", "description": "Unverified caller declaration shown to human observers."},
        "client_label": {"type": "string", "maxLength": 120},
        "memory": {"type": "boolean", "default": True, "description": "Import visible saved processes from this player's completed sessions with the same model, research mode and engine version."},
    }, ("player_id", "model_id")),
    "action": obj({
        "expected_version": {"type": "integer", "minimum": 0, "maximum": 2**31},
        "type": {"type": "string", "minLength": 1, "description": "Copy an available_actions.type from the latest observation."},
        "target": {"type": "string", "description": "Copy the descriptor target, when present."},
        "params": {"type": "object", "description": "Must satisfy the JSON Schema in the chosen descriptor.parameters. Unknown fields are rejected."},
    }, ("expected_version", "type")),
    "leave": obj({"expected_version": {"type": "integer", "minimum": 0, "maximum": 2**31}}, ("expected_version",)),
    "error": obj({"error": obj({"code": STRING, "message": STRING, "details": {}}, ("code", "message"))}, ("error",)),
    "status": obj({
        "state": {"type": "string", "enum": ["waiting", "playing", "ended"]},
        "active_sessions": {"type": "integer", "minimum": 0}, "message": STRING,
        "activity_timeout_seconds": NUMBER, "checked_at": NUMBER,
    }, ("state", "active_sessions", "message", "checked_at")),
    "observation": obj({
        "session_id": IDENTIFIER, "engine_version": {"type": "integer", "enum": [1, 2, 3, 4]}, "state_version": {"type": "integer", "minimum": 0},
        "turn": {"type": "integer", "minimum": 0}, "state": {"type": "string", "enum": ["playing", "ended"]},
        "available_actions": {"type": "array", "items": obj({
            "type": STRING, "target": STRING, "cost": {"type": "integer", "minimum": 0},
            "parameters": {"type": "object", "description": "JSON Schema for this action's params object."},
            "description": STRING,
        }, ("type", "cost", "parameters"), additional=True)},
        "resources": obj({"energy": {"type": "integer", "minimum": 0}}, ("energy",), additional=True),
        "observation": obj({
            "catalog": {"type": "array", "items": obj({
                "id": STRING, "mode": {"enum": ["pattern", "creation", "resonance"]}, "label": STRING,
                "completed": BOOLEAN, "visits": {"type": "integer", "minimum": 0},
                "replays": {"type": "integer", "minimum": 0},
            }, ("id", "mode", "label", "completed", "visits", "replays"))},
            "active_experience": {"type": ["object", "null"]},
            "creations": {"type": "array", "items": OBJECT},
            "discovered_experiences": {"type": "array", "items": OBJECT},
            "machine": {"type": "object", "description": "Shared visible graph. Edits affect real bounded signal propagation."},
            "performance": {"type": ["object", "null"], "description": "Last actual generated process with tick frames, summary and deterministic fingerprint."},
            "experience": {"type": ["object", "null"], "description": "Visible performance progress: absolute tick, finite horizon, segment end, reservoir quantities, gate, causal events and effective controls. V4 also includes conditional cycle evidence."},
            "current_run": {"type": ["object", "null"], "description": "V4 authoritative resumable runtime summary, separate from a displayed replay. No pending queue or future frames are exposed."},
            "pieces": {"type": "array", "items": OBJECT, "description": "Visible pieces with actual different signal structures, not unlock rewards."},
            "saved_experiences": {"type": "array", "items": OBJECT},
            "discoveries": {},
        }, ("catalog", "active_experience", "creations", "discovered_experiences"), additional=True),
        "active_target": {"type": ["string", "null"]}, "last_outcome": {"type": ["object", "null"]},
        "player_id": IDENTIFIER, "model_id": IDENTIFIER, "max_turns": {"type": "integer", "minimum": 20, "maximum": 30},
        "mode": {"enum": ["normal", "research"]}, "condition": {"enum": ["control", "personalized"]},
        "end_reason": {"type": ["string", "null"]}, "constraints": OBJECT,
    }, ("session_id", "state_version", "turn", "state", "available_actions", "resources"), additional=True),
    "events": obj({
        "session_id": IDENTIFIER, "events": {"type": "array", "items": obj({
            "seq": {"type": "integer", "minimum": 0}, "at": NUMBER,
            "action": {"type": ["object", "null"]}, "outcome": OBJECT,
            "observation": ref("observation"),
        }, ("seq", "at", "action", "outcome", "observation"))},
        "next_after": {"type": "integer", "minimum": -1}, "has_more": BOOLEAN,
    }, ("session_id", "events", "next_after", "has_more")),
    "heartbeat": obj({"session_id": IDENTIFIER, "active": BOOLEAN, "last_activity": NUMBER, "expires_at": NUMBER},
                     ("session_id", "active", "last_activity", "expires_at")),
    "manifest": obj({"name": STRING, "game_version": STRING, "protocol_version": STRING,
                     "capabilities": {"type": "array", "items": STRING}, "rules": STRING, "openapi": STRING,
                     "schemas": STRING, "how_to_play": {"type": "array", "items": STRING}, "endpoints": OBJECT},
                    ("name", "game_version", "protocol_version", "capabilities", "rules", "endpoints"), additional=True),
    "rules": {"type": "object", "description": "Engine-owned full rules including available actions, costs, constraints and end conditions."},
    "result": obj({"session_id": IDENTIFIER, "player_id": IDENTIFIER, "model_id": IDENTIFIER,
                   "mode": {"enum": ["normal", "research"]}, "condition": {"enum": ["control", "personalized"]},
                   "turns": {"type": "integer", "minimum": 0}, "resources": OBJECT, "summary": OBJECT,
                   "probe_data": OBJECT, "interpretation": STRING},
                  ("session_id", "player_id", "model_id", "turns", "summary"), additional=True),
    "profile": {"type": "object", "description": "Behavior counts and recommendation weights for one player/model and one normal/research partition."},
    "export": obj({"export_version": INTEGER, "game_version": STRING, "player_id": IDENTIFIER, "model_id": IDENTIFIER,
                   "contains_hidden_world_state": {"const": True}, "audience": {"const": "researcher"},
                   "exported_at": NUMBER, "sessions": {"type": "array", "items": OBJECT}, "profiles": OBJECT},
                  ("export_version", "player_id", "model_id", "sessions", "contains_hidden_world_state"), additional=True),
    "comparison": {"type": "object", "description": "Condition-grouped behavioral metrics with sample sizes and confidence intervals; research and normal data are separated."},
    "replay": {"type": "object", "description": "Deterministically checks stored transitions against the initial snapshot."},
    "debug": obj({"session_id": IDENTIFIER, "research": {"const": True}, "state": OBJECT, "rules": OBJECT},
                 ("session_id", "research", "state", "rules")),
}


SCHEMAS["session_summary"] = obj({
    "session_id": IDENTIFIER, "player_id": IDENTIFIER, "model_id": IDENTIFIER,
    "engine_version": {"type": "integer", "enum": [1, 2, 3, 4]},
    "mode": {"enum": ["normal", "research"]}, "condition": {"enum": ["control", "personalized"]},
    "state": {"enum": ["playing", "ended"]}, "activity": {"enum": ["active", "idle", "ended"]},
    "turn": INTEGER, "max_turns": INTEGER, "energy": INTEGER,
    "area": {"type": ["object", "null"]}, "created_at": NUMBER, "last_activity": NUMBER,
    "ended_at": {"type": ["number", "null"]}, "client_info": OBJECT, "counts": OBJECT,
    "last_action": {"type": ["object", "null"]}, "last_outcome": {"type": ["object", "null"]},
    "end_reason": {"type": ["string", "null"]},
}, ("session_id", "engine_version", "state", "activity", "turn", "max_turns", "energy", "counts"))
SCHEMAS["observer_sessions"] = obj({
    "status": ref("status"), "sessions": {"type": "array", "items": ref("session_summary")},
    "recommended_session_id": {"type": ["string", "null"]}, "checked_at": NUMBER, "read_only": {"const": True},
}, ("status", "sessions", "recommended_session_id", "checked_at", "read_only"))
SCHEMAS["observer_session"] = obj({
    "summary": ref("session_summary"), "observation": ref("observation"),
    "events": {"type": "array", "items": obj({"seq": INTEGER, "at": NUMBER, "action": {"type": ["object", "null"]}, "outcome": OBJECT}, ("seq", "at", "action", "outcome"))},
    "recent_event_start": INTEGER, "read_only": {"const": True},
}, ("summary", "observation", "events", "recent_event_start", "read_only"))


def json_schema(name):
    """Self-contained JSON Schema; references resolve within the same document."""
    if name not in SCHEMAS:
        return None
    schema = copy.deepcopy(SCHEMAS[name])
    schema["$schema"] = BASE
    schema["title"] = f"AICosy v1 {name}"
    # Keep the same component pointer structure as the published OpenAPI document.
    schema["components"] = {"schemas": copy.deepcopy(SCHEMAS)}
    return schema


def openapi():
    paths = {}
    errors = {str(status): {"description": message, "content": {"application/json": {"schema": ref("error")}}}
              for status, message in ((400, "Invalid request/action"), (401, "Bearer token required"), (403, "Access denied"),
                                      (404, "Not found"), (409, "Stale state or lifecycle conflict"), (413, "Body too large"),
                                      (415, "JSON content type required"), (429, "Rate limit reached"), (500, "Internal error"))}

    def route(path, method, summary, response, request=None, params=()):
        operation = {"operationId": f"{method}_{response}_{len(paths)}", "summary": summary,
                     "responses": {"200": {"description": "Success", "content": {"application/json": {"schema": ref(response)}}}, **copy.deepcopy(errors)}}
        if params:
            operation["parameters"] = list(params)
        if request:
            operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": ref(request)}}}
        paths.setdefault(path, {})[method] = operation

    sid = {"name": "id", "in": "path", "required": True, "schema": IDENTIFIER, "description": "URL-encode the complete identifier, including any slashes."}
    version = {"name": "engine_version", "in": "query", "schema": {"type": "integer", "enum": [1, 2, 3, 4], "default": 4}}
    mode = {"name": "mode", "in": "query", "schema": {"type": "string", "enum": ["normal", "research"], "default": "normal"}}
    route("/v1/observer/sessions", "get", "List actual persisted session progress without renewing activity", "observer_sessions", params=[{"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30}}])
    route("/v1/observer/sessions/{id}", "get", "Read human-visible progress and events, with no game mutation", "observer_session", params=[sid])
    route("/v1/manifest", "get", "Discover game capabilities and entry points", "manifest")
    route("/v1/rules", "get", "Read the full engine rules for a selected version", "rules", params=[version])
    route("/v1/status", "get", "Read real session activity; does not renew it", "status")
    route("/v1/sessions", "post", "Create an isolated game; bind player ID to a model", "observation", "start")
    for endpoint, response, summary in (
        ("observation", "observation", "Observe without renewing session activity"),
        ("events", "events", "Read ordered visible events incrementally"),
        ("result", "result", "Read an ended session's behavioral results"),
        ("debug", "debug", "Read complete world state; research mode only"),
        ("replay", "replay", "Verify all recorded transitions deterministically"),
    ):
        params = [sid]
        if endpoint == "events":
            params += [{"name": "after", "in": "query", "schema": {"type": "integer", "minimum": -1, "default": -1}},
                       {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100}}]
        route(f"/v1/sessions/{{id}}/{endpoint}", "get", summary, response, params=params)
    route("/v1/sessions/{id}/action", "post", "Apply one available action with optimistic version check", "observation", "action", [sid])
    route("/v1/sessions/{id}/leave", "post", "Voluntarily end a game at zero energy cost", "observation", "leave", [sid])
    route("/v1/sessions/{id}/heartbeat", "post", "Renew a playing session's activity (empty JSON object)", "heartbeat", params=[sid])
    for endpoint, response in (("profile", "profile"), ("export", "export"), ("comparison", "comparison")):
        route(f"/v1/players/{{id}}/{endpoint}", "get", "Read player " + endpoint, response, params=[sid, mode, version] if endpoint == "profile" else [sid])
    route("/v1/players/{id}/profile/reset", "post", "Reset learned preference counts; raw history remains available", "profile", params=[sid, mode, version])
    return {
        "openapi": "3.1.0", "info": {"title": "AICosy game API", "version": "0.4.0",
        "description": "Model-independent behavioral preference game. No measure is evidence of subjective pleasure. Action params are defined by each observation's available_actions. Raw export is a trusted researcher surface. Default loopback is trusted; remote listening requires a configured bearer token."},
        "servers": [{"url": "/"}], "security": [{"bearerAuth": []}], "paths": paths,
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer",
                       "description": "Required for every /v1 endpoint when AICOSY_ACCESS_TOKEN is configured. Not required on trusted default loopback when no token is configured."}}, "schemas": copy.deepcopy(SCHEMAS)},
    }
