"""Run a small matched AICosy experiment through external HTTP clients."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen
from urllib.parse import quote

from clients.common import env_value
from .experiments import experiment_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default=env_value("AICOSY_SERVER", "http://127.0.0.1:8765"))
    parser.add_argument("--player-id", required=True)
    parser.add_argument("--model-id")
    parser.add_argument("--engine-version", type=int, choices=(2, 3, 4), default=4)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--mode", choices=["normal", "research"], default="normal")
    parser.add_argument("--output", default="evidence/experiment")
    args = parser.parse_args()
    args.model_id = args.model_id or f"rule-script-v{args.engine_version}"
    plan = experiment_plan(args.player_id, args.model_id, args.repetitions, args.seed, args.mode, args.engine_version)
    directory = Path(args.output)
    directory.mkdir(parents=True, exist_ok=True)
    plan_path = directory / "plan.json"
    if plan_path.exists():
        parser.error("output already contains an experiment plan; choose a new output to preserve evidence")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2)+"\n")
    for index, session in enumerate(plan["sessions"]):
        command = [sys.executable, "-m", "clients.rule_agent", "--server", args.server,
                   "--player-id", args.player_id, "--model-id", args.model_id,
                   "--seed", str(session["seed"]), "--condition", session["condition"],
                   "--mode", args.mode, "--no-memory", "--record", str(directory / f"session-{index:03d}.jsonl")]
        command.extend(["--engine-version", str(session["engine_version"])])
        subprocess.run(command, check=True, timeout=90)
    token = env_value("AICOSY_ACCESS_TOKEN")
    headers = {"Authorization": "Bearer " + token} if token else {}
    req = Request(args.server.rstrip("/")+"/v1/players/"+quote(args.player_id, safe="")+"/comparison", headers=headers)
    with urlopen(req, timeout=10) as response:
        result = json.load(response)
    (directory / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"completed_sessions": len(plan["sessions"]), "output": str(directory)}))


if __name__ == "__main__":
    main()
