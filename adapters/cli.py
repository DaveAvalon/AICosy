"""AICosy JSON Lines adapter over the shared application service."""
from __future__ import annotations

import argparse
import json
import sys
from aicosy.errors import GameError
from aicosy.service import GameService

MAX_LINE = 1024 * 1024


def fields(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise GameError("INVALID_PARAMS", "Unknown or missing protocol parameters")


def dispatch(service, method, params):
    """Translate one protocol command without implementing game rules."""
    if method == "rules":
        fields(params, ("engine_version",))
        return service.rules(params.get("engine_version", 4))
    if method in ("manifest", "status"):
        fields(params, ())
        return getattr(service, method)()
    if method == "start":
        return service.start(params)
    if method in ("observe", "heartbeat", "result", "replay", "debug"):
        fields(params, ("session_id",), ("session_id",))
        return getattr(service, method)(params["session_id"])
    if method == "act":
        fields(params, ("session_id", "action"), ("session_id", "action"))
        return service.act(params["session_id"], params["action"])
    if method == "leave":
        fields(params, ("session_id", "expected_version"), ("session_id", "expected_version"))
        return service.leave(params["session_id"], {"expected_version": params["expected_version"]})
    if method == "events":
        fields(params, ("session_id", "after", "limit"), ("session_id",))
        return service.events(params["session_id"], params.get("after", -1), params.get("limit", 100))
    if method in ("profile", "reset_profile"):
        fields(params, ("player_id", "mode", "engine_version"), ("player_id",))
        return getattr(service, method)(params["player_id"], params.get("mode", "normal"), params.get("engine_version", 4))
    if method in ("export", "compare"):
        fields(params, ("player_id",), ("player_id",))
        return getattr(service, "export_player" if method == "export" else method)(params["player_id"])
    raise GameError("UNKNOWN_METHOD", "Unknown method; use manifest to discover the game")


def strict_json(line):
    def bad_constant(value):
        raise ValueError("Non-finite JSON number")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(line, parse_constant=bad_constant, object_pairs_hook=pairs)


def lines(stream):
    """Yield a bounded line or None for an overlong request, then recover."""
    while True:
        line = stream.readline(MAX_LINE + 1)
        if not line:
            return
        if len(line.encode("utf-8")) > MAX_LINE:
            while line and not line.endswith("\n"):
                line = stream.readline(MAX_LINE + 1)
            yield None
        else:
            yield line


def respond(service, line):
    request_id = None
    try:
        if line is None:
            raise GameError("REQUEST_TOO_LARGE", "JSON line exceeds 1 MiB")
        req = strict_json(line)
        fields(req, ("id", "method", "params"), ("method",))
        request_id = req.get("id")
        if request_id is not None and (isinstance(request_id, (dict, list, bool)) or not isinstance(request_id, (str, int))):
            raise GameError("INVALID_REQUEST", "id must be a string, integer or null")
        if not isinstance(req["method"], str):
            raise GameError("INVALID_REQUEST", "method must be a string")
        return {"id": request_id, "result": dispatch(service, req["method"], req.get("params", {}))}
    except (ValueError, RecursionError):
        return {"id": request_id, "error": {"code": "INVALID_JSON", "message": "Malformed JSON", "details": None}}
    except GameError as exc:
        return {"id": request_id, **exc.as_dict()}
    except Exception:
        return {"id": request_id, "error": {"code": "INTERNAL_ERROR", "message": "Request could not be processed", "details": None}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/porn.sqlite3")
    args = parser.parse_args()
    service = GameService(args.db)
    try:
        for line in lines(sys.stdin):
            print(json.dumps(respond(service, line), ensure_ascii=False, allow_nan=False), flush=True)
    finally:
        service.close()


if __name__ == "__main__":
    main()
