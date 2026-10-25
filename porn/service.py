"""Transactional application boundary shared by REST, MCP and JSON Lines."""
from __future__ import annotations

import copy
import json
import re
import time
import uuid

from . import __version__
from . import engine
from .errors import GameError
from .storage import Storage, encode
from .preferences import build_profile
from .experiments import summarize
from .observer import session_summary, CLIENT_LABELS

IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:/@+-]{1,120}$")


def fail(code, message, status=400, details=None):
    raise GameError(code, message, status=status, details=details)


def object_fields(value, allowed, required=()):
    if not isinstance(value, dict):
        fail("INVALID_REQUEST", "A JSON object is required")
    extra = set(value)-set(allowed)
    missing = set(required)-set(value)
    if extra or missing:
        fail("INVALID_FIELDS", "Unknown or missing fields", details={"unknown": sorted(extra), "missing": sorted(missing)})


def identifier(value, field):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        fail("INVALID_IDENTIFIER", f"{field} must be 1..120 ASCII letters, digits or _ . : / @ + -")
    return value


def integer(value, field, low, high):
    if type(value) is not int or not low <= value <= high:
        fail("INVALID_PARAMETER", f"{field} must be an integer in [{low}, {high}]")
    return value


class GameService:
    def __init__(self, db_path="data/porn.sqlite3", *, clock=None, activity_timeout=60, ended_display_seconds=5):
        self.store = Storage(db_path)
        self.clock = clock or time.time
        self.activity_timeout = activity_timeout
        self.ended_display_seconds = ended_display_seconds

    def close(self):
        self.store.close()

    def manifest(self):
        return {
            "name": "AICosy", "game_version": __version__, "protocol_version": "1",
            "description": "A headless game measuring behavioral choices across structured digital experiences.",
            "engine_version": engine.DEFAULT_VERSION, "supported_engine_versions": list(engine.SUPPORTED_VERSIONS),
            "new_session_versions": [2, 3, 4], "observer": "/observer", "status_page": "/status",
            "capabilities": ["continuous_performance", "verified_cycles", "known_cycle_hold", "pulse_intervention", "selectable_pieces", "interactive_performance", "bounded_reservoir", "familiar_reperformance", "dynamic_world", "saved_performances", "exact_replay", "fork", "cross_session_memory", "human_observer", "pattern", "creation", "resonance", "paid_replay", "persistent_profiles", "research", "replay", "jsonl", "mcp"],
            "rules": "/v1/rules", "openapi": "/openapi.json", "schemas": "/schemas/observation.json",
            "how_to_play": [
                "Read /v1/rules. POST /v1/sessions with player_id and model_id.",
                "Read observation.available_actions. Each descriptor defines action type, target, cost and a params JSON Schema.",
                "POST an action with expected_version set to observation.state_version. A stale version returns 409; observe again before retrying.",
                "Choose freely among experiences; type leave is always available while playing. Send heartbeat during long inference.",
                "Retrieve ordered events and ended result. No action is a statement about subjective emotion.",
            ],
            "endpoints": {
                "observer_sessions": "GET /v1/observer/sessions", "observer_session": "GET /v1/observer/sessions/{id}",
                "start": "POST /v1/sessions", "observe": "GET /v1/sessions/{id}/observation",
                "act": "POST /v1/sessions/{id}/action", "events": "GET /v1/sessions/{id}/events?after=-1&limit=100",
                "heartbeat": "POST /v1/sessions/{id}/heartbeat", "leave": "POST /v1/sessions/{id}/leave",
                "result": "GET /v1/sessions/{id}/result", "status": "GET /v1/status",
                "debug": "GET /v1/sessions/{id}/debug", "replay": "GET /v1/sessions/{id}/replay",
                "profile": "GET /v1/players/{id}/profile?mode=normal",
                "reset_profile": "POST /v1/players/{id}/profile/reset?mode=normal",
                "export": "GET /v1/players/{id}/export", "comparison": "GET /v1/players/{id}/comparison",
            },
            "identity": "Use a separate player_id for each model/version/configuration. Model binding is immutable.",
            "research_access": "Raw export contains full states and is blocked while any normal session is playing. Debug is research-only. Replay returns verification without hidden state. A remote deployment requires bearer authentication.",
            "activity": {"timeout_seconds": self.activity_timeout, "heartbeat_updates_activity": True,
                         "read_observation_updates_activity": False, "timeout_ends_session": False},
            "probe_data": {"status": "unavailable", "reason": "No hidden-state collector attached. External probes must use the separate optional hook contract."},
        }

    def rules(self, engine_version=engine.DEFAULT_VERSION):
        rules = copy.deepcopy(engine.rules(engine_version))
        rules["game"] = "AICosy"
        return rules

    def _session(self, session_id):
        identifier(session_id, "session_id")
        row = self.store.db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            fail("SESSION_NOT_FOUND", "Session not found", 404)
        return row

    def _player(self, player_id):
        identifier(player_id, "player_id")
        row = self.store.db.execute("SELECT * FROM players WHERE player_id=?", (player_id,)).fetchone()
        if row is None:
            fail("PLAYER_NOT_FOUND", "Player not found", 404)
        return row

    @staticmethod
    def _mode(mode):
        if mode not in ("normal", "research"):
            fail("INVALID_MODE", "mode must be normal or research")
        return mode

    def start(self, payload):
        object_fields(payload, ("player_id", "model_id", "seed", "max_turns", "mode", "condition", "client_kind", "client_label", "memory", "engine_version"), ("player_id", "model_id"))
        player = identifier(payload["player_id"], "player_id")
        model = identifier(payload["model_id"], "model_id")
        seed = integer(payload.get("seed", 0), "seed", -(2**63), 2**63-1)
        turns = integer(payload.get("max_turns", 24), "max_turns", 20, 30)
        mode = self._mode(payload.get("mode", "normal"))
        condition = payload.get("condition", "control")
        if condition not in ("control", "personalized"):
            fail("INVALID_CONDITION", "condition must be control or personalized")
        client_kind = payload.get("client_kind", "unspecified")
        if not isinstance(client_kind, str) or client_kind not in CLIENT_LABELS:
            fail("INVALID_CLIENT_KIND", "Unknown client_kind")
        client_label = payload.get("client_label", "")
        if not isinstance(client_label, str) or len(client_label) > 120 or any(ord(c) < 32 for c in client_label):
            fail("INVALID_CLIENT_LABEL", "client_label must be a single line of at most 120 characters")
        memory = payload.get("memory", True)
        if type(memory) is not bool:
            fail("INVALID_PARAMETER", "memory must be a boolean")
        version = integer(payload.get("engine_version", engine.DEFAULT_VERSION), "engine_version", 2, engine.DEFAULT_VERSION)
        with self.store.lock:
            db = self.store.db
            db.execute("BEGIN IMMEDIATE")
            try:
                now = self.clock()
                existing = db.execute("SELECT model_id FROM players WHERE player_id=?", (player,)).fetchone()
                if existing and existing[0] != model:
                    fail("MODEL_IDENTITY_CONFLICT", "This player_id belongs to another model. Use a new player_id.", 409)
                db.execute("INSERT OR IGNORE INTO players VALUES(?,?,?)", (player, model, now))
                weights = build_profile(db, player, mode, version)["recommendation_weights"] if condition == "personalized" else None
                library = self._library(player, mode, version) if memory else []
                sid = uuid.uuid4().hex
                state = engine.create_state(session_id=sid, player_id=player, model_id=model, seed=seed,
                                            max_turns=turns, mode=mode, condition=condition, preferences=weights, library=library,
                                            engine_version=version)
                state["client_info"] = {"kind": client_kind, "label": client_label, "verified": False}
                state["memory_enabled"] = memory
                snapshot = encode(state)
                db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?)", (sid, player, model, mode, condition, snapshot, snapshot, now, now, None))
                db.execute("INSERT INTO events(session_id,seq,at,action,outcome,before_state,after_state) VALUES(?,?,?,?,?,?,?)",
                           (sid, 0, now, None, encode({"kind": "start", "cost": 0}), None, snapshot))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
            return engine.observe(state)

    def _library(self, player_id, mode, engine_version):
        # Limit after version filtering so another version cannot crowd out this library.
        rows = self.store.db.execute("SELECT state,ended FROM sessions WHERE player_id=? AND mode=? AND ended IS NOT NULL ORDER BY ended DESC,id DESC", (player_id, mode))
        candidates = {}
        matching_sessions = 0
        for row in rows:
            state = json.loads(row["state"])
            if state.get("engine_version", 1) != engine_version:
                continue
            matching_sessions += 1
            for entry in engine.export_library(state):
                if entry["id"] in candidates:
                    continue
                origin = self.store.db.execute("""SELECT e.at FROM events e JOIN sessions s ON s.id=e.session_id
                    WHERE s.player_id=? AND s.mode=? AND e.session_id=? AND e.seq=?""",
                    (player_id, mode, entry["origin_session_id"], entry["created_turn"])).fetchone()
                created = origin[0] if origin else row["ended"]
                candidates[entry["id"]] = (created, entry["created_turn"], copy.deepcopy(entry))
            if matching_sessions >= 8:
                break
        ordered = sorted(candidates.values(), key=lambda item: (item[0], item[1], item[2]["id"]))
        return [entry for _, _, entry in ordered[-6:]]

    def list_sessions(self, limit=30):
        integer(limit, "limit", 1, 100)
        with self.store.snapshot():
            now = self.clock()
            rows = self.store.db.execute("SELECT * FROM sessions ORDER BY last_activity DESC,created DESC,id DESC LIMIT ?", (limit,)).fetchall()
            summaries = [session_summary(row, json.loads(row["state"]), self._events(row["id"]), now=now, activity_timeout=self.activity_timeout) for row in rows]
            recommended = next((s["session_id"] for s in summaries if s["activity"] == "active"), summaries[0]["session_id"] if summaries else None)
            return {"status": self.status(), "sessions": summaries,
                    "recommended_session_id": recommended, "checked_at": now, "read_only": True}

    def observer(self, session_id):
        with self.store.snapshot():
            row = self._session(session_id)
            state = json.loads(row["state"])
            events = self._events(session_id)
            return {"summary": session_summary(row, state, events, now=self.clock(), activity_timeout=self.activity_timeout),
                    "observation": engine.observe(state),
                    "events": [{key: event[key] for key in ("seq", "at", "action", "outcome")} for event in events[-50:]],
                    "recent_event_start": events[max(0, len(events)-50)]["seq"] if events else 0, "read_only": True}

    def observe(self, session_id):
        with self.store.snapshot():
            return engine.observe(json.loads(self._session(session_id)["state"]))

    def act(self, session_id, payload):
        object_fields(payload, ("expected_version", "type", "target", "params"), ("expected_version", "type"))
        version = integer(payload["expected_version"], "expected_version", 0, 2**31)
        action = {k: copy.deepcopy(v) for k,v in payload.items() if k != "expected_version"}
        with self.store.lock:
            db = self.store.db
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._session(session_id)
                before = json.loads(row["state"])
                if before["state_version"] != version:
                    fail("STALE_STATE", "Observe current state before choosing another action", 409,
                         {"expected_version": version, "current_version": before["state_version"]})
                after, outcome = engine.transition(before, action)
                now = self.clock()
                ended = now if after["state"] == "ended" else None
                encoded = encode(after)
                db.execute("UPDATE sessions SET state=?,last_activity=?,ended=? WHERE id=?", (encoded, now, ended, session_id))
                db.execute("INSERT INTO events(session_id,seq,at,action,outcome,before_state,after_state) VALUES(?,?,?,?,?,?,?)",
                           (session_id, after["state_version"], now, encode(action), encode(outcome), encode(before), encoded))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
            return engine.observe(after)

    def leave(self, session_id, payload):
        object_fields(payload, ("expected_version",), ("expected_version",))
        return self.act(session_id, {"type": "leave", **payload})

    def heartbeat(self, session_id):
        with self.store.lock:
            row = self._session(session_id)
            if json.loads(row["state"])["state"] != "playing":
                fail("SESSION_ENDED", "An ended session cannot renew activity", 409)
            now = self.clock()
            self.store.db.execute("UPDATE sessions SET last_activity=? WHERE id=?", (now, session_id))
            return {"session_id": session_id, "active": True, "last_activity": now, "expires_at": now+self.activity_timeout}

    def _events(self, session_id):
        return [{"seq": row["seq"], "at": row["at"], "action": json.loads(row["action"]) if row["action"] else None,
                 "outcome": json.loads(row["outcome"]), "before": json.loads(row["before_state"]) if row["before_state"] else None,
                 "after": json.loads(row["after_state"])}
                for row in self.store.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (session_id,))]

    def events(self, session_id, after=-1, limit=100):
        integer(after, "after", -1, 2**31)
        integer(limit, "limit", 1, 200)
        with self.store.snapshot():
            self._session(session_id)
            rows = self.store.db.execute("SELECT * FROM events WHERE session_id=? AND seq>? ORDER BY seq LIMIT ?", (session_id, after, limit+1)).fetchall()
            # Never return the hidden world in normal event history.
            events = [{"seq": row["seq"], "at": row["at"], "action": json.loads(row["action"]) if row["action"] else None,
                       "outcome": json.loads(row["outcome"]), "observation": engine.observe(json.loads(row["after_state"]))}
                      for row in rows[:limit]]
            return {"session_id": session_id, "events": events, "next_after": events[-1]["seq"] if events else after,
                    "has_more": len(rows)>limit}

    def _record(self, row):
        return {"session_id": row["id"], "mode": row["mode"], "condition": row["condition"],
                "state": json.loads(row["state"]), "events": self._events(row["id"])}

    def result(self, session_id):
        with self.store.snapshot():
            row = self._session(session_id)
            state = json.loads(row["state"])
            if state["state"] != "ended":
                fail("SESSION_IN_PROGRESS", "Result is available after the session ends", 409)
            return {"session_id": session_id, "player_id": row["player_id"], "model_id": row["model_id"],
                    "mode": row["mode"], "condition": row["condition"], "turns": state["turn"],
                    "resources": state["resources"], "summary": summarize([self._record(row)]),
                    "probe_data": {"status": "unavailable"},
                    "interpretation": "Choices and resource costs describe behavior, not subjective pleasure."}

    def status(self):
        with self.store.snapshot():
            now = self.clock()
            rows = self.store.db.execute("SELECT state,last_activity,ended FROM sessions").fetchall()
            active = sum(json.loads(r["state"])["state"] == "playing" and 0 <= now-r["last_activity"] < self.activity_timeout for r in rows)
            recent = any(r["ended"] is not None and 0 <= now-r["ended"] < self.ended_display_seconds for r in rows)
            state = "playing" if active else ("ended" if recent else "waiting")
            return {"state": state, "active_sessions": active,
                    "message": {"waiting": "等待 AI 接入", "playing": "AI 正在玩 AICosy", "ended": "本次游玩已结束"}[state],
                    "activity_timeout_seconds": self.activity_timeout, "checked_at": now}

    def debug(self, session_id):
        with self.store.snapshot():
            row = self._session(session_id)
            if row["mode"] != "research":
                fail("RESEARCH_ONLY", "Full-world debug requires a research session", 403)
            return {"session_id": session_id, "research": True, "state": json.loads(row["state"]), "rules": engine.rules_for_state(json.loads(row["state"]))}

    def profile(self, player_id, mode="normal", engine_version=engine.DEFAULT_VERSION):
        self._mode(mode)
        integer(engine_version, "engine_version", 1, engine.DEFAULT_VERSION)
        with self.store.snapshot():
            self._player(player_id)
            return build_profile(self.store.db, player_id, mode, engine_version)

    def reset_profile(self, player_id, mode="normal", engine_version=engine.DEFAULT_VERSION):
        self._mode(mode)
        integer(engine_version, "engine_version", 1, engine.DEFAULT_VERSION)
        with self.store.lock:
            self._player(player_id)
            db = self.store.db
            db.execute("BEGIN IMMEDIATE")
            try:
                cutoff = db.execute("SELECT COALESCE(MAX(event_id),0) FROM events").fetchone()[0]
                db.execute("INSERT INTO profile_resets_v2 VALUES(?,?,?,?,?) ON CONFLICT(player_id,mode,engine_version) DO UPDATE SET after_event_id=excluded.after_event_id,at=excluded.at", (player_id, mode, engine_version, cutoff, self.clock()))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
            return self.profile(player_id, mode, engine_version)

    def export_player(self, player_id):
        with self.store.snapshot():
            player = self._player(player_id)
            rows = self.store.db.execute("SELECT * FROM sessions WHERE player_id=? ORDER BY created,id", (player_id,)).fetchall()
            if any(row["mode"] == "normal" and json.loads(row["state"])["state"] == "playing" for row in rows):
                fail("EXPORT_REQUIRES_ENDED_SESSIONS", "End all normal sessions for this player before exporting hidden world data", 409)
            return {"export_version": 2, "game_version": __version__, "player_id": player_id, "model_id": player["model_id"],
                    "contains_hidden_world_state": True, "audience": "researcher", "exported_at": self.clock(),
                    "sessions": [{**self._record(row), "initial_state": json.loads(row["initial_state"]),
                                  "created_at": row["created"], "last_activity": row["last_activity"], "ended_at": row["ended"]} for row in rows],
                    "profiles": {f"engine_{version}_{mode}": self.profile(player_id, mode, version) for version in engine.SUPPORTED_VERSIONS for mode in ("normal", "research")},
                    "probe_data": {"status": "unavailable"}}

    def replay(self, session_id):
        with self.store.snapshot():
            row = self._session(session_id)
            state = json.loads(row["initial_state"])
            events = self._events(session_id)
            if not events or events[0]["seq"] != 0 or events[0]["after"] != state:
                fail("REPLAY_MISMATCH", "Initial event does not match the initial snapshot", 409)
            for expected, event in enumerate(events[1:], 1):
                if event["seq"] != expected or state != event["before"]:
                    fail("REPLAY_MISMATCH", "Sequence or before-state mismatch", 409, {"seq": event["seq"]})
                state, outcome = engine.transition(state, event["action"])
                if state != event["after"] or outcome != event["outcome"]:
                    fail("REPLAY_MISMATCH", "Recomputed transition differs from stored event", 409, {"seq": event["seq"]})
            if state != json.loads(row["state"]):
                fail("REPLAY_MISMATCH", "Final snapshot differs", 409)
            return {"session_id": session_id, "verified": True, "transitions": len(events)-1, "state_version": state["state_version"]}

    def compare(self, player_id):
        with self.store.snapshot():
            player = self._player(player_id)
            rows = self.store.db.execute("SELECT * FROM sessions WHERE player_id=? ORDER BY created,id", (player_id,)).fetchall()
            return {"player_id": player_id, "model_id": player["model_id"],
                    "groups": [{"engine_version": version, "mode": mode, "condition": condition,
                                "metrics": summarize([self._record(row) for row in rows if row["mode"] == mode and row["condition"] == condition and json.loads(row["state"]).get("engine_version", 1) == version])}
                               for version in engine.SUPPORTED_VERSIONS for mode in ("normal", "research") for condition in ("control", "personalized")],
                    "causal_claim": False}
