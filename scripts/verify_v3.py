"""One small real HTTP scripted V3 path, with guaranteed server/DB cleanup."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters.http import make_server
from clients.common import GameClient
from porn.service import GameService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/v3/scripted")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output must be empty; preserve existing evidence")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="porn-v3-http-") as temporary:
        db = str(Path(temporary) / "test.sqlite3")
        service = GameService(db)
        server = None
        worker = None
        try:
            server = make_server(service, port=0, rate_limit=250)
            worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
            worker.start()
            base = f"http://127.0.0.1:{server.server_port}"
            client = GameClient(base)
            run = subprocess.run([
                sys.executable, "-m", "clients.rule_agent", "--server", base,
                "--player-id", "v3-scripted-check", "--model-id", "rule-script-v3",
                "--engine-version", "3", "--no-memory", "--record", str(output / "session.jsonl"),
            ], cwd=ROOT, text=True, capture_output=True, timeout=20, check=True)
            result = json.loads(run.stdout)
            sid = result["session_id"]
            observer = client.get(f"/v1/observer/sessions/{sid}")
            assert observer["summary"]["engine_version"] == 3
            assert observer["summary"]["client_info"]["kind"] == "rule-script"
            assert observer["summary"]["counts"]["reperformances"] == 1
            assert observer["summary"]["counts"]["replays"] == 4
            assert result["summary"]["forks"] == 1
            replay = client.get(f"/v1/sessions/{sid}/replay")
            assert replay["verified"]
            assert client.get("/v1/rules?engine_version=2")["rules_version"] == 2
            for name, value in (("result", result), ("observer", observer), ("replay", replay)):
                (output / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            persisted = service.observe(sid)
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
            assert restored.observe(sid) == persisted
            assert restored.replay(sid)["verified"]
        finally:
            restored.close()
    print(json.dumps({"verified": True, "session_id": sid, "turns": result["turns"],
                      "kind": "scripted-interface-check", "temporary_server_closed": True,
                      "temporary_database_removed": True, "output": str(output)}))


if __name__ == "__main__":
    main()
