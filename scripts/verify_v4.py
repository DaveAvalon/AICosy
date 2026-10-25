"""One small V4 HTTP flow with temporary state and a compact public example.

The player is an explicitly scripted interface check. No model preference or
subjective experience is measured. All test processes and SQLite files close.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters.http import make_server
from clients.common import GameClient
from aicosy.service import GameService


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/v4/scripted")
    parser.add_argument("--example", type=Path, help="Write a compact, explicitly scripted public example")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output must be empty; preserve existing evidence")
    if args.example and args.example.exists():
        parser.error("Example already exists; preserve the reviewed example")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aicosy-v4-http-") as temporary:
        db = str(Path(temporary) / "state.sqlite3")
        service = GameService(db)
        server = worker = None
        try:
            server = make_server(service, port=0, rate_limit=250)
            worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
            worker.start()
            client = GameClient(f"http://127.0.0.1:{server.server_port}")
            environment = {key: value for key, value in os.environ.items()
                           if not key.startswith(("AICOSY_", "AIRPORN_", "PORN_"))
                           and key not in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")}
            run = subprocess.run([
                sys.executable, "-m", "clients.rule_agent", "--server", client.server,
                "--player-id", "public-scripted-example", "--model-id", "rule-script-v4",
                "--engine-version", "4", "--no-memory", "--record", str(output / "session.jsonl"),
            ], cwd=ROOT, env=environment, text=True, capture_output=True, timeout=20, check=True)
            result = json.loads(run.stdout)
            sid = result["session_id"]
            view = client.get(f"/v1/observer/sessions/{sid}")
            assert result["turns"] == 12
            assert result["summary"]["known_cycle_holds"] == 1
            assert result["summary"]["pulse_interventions"] == 2
            assert result["summary"]["paid_replays"] == 1
            assert view["summary"]["client_info"]["kind"] == "rule-script"
            replay = client.get(f"/v1/sessions/{sid}/replay")
            assert replay["verified"]
            for name, value in (("result", result), ("observer", view), ("replay", replay)):
                write_json(output / f"{name}.json", value)
            observed = service.observe(sid)
            example = {"format": 1, "engine_version": 4, "rules_version": 4,
                       "provenance": "Prescribed rule script over real localhost HTTP. Interface and deterministic replay evidence only; not a model preference or pleasure trial.",
                       "actions": [{"seq": event["seq"], "action": {k: v for k, v in event["action"].items() if k != "expected_version"},
                                    "kind": event["outcome"]["kind"], "cost": event["outcome"].get("cost", 0),
                                    "piece_id": event["outcome"].get("piece_id"),
                                    "tick": event["outcome"].get("experience", {}).get("tick"),
                                    "cycle": event["outcome"].get("experience", {}).get("cycle")}
                                   for event in view["events"] if event["action"]],
                       "result": {"turns": result["turns"], "energy_remaining": result["resources"]["energy"],
                                  "extensions": result["summary"]["extensions"], "known_cycle_holds": result["summary"]["known_cycle_holds"],
                                  "pulse_interventions": result["summary"]["pulse_interventions"], "exact_replays": result["summary"]["paid_replays"]},
                       "last_visible_output": observed["observation"]["performance"]["summary"]["output_sequence"],
                       "deterministic_replay_verified": replay["verified"]}
        finally:
            if server is not None:
                if worker is not None:
                    server.shutdown()
                server.server_close()
            if worker is not None:
                worker.join(timeout=2)
            service.close()
        restored = GameService(db)
        try:
            assert restored.observe(sid) == observed
            assert restored.replay(sid)["verified"]
        finally:
            restored.close()
    if args.example:
        args.example.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.example, example)
    summary = {"verified": True, "kind": "scripted-interface-check", "turns": result["turns"],
               "temporary_server_closed": True, "temporary_database_removed": True, "output": str(output)}
    write_json(output / "validation.json", summary)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
