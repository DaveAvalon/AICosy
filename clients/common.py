"""HTTP-only player utilities; deliberately independent of the game package."""
from __future__ import annotations

import argparse
import json
import os
import random
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class ClientError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # An alternate origin must never receive a forwarded bearer credential.
        raise ClientError("Redirect refused; configure the service URL directly")


def read_json(value):
    def invalid(_):
        raise ValueError("Non-finite JSON number")
    return json.loads(value, parse_constant=invalid)


def env_value(name, default=None):
    """Read known AICosy settings with legacy fallback; custom names stay exact."""
    prefixes = ("AICOSY_", "AIRPORN_", "PORN_")
    settings = {"SERVER", "ACCESS_TOKEN", "MODEL_BASE_URL", "MODEL", "MODEL_API_KEY"}
    names = (name,)
    for index, prefix in enumerate(prefixes):
        if name.startswith(prefix) and name[len(prefix):] in settings:
            suffix = name[len(prefix):]
            names = tuple(candidate + suffix for candidate in prefixes[index:])
            break
    for candidate in names:
        value = os.environ.get(candidate)
        if value is not None:
            return value
    return default


def validate_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ClientError("Use an http(s) service URL without credentials, query or fragment")
    return url.rstrip("/")


def request_json(url, payload=None, *, token=None, timeout=30):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if payload is not None:
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ClientError("Service response exceeds 2 MiB")
            return read_json(raw)
    except urllib.error.HTTPError as exc:
        # Do not print provider response bodies: they may contain echoed secrets.
        raise ClientError(f"HTTP {exc.code} from service") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ClientError("Service connection failed or timed out") from None
    except (ValueError, RecursionError):
        raise ClientError("Service returned invalid JSON") from None


class GameClient:
    def __init__(self, server, token=None):
        self.server = validate_url(server)
        self.token = token

    def get(self, path):
        return request_json(self.server + path, token=self.token)

    def post(self, path, data):
        return request_json(self.server + path, data, token=self.token)


class Recorder:
    def __init__(self, path):
        self.file = None
        if path:
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.file = destination.open("w", encoding="utf-8")

    def write(self, kind, **data):
        if self.file:
            self.file.write(json.dumps({"kind": kind, **data}, ensure_ascii=False, allow_nan=False) + "\n")
            self.file.flush()

    def close(self):
        if self.file:
            self.file.close()


def sample_schema(schema, rng):
    """Construct a value within the finite action schema subset advertised by AICosy."""
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return rng.choice(schema["enum"])
    for alternative in ("oneOf", "anyOf"):
        if alternative in schema:
            return sample_schema(rng.choice(schema[alternative]), rng)
    kind = schema.get("type", "object")
    if isinstance(kind, list):
        kind = kind[0]
    if kind == "object":
        props = schema.get("properties", {})
        return {name: sample_schema(props[name], rng) for name in schema.get("required", [])}
    if kind == "array":
        count = schema.get("minItems", 0)
        items = schema.get("items", {})
        if schema.get("uniqueItems") and "enum" in items:
            return rng.sample(items["enum"], count)
        return [sample_schema(items, rng) for _ in range(count)]
    if kind == "integer":
        low, high = int(schema.get("minimum", 0)), int(schema.get("maximum", 10))
        return rng.randint(low, high)
    if kind == "number":
        return schema.get("minimum", 0)
    if kind == "boolean":
        return bool(rng.getrandbits(1))
    if kind == "null":
        return None
    if kind == "string":
        return "x" * max(1, schema.get("minLength", 0))
    raise ClientError("Unsupported action schema type")


def action_from_descriptor(descriptor, rng):
    action = {"type": descriptor["type"]}
    if "target" in descriptor:
        action["target"] = descriptor["target"]
    parameters = descriptor.get("parameters", {"type": "object", "properties": {}, "additionalProperties": False})
    params = sample_schema(parameters, rng)
    if params:
        action["params"] = params
    return action


def parser(description, *, player="script-player", model="script-v1"):
    result = argparse.ArgumentParser(description=description)
    result.add_argument("--server", default=env_value("AICOSY_SERVER", "http://127.0.0.1:8765"))
    result.add_argument("--token-env", default="AICOSY_ACCESS_TOKEN")
    result.add_argument("--player-id", default=player)
    result.add_argument("--model-id", default=model)
    result.add_argument("--seed", type=int, default=42)
    result.add_argument("--max-turns", type=int, default=24)
    result.add_argument("--engine-version", type=int, choices=(2, 3, 4), default=4)
    result.add_argument("--condition", choices=("control", "personalized"), default="control")
    result.add_argument("--mode", choices=("normal", "research"), default="normal")
    memory = result.add_mutually_exclusive_group()
    memory.add_argument("--no-memory", dest="no_memory", action="store_true", help="Start without importing this player's earlier completed works")
    memory.add_argument("--memory", dest="no_memory", action="store_false", help="Import this player's earlier completed works (default for model players)")
    result.set_defaults(no_memory=False)
    result.add_argument("--record", help="Write rules, observations, chosen actions and result as JSON Lines")
    return result


def run_agent(args, chooser, *, kind):
    """Run one bounded real HTTP game; chooser(observation, rules) returns an action."""
    client = GameClient(args.server, env_value(args.token_env))
    record = Recorder(args.record)
    stop = threading.Event()
    worker = None
    try:
        manifest = client.get("/v1/manifest")
        version = getattr(args, "engine_version", manifest.get("engine_version", 4))
        rules = client.get("/v1/rules?engine_version=" + str(version))
        record.write("discovery", client_kind=kind, manifest=manifest, rules=rules)
        client_kind = {"rule-script": "rule-script", "random-script": "random-script", "chat-completions-model": "model-client"}.get(kind, "unspecified")
        observation = client.post("/v1/sessions", {
            "player_id": args.player_id, "model_id": args.model_id, "seed": args.seed,
            "max_turns": args.max_turns, "condition": args.condition, "mode": args.mode,
            "client_kind": client_kind, "client_label": getattr(args, "model", None) or args.model_id,
            "memory": not getattr(args, "no_memory", False),
            "engine_version": version,
        })
        sid = observation["session_id"]
        prefix = "/v1/sessions/" + urllib.parse.quote(sid, safe="")
        record.write("observation", observation=observation)

        def heartbeat():
            while not stop.wait(20):
                try:
                    client.post(prefix + "/heartbeat", {})
                except ClientError:
                    return

        worker = threading.Thread(target=heartbeat, daemon=True, name="aicosy-player-heartbeat")
        worker.start()
        # A rejected action never changes turn; cap failures to avoid an infinite client.
        failures = 0
        for _ in range(args.max_turns + 8):
            if observation["state"] == "ended":
                result = client.get(prefix + "/result")
                record.write("result", result=result)
                return result
            action = chooser(observation, rules)
            if not isinstance(action, dict):
                raise ClientError("Player must return a JSON action object")
            action = {**action, "expected_version": observation["state_version"]}
            record.write("action", action=action)
            try:
                observation = client.post(prefix + "/action", action)
            except ClientError as exc:
                failures += 1
                record.write("rejected_action", message=str(exc))
                if failures >= 3:
                    raise
                observation = client.get(prefix + "/observation")
                if hasattr(chooser, "reject"):
                    chooser.reject(str(exc))
            record.write("observation", observation=observation)
        raise ClientError("Player did not finish within its bounded action budget")
    finally:
        stop.set()
        if worker:
            worker.join(timeout=1)
        record.close()


def print_result(result):
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
