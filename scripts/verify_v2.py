"""One bounded V2 HTTP game and persistence/observer checks; no visible UI.

Uses a tiny temporary SQLite database, the existing source tree, one ephemeral
loopback server and one external scripted player. Cleanup is guaranteed. Saved
files are evidence only; scripted choices do not estimate model preference.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters.http import make_server
from porn import engine
from porn.service import GameService


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


@contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="porn-v2-verification")
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        if thread.is_alive():
            raise RuntimeError("Verification server did not stop")


def get(base, path):
    with urlopen(base+path, timeout=5) as response:
        body = response.read(16*1024*1024+1)
        if len(body)>16*1024*1024:
            raise RuntimeError("Verification response exceeded its bounded size")
        return json.loads(body)


def assert_legacy_replay():
    fixture = json.loads((ROOT/"tests/fixtures/v1-golden.json").read_text())
    state = fixture["initial_state"]
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    for step in fixture["steps"]:
        state, outcome = engine.transition(state, step["action"])
        assert digest(state) == step["state_hash"]
        assert digest(outcome) == step["outcome_hash"]
    return [{"session_id": state["session_id"], "transitions": state["state_version"]}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="evidence/v2")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output/"validation.json").exists():
        parser.error("output already has completed evidence; choose another directory")
    legacy = assert_legacy_replay()
    with tempfile.TemporaryDirectory(prefix="porn-v2-verification-") as temporary:
        database = str(Path(temporary)/"game.sqlite3")
        service = GameService(database)
        try:
            server = make_server(service, port=0, rate_limit=1000)
            with running(server) as base:
                assert get(base, "/v1/observer/sessions")["sessions"] == []
                environment = {key: value for key,value in os.environ.items() if not key.startswith(("AICOSY_", "AIRPORN_", "PORN_")) and key != "OPENAI_API_KEY"}
                completed = subprocess.run([
                    sys.executable, "-m", "clients.rule_agent", "--server", base,
                    "--player-id", "v2-coverage", "--model-id", "rule-script-v2",
                    "--seed", "42", "--engine-version", "2", "--no-memory", "--record", str(output/"full-session.jsonl"),
                ], cwd=ROOT, env=environment, capture_output=True, text=True, timeout=35, check=True)
                result = json.loads(completed.stdout)
                sid = result["session_id"]
                assert result["turns"] == 24
                exported = get(base, "/v1/players/v2-coverage/export")
                record = exported["sessions"][0]
                events = record["events"]
                outcomes = [event["outcome"] for event in events]
                assert {o.get("mode") for o in outcomes} >= {"pattern", "creation", "resonance"}
                assert {"replay", "fork", "revise"} <= {o["kind"] for o in outcomes}
                processes = {}
                performances = []
                for event in events:
                    kind = event["outcome"]["kind"]
                    process = event["outcome"].get("performance")
                    if kind in ("perform", "fork") and process:
                        processes[process["trace_hash"]] = process
                    if kind == "perform" and process:
                        performances.append(process)
                    if kind in ("replay", "fork"):
                        before_visible = engine.observe(event["before"])["observation"]
                        after_visible = engine.observe(event["after"])["observation"]
                        assert before_visible["machine"] == after_visible["machine"]
                        source = next(item for item in before_visible["saved_experiences"] if item["id"] == event["action"]["target"])
                        assert event["outcome"]["cost"] == 2
                        if kind == "replay":
                            assert process["trace_hash"] == source["trace_hash"]
                            assert process["frames"] == processes[source["trace_hash"]]["frames"]
                            assert process["inputs"] == source["inputs"]
                        else:
                            assert process["inputs"]["phase"] == source["inputs"]["phase"]
                            assert process["inputs"]["period"] != source["inputs"]["period"]
                same_input_runs = [p for p in performances if p["inputs"] == {"period": 4, "phase": 0}]
                assert len(same_input_runs) >= 2
                assert same_input_runs[0]["frames"] != same_input_runs[1]["frames"], "A real node edit must change the actual signal trace under the same inputs"
                detail = get(base, "/v1/observer/sessions/"+sid)
                listing = get(base, "/v1/observer/sessions")
                assert detail["summary"]["turn"] == 24
                assert detail["summary"]["state"] == "ended"
                assert detail["summary"]["client_info"]["kind"] == "rule-script"
                assert detail["read_only"] is True
                assert len(detail["events"]) == 25
                assert listing["sessions"][0]["session_id"] == sid
                before_restart = get(base, "/v1/sessions/"+sid+"/observation")
                replay = get(base, "/v1/sessions/"+sid+"/replay")
                assert replay["verified"] and replay["transitions"] == 24
                write_json(output/"result.json", result)
                write_json(output/"raw-export.json", exported)
                write_json(output/"observer.json", detail)
                write_json(output/"replay.json", replay)
            service.close()
            service = GameService(database)
            assert service.observe(sid) == before_restart
            assert service.replay(sid)["verified"]
            write_json(output/"validation.json", {
                "engine_version": 2, "turns": 24,
                "player": "external deterministic rule script; not spontaneous model preference",
                "real_http": True, "visited_modes": ["pattern", "creation", "resonance"],
                "paid_replay": "saved process frames/hash/inputs reproduced with current machine unchanged",
                "causal_edit": "same period and phase produce different actual frames after a node edit",
                "fork_and_revision": "distinct accepted outcomes",
                "observer": "real current state, events and declared script identity returned by HTTP",
                "persistence": "same observation after reopening SQLite; 24 transitions verified",
                "legacy_replay": legacy,
                "visual_browser_check": "not run; no windows created",
                "cleanup": "loopback server stopped, child exited, temporary database directory removed",
            })
        finally:
            service.close()
    print(json.dumps({"output":str(output),"turns":24,"legacy_sessions_verified":len(legacy),"cleanup":"complete"}))


if __name__ == "__main__":
    main()
