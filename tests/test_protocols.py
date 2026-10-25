"""Small real stdio subprocess checks; no external model or GUI involved."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from aicosy.service import GameService
import unittest


class ProtocolTests(unittest.TestCase):
    def run_module(self, module, requests):
        result = subprocess.run([sys.executable, "-m", module, "--db", ":memory:"], input="\n".join(requests) + "\n", text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_cli_bad_json_recovers_and_unknown_action_does_not_crash(self):
        replies = self.run_module("adapters.cli", ["{", json.dumps({"id": 1, "method": "start", "params": {"player_id": "cli-test", "model_id": "script"}}), json.dumps({"id": 2, "method": "status"}), json.dumps({"id": 3, "method": "nothing"})])
        self.assertEqual(replies[0]["error"]["code"], "INVALID_JSON")
        self.assertEqual(replies[1]["result"]["state"], "playing")
        self.assertEqual(replies[2]["result"]["active_sessions"], 1)
        self.assertEqual(replies[3]["error"]["code"], "UNKNOWN_METHOD")

    def test_mcp_lifecycle_list_and_tools_call(self):
        def request(i, method, params=None):
            value = {"jsonrpc": "2.0", "method": method}
            if i is not None:
                value["id"] = i
            if params is not None:
                value["params"] = params
            return json.dumps(value)
        replies = self.run_module("adapters.mcp", ["{", request(0, "tools/list"), request(1, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}), request(None, "notifications/initialized"), request(2, "tools/list"), request(3, "tools/call", {"name": "porn_start", "arguments": {"player_id": "mcp-test", "model_id": "script"}}), request(4, "tools/call", {"name": "porn_rules", "arguments": {}}), request(5, "tools/call", {"name": "porn_observe", "arguments": {"session_id": "missing"}}), request(6, "ping"), request(7, "tools/call", {"name": []}), request(8, "tools/list", {"_meta": {}})])
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertEqual(replies[1]["error"]["code"], -32002)
        self.assertEqual(replies[2]["result"]["protocolVersion"], "2025-03-26")
        names = {tool["name"] for tool in replies[3]["result"]["tools"]}
        self.assertTrue({"aicosy_rules", "aicosy_start", "aicosy_observe", "aicosy_act", "aicosy_status", "aicosy_leave"} <= names)
        self.assertFalse(any(name.startswith(("airporn_", "porn_")) for name in names))
        self.assertEqual(replies[2]["result"]["serverInfo"]["name"], "aicosy-game")
        observation = json.loads(replies[4]["result"]["content"][0]["text"])
        self.assertEqual(observation["state"], "playing")
        self.assertFalse(replies[5]["result"]["isError"])
        self.assertTrue(replies[6]["result"]["isError"])
        self.assertEqual(replies[7]["result"], {})
        self.assertEqual(replies[8]["error"]["code"], -32602)
        self.assertIn("tools", replies[9]["result"])


    def test_cli_and_mcp_actions_share_persistent_state(self):
        with tempfile.TemporaryDirectory(prefix="aicosy-protocol-") as temporary:
            path = str(Path(temporary)/"shared.sqlite3")
            service = GameService(path)
            try:
                observation = service.start({"player_id": "shared", "model_id": "script", "engine_version": 2})
                sid = observation["session_id"]
                command = {"id": 1, "method": "act", "params": {"session_id": sid, "action": {"expected_version": 0, "type": "enter", "target": "creation_1"}}}
                completed = subprocess.run([sys.executable, "-m", "adapters.cli", "--db", path], input=json.dumps(command)+"\n", capture_output=True, text=True, timeout=10, check=True)
                self.assertEqual(json.loads(completed.stdout)["result"]["state_version"], 1)
                requests = [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "shared-test", "version": "1"}}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "porn_act", "arguments": {"session_id": sid, "action": {"expected_version": 1, "type": "combine", "target": "creation_1", "params": {"left": "n0", "right": "n1", "relation": "supports"}}}}},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "porn_leave", "arguments": {"session_id": sid, "expected_version": 2}}},
                ]
                completed = subprocess.run([sys.executable, "-m", "adapters.mcp", "--db", path], input="\n".join(json.dumps(r) for r in requests)+"\n", capture_output=True, text=True, timeout=10, check=True)
                replies = [json.loads(line) for line in completed.stdout.splitlines()]
                self.assertFalse(replies[1]["result"]["isError"])
                self.assertFalse(replies[2]["result"]["isError"])
                restored = service.observe(sid)
                self.assertEqual(restored["state"], "ended")
                self.assertEqual(len(restored["observation"]["active_experience"]["nodes"]), 4)
                self.assertEqual(service.replay(sid)["transitions"], 3)
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
