"""Archived V1 protocol demonstration; use verify_v4.py for the current game.

Keeps only JSON evidence. All temporary databases, HTTP servers and child player
processes have bounded lifetimes and cleanup in finally/context managers.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
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
from clients.rule_agent import RulePlayer
from aicosy.service import GameService


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


@contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="aicosy-verification-http")
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        if thread.is_alive():
            raise RuntimeError("Verification server thread did not stop")


class MockModel(BaseHTTPRequestHandler):
    """An explicit scripted protocol stub, never presented as an actual LLM."""
    player = None
    requests_seen = 0

    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        data = json.loads(payload["messages"][1]["content"])
        action = self.player(data["observation"], data["rules"])
        type(self).requests_seen += 1
        body = json.dumps({"choices": [{"message": {"role": "assistant", "content": json.dumps(action)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_player(module, base, output, *args):
    command = [sys.executable, "-m", module, "--server", base, *args]
    # Preserve normal service auth configuration but remove real provider credentials.
    env = {k: v for k,v in os.environ.items() if not k.startswith(("AICOSY_", "AIRPORN_", "PORN_")) and k not in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")}
    completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=35, check=True)
    result = json.loads(completed.stdout)
    write_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="evidence")
    args = parser.parse_args()
    from aicosy.engine import DEFAULT_VERSION
    if DEFAULT_VERSION != 1:
        parser.error("This V1 demo is archived. Use scripts/verify_v4.py; historical replay is covered by tests/fixtures.")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aicosy-verification-") as temporary:
        database = str(Path(temporary)/"demo.sqlite3")
        service = GameService(database)
        try:
            server = make_server(service, port=0, rate_limit=1000)
            with running(server) as base:
                with urlopen(base+"/", timeout=3) as response:
                    html = response.read().decode()
                    assert "等待 AI 接入" in html
                assert service.status()["state"] == "waiting"
                result = run_player("clients.rule_agent", base, output/"rule-result.json", "--player-id", "demo-rule", "--model-id", "rule-v1", "--seed", "42", "--record", str(output/"full-session.jsonl"))
                sid = result["session_id"]
                assert result["turns"] == 24, result
                exported = service.export_player("demo-rule")
                outcomes = [e["outcome"] for e in exported["sessions"][0]["events"]]
                assert {o.get("mode") for o in outcomes} >= {"pattern", "creation", "resonance"}
                assert any(o["kind"] == "replay" and o["cost"] == 2 for o in outcomes)
                assert service.status()["state"] == "ended"
                write_json(output/"session-export.json", exported)
                write_json(output/"replay.json", service.replay(sid))

                MockModel.player = RulePlayer(7)
                MockModel.requests_seen = 0
                mock = ThreadingHTTPServer(("127.0.0.1", 0), MockModel)
                with running(mock) as model_base:
                    mock_result = run_player("clients.compatible", base, output/"compatible-mock-result.json", "--player-id", "demo-compatible-mock", "--model-id", "mock-rule-v1", "--seed", "7", "--base-url", model_base+"/v1", "--model", "mock-script-not-an-llm", "--record", str(output/"compatible-mock-session.jsonl"))
                assert mock_result["turns"] == 24
                assert MockModel.requests_seen == 24
                random_result = run_player("clients.random_agent", base, output/"random-result.json", "--player-id", "demo-random", "--model-id", "random-v1", "--seed", "7", "--record", str(output/"random-session.jsonl"))
                assert 1 <= random_result["turns"] <= 24
                write_json(output/"comparison.json", service.compare("demo-rule"))
                for row in service.store.db.execute("SELECT id FROM sessions").fetchall():
                    assert service.replay(row["id"])["verified"]
                before_restart = service.observe(sid)
            service.close()
            service = GameService(database)
            assert service.observe(sid) == before_restart
            replay = service.replay(sid)
            write_json(output/"validation.json", {
                "real_network": "localhost HTTP, external subprocess players",
                "rule_session": {"turns": result["turns"], "session_id": sid, "visited_modes": ["pattern", "creation", "resonance"], "paid_replay": True},
                "compatible_client": {"transport": "Chat Completions-compatible HTTP", "backend": "explicit local scripted mock; no real LLM", "turns": mock_result["turns"], "model_requests": MockModel.requests_seen},
                "random_client": {"turns": random_result["turns"], "ended": True},
                "persistence_restart": "exact observation restored from reopened SQLite database",
                "deterministic_replay_after_restart": replay,
                "status": "waiting before start; ended after completed script session; timeout/heartbeat/multiple sessions tested separately",
                "browser_visual_interaction": "not run; no visible windows opened",
                "commercial_model_connection": "not tested; no configured real provider used",
                "cleanup": "all verification HTTP servers stopped, subprocesses exited, temporary SQLite removed",
            })
        finally:
            service.close()
    print(json.dumps({"output": str(output), "rule_turns": 24, "mock_turns": 24, "cleanup": "complete"}))


if __name__ == "__main__":
    main()
