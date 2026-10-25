"""Behavioral profiles derived from accepted transitions, never model self-report."""
from __future__ import annotations

import json

MODES = ("pattern", "creation", "resonance")


def build_profile(db, player_id, mode, engine_version=4):
    player = db.execute("SELECT * FROM players WHERE player_id=?", (player_id,)).fetchone()
    reset = db.execute("SELECT after_event_id,at FROM profile_resets_v2 WHERE player_id=? AND mode=? AND engine_version=?", (player_id, mode, engine_version)).fetchone()
    cutoff = reset[0] if reset else 0
    result = {
        "player_id": player_id, "model_id": player["model_id"], "mode": mode, "engine_version": engine_version,
        "basis": "accepted behavior after the most recent profile reset",
        "reset_after_event_id": cutoff, "sessions": 0,
        "experiences": {name: {"selections": 0, "replays": 0, "reperformances": 0, "performances": 0, "interactive_starts": 0, "extensions": 0, "holds": 0, "taps": 0, "piece_selections": 0, "forks": 0, "revisions": 0, "restores": 0, "abandons": 0,
                                "energy_spent": 0, "replay_energy_spent": 0} for name in MODES},
        "interpretation": "Behavioral preference only; no inference of subjective pleasure.",
    }
    rows = db.execute("""SELECT e.*,s.condition FROM events e JOIN sessions s ON s.id=e.session_id
                         WHERE s.player_id=? AND s.mode=? AND e.event_id>? ORDER BY e.event_id""",
                      (player_id, mode, cutoff)).fetchall()
    seen = set()
    for row in rows:
        if json.loads(row["after_state"]).get("engine_version", 1) != engine_version:
            continue
        seen.add(row["session_id"])
        outcome = json.loads(row["outcome"])
        abandoned_mode = outcome.get("abandoned_mode") or outcome.get("abandoned", {}).get("mode")
        if abandoned_mode in result["experiences"]:
            result["experiences"][abandoned_mode]["abandons"] += 1
        name = outcome.get("mode")
        if name not in result["experiences"]:
            continue
        bucket = result["experiences"][name]
        kind = outcome.get("kind")
        if kind == "selection":
            bucket["selections"] += 1
        elif kind == "replay":
            bucket["replays"] += 1
            bucket["replay_energy_spent"] += outcome.get("cost", 0)
        elif kind == "fork":
            bucket["forks"] += 1
        elif kind == "reperform":
            bucket["reperformances"] += 1
        elif kind == "perform":
            bucket["performances"] += 1
        elif kind == "begin":
            bucket["interactive_starts"] += 1
        elif kind == "extend":
            bucket["extensions"] += 1
        elif kind == "hold":
            bucket["holds"] += 1
        elif kind == "tap":
            bucket["taps"] += 1
        elif kind == "select_piece":
            bucket["piece_selections"] += 1
        elif kind == "revise":
            bucket["revisions"] += 1
        elif kind == "restore":
            bucket["restores"] += 1
        elif kind == "abandon":
            bucket["abandons"] += 1
        bucket["energy_spent"] += outcome.get("cost", 0)
    result["sessions"] = len(seen)
    # Used only for offering order. All areas remain accessible.
    result["recommendation_weights"] = {
        name: bucket["selections"] + 2 * bucket["replays"] + bucket["revisions"] - bucket["abandons"]
        for name, bucket in result["experiences"].items()
    }
    return result
