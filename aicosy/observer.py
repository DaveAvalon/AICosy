"""Read-only human projections derived from persisted game state and events."""
from __future__ import annotations

from . import engine

CLIENT_LABELS = {
    "rule-script": "规则脚本", "random-script": "随机脚本",
    "model-client": "模型客户端（接入方声明）", "live-assistant": "对话 AI（接入方声明）",
    "unspecified": "未注明接入类型",
}


def compact_outcome(outcome):
    if not outcome:
        return None
    keys = ("kind", "mode", "target", "cost", "completed", "correct", "novel",
            "abandoned_mode", "performance_id", "source_id", "summary", "trace_hash", "exact_repeat", "experience", "run_id", "parent_run_id", "parent_tick", "known_cycle", "piece_id")
    return {key: outcome[key] for key in keys if key in outcome}


def session_summary(row, state, events, *, now, activity_timeout):
    observation = engine.observe(state)
    visible = observation.get("observation", {})
    area = visible.get("active_experience")
    ended = state["state"] == "ended"
    active = not ended and 0 <= now-row["last_activity"] < activity_timeout
    metadata = state.get("client_info", {})
    kind = metadata.get("kind", "unspecified")
    outcomes = [event["outcome"] for event in events]
    saved = visible.get("saved_experiences", [])
    last = events[-1] if events else {}
    return {
        "session_id": row["id"], "player_id": row["player_id"], "model_id": row["model_id"],
        "engine_version": state.get("engine_version", 1), "mode": row["mode"], "condition": row["condition"],
        "state": state["state"], "activity": "ended" if ended else "active" if active else "idle",
        "turn": state["turn"], "max_turns": state["max_turns"], "energy": state["resources"]["energy"],
        "area": {key: area[key] for key in ("id", "mode", "label") if key in area} if area else None,
        "created_at": row["created"], "last_activity": row["last_activity"], "ended_at": row["ended"],
        "client_info": {"kind": kind, "label": metadata.get("label") or CLIENT_LABELS.get(kind, CLIENT_LABELS["unspecified"]), "verified": False},
        "counts": {
            "actions": sum(event.get("action") is not None for event in events),
            "replays": sum(o.get("kind") == "replay" for o in outcomes),
            "reperformances": sum(o.get("kind") == "reperform" for o in outcomes),
            "interactive_starts": sum(o.get("kind") == "begin" for o in outcomes),
            "extensions": sum(o.get("kind") == "extend" for o in outcomes),
            "holds": sum(o.get("kind") == "hold" for o in outcomes),
            "taps": sum(o.get("kind") == "tap" for o in outcomes),
            "piece_selections": sum(o.get("kind") == "select_piece" for o in outcomes),
            "forks": sum(o.get("kind") == "fork" for o in outcomes),
            "revisions": sum(o.get("kind") == "revise" for o in outcomes),
            "saved_experiences": len(saved),
        },
        "last_action": last.get("action"), "last_outcome": compact_outcome(state.get("last_outcome")),
        "end_reason": state.get("end_reason"),
    }
