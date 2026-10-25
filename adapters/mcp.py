"""AICosy MCP stdio adapter, JSON-RPC 2.0 and newline-delimited UTF-8 transport."""
from __future__ import annotations

import argparse
import json
import sys
from adapters.cli import dispatch, fields, lines, strict_json
from aicosy import __version__
from aicosy.errors import GameError
from aicosy.service import GameService

SUPPORTED = ("2024-11-05", "2025-03-26")


def obj(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}


SID = {"type": "string", "minLength": 1, "maxLength": 120}
VERSION = {"type": "integer", "minimum": 0}
START = obj({"player_id": SID, "model_id": SID, "seed": {"type": "integer"}, "max_turns": {"type": "integer", "minimum": 20, "maximum": 30}, "mode": {"enum": ["normal", "research"]}, "condition": {"enum": ["control", "personalized"]}, "client_kind": {"enum": ["unspecified", "rule-script", "random-script", "model-client", "live-assistant"]}, "client_label": {"type": "string", "maxLength": 120}, "memory": {"type": "boolean"}}, ("player_id", "model_id"))
START["properties"]["engine_version"] = {"type": "integer", "enum": [2, 3, 4], "default": 4}
ACTION = obj({"expected_version": VERSION, "type": {"type": "string"}, "target": {"type": "string"}, "params": {"type": "object"}}, ("expected_version", "type"))
TOOL_DEFS = [
    ("rules", "Read structured game rules. Start a session, then choose freely from each observation's available_actions.", obj({"engine_version": {"type": "integer", "enum": [1, 2, 3, 4], "default": 4}})),
    ("start", "Create a game session; player_id must stay bound to one model identity.", START),
    ("observe", "Observe a session and its legal actions without renewing activity.", obj({"session_id": SID}, ("session_id",))),
    ("act", "Perform a legal action with current expected_version; unknown or stale actions return errors.", obj({"session_id": SID, "action": ACTION}, ("session_id", "action"))),
    ("status", "Read real connection status across sessions.", obj()),
    ("leave", "Voluntarily leave a game at no resource cost.", obj({"session_id": SID, "expected_version": VERSION}, ("session_id", "expected_version"))),
    ("heartbeat", "Renew a playing session's activity during long inference.", obj({"session_id": SID}, ("session_id",))),
    ("events", "Read ordered visible observations and choices incrementally.", obj({"session_id": SID, "after": {"type": "integer", "minimum": -1}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}, ("session_id",))),
    ("result", "Read an ended session's behavioral result.", obj({"session_id": SID}, ("session_id",))),
]
TOOLS = [{"name": "aicosy_" + name, "description": desc, "inputSchema": schema} for name, desc, schema in TOOL_DEFS]
TOOL_METHODS = {prefix + name: name for prefix in ("aicosy_", "airporn_", "porn_") for name, _, _ in TOOL_DEFS}


def error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class MCPServer:
    def __init__(self, service):
        self.service = service
        self.initialized = False
        self.ready = False

    def message(self, req):
        if isinstance(req, list):
            if not req or not self.ready:
                return error(None, -32600, "Invalid batch or initialization has not completed")
            replies = [self.message(item) for item in req]
            return [reply for reply in replies if reply is not None] or None
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0" or not isinstance(req.get("method"), str):
            return error(None, -32600, "Invalid JSON-RPC request")
        request_id = req.get("id")
        if request_id is not None and (type(request_id) not in (int, str)):
            return error(None, -32600, "Invalid request id")
        method = req["method"]
        params = req.get("params", {})
        notification = "id" not in req
        if notification:
            if method == "notifications/initialized" and self.initialized:
                self.ready = True
            return None
        if method == "initialize":
            if self.initialized:
                return error(request_id, -32600, "Already initialized")
            if not isinstance(params, dict) or not isinstance(params.get("protocolVersion"), str) or not isinstance(params.get("capabilities"), dict) or not isinstance(params.get("clientInfo"), dict):
                return error(request_id, -32602, "Initialization requires protocolVersion, capabilities and clientInfo")
            self.initialized = True
            return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": params["protocolVersion"] if params["protocolVersion"] in SUPPORTED else SUPPORTED[-1], "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "aicosy-game", "version": __version__}, "instructions": "AICosy: use aicosy_rules, aicosy_start, then choose available actions. You may leave at any time. Behavioral choices do not establish subjective pleasure."}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}
        if not self.ready:
            return error(request_id, -32002, "Initialize and send notifications/initialized first")
        if method == "tools/list":
            if not isinstance(params, dict) or set(params) - {"_meta"} or ("_meta" in params and not isinstance(params["_meta"], dict)):
                return error(request_id, -32602, "No pagination cursor is available")
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
        if method == "tools/call":
            if not isinstance(params, dict) or set(params) - {"name", "arguments", "_meta"} or not isinstance(params.get("name"), str) or params["name"] not in TOOL_METHODS:
                return error(request_id, -32602, "Unknown tool or invalid parameters")
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                return error(request_id, -32602, "Tool arguments must be an object")
            try:
                result = dispatch(self.service, TOOL_METHODS[params["name"]], arguments)
                return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, allow_nan=False)}], "isError": False}}
            except GameError as exc:
                return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(exc.as_dict(), ensure_ascii=False)}], "isError": True}}
            except Exception:
                return error(request_id, -32603, "Request could not be processed")
        return error(request_id, -32601, "Method not found")

    def line(self, line):
        if line is None:
            return error(None, -32600, "JSON line exceeds 1 MiB")
        try:
            return self.message(strict_json(line))
        except (ValueError, RecursionError):
            return error(None, -32700, "Malformed JSON")
        except Exception:
            return error(None, -32603, "Request could not be processed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/porn.sqlite3")
    args = parser.parse_args()
    service = GameService(args.db)
    server = MCPServer(service)
    try:
        for line in lines(sys.stdin):
            response = server.line(line)
            if response is not None:
                print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)
    finally:
        service.close()


if __name__ == "__main__":
    main()
