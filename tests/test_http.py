"""Small headless checks of the HTTP transport and real service boundary."""
import http.client
import json
import threading
import unittest

from adapters.http import make_server
from adapters.schemas import SCHEMAS, json_schema, openapi
from porn.service import GameService


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.service = GameService(":memory:")
        self.server = make_server(self.service, port=0, rate_limit=200)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.service.close()

    def request(self, method, path, value=None, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            body = raw if raw is not None else (json.dumps(value) if value is not None else None)
            merged = {"Content-Type": "application/json"}
            merged.update(headers or {})
            connection.request(method, path, body=body, headers=merged)
            response = connection.getresponse()
            data = response.read()
            return response.status, (json.loads(data) if "json" in response.getheader("Content-Type", "") else data)
        finally:
            connection.close()

    def test_discovery_action_and_status_are_real(self):
        code, manifest = self.request("GET", "/v1/manifest")
        self.assertEqual(code, 200)
        self.assertEqual(manifest["rules"], "/v1/rules")
        self.assertEqual(self.request("GET", "/v1/status")[1]["state"], "waiting")
        code, observation = self.request("POST", "/v1/sessions", {"player_id": "http-test", "model_id": "script-v1"})
        self.assertEqual(code, 200, observation)
        self.assertEqual(self.request("GET", "/v1/status")[1]["active_sessions"], 1)
        sid = observation["session_id"]
        code, ended = self.request("POST", f"/v1/sessions/{sid}/leave", {"expected_version": 0})
        self.assertEqual(code, 200, ended)
        self.assertEqual(ended["state"], "ended")
        self.assertEqual(self.request("GET", "/v1/status")[1]["state"], "ended")
        events = self.request("GET", f"/v1/sessions/{sid}/events?after=0&limit=1")[1]
        self.assertEqual(events["events"][0]["seq"], 1)
        self.assertNotIn("before", events["events"][0])

    def test_v3_flow_and_selected_rules_cross_http_boundary(self):
        self.assertEqual(self.request("GET", "/v1/rules?engine_version=3")[1]["rules_version"], 3)
        self.assertEqual(self.request("GET", "/v1/rules?engine_version=2")[1]["rules_version"], 2)
        self.assertEqual(self.request("GET", "/v1/rules?engine_version=5")[0], 400)
        _, obs = self.request("POST", "/v1/sessions", {"player_id": "http-v3", "model_id": "script", "engine_version": 3})
        self.assertEqual(obs["engine_version"], 3)
        sid = obs["session_id"]
        for kind in ("enter", "begin", "wait", "release", "continue", "continue", "continue"):
            code, obs = self.request("POST", f"/v1/sessions/{sid}/action", {
                "expected_version": obs["state_version"], "type": kind, "target": "resonance_1"})
            self.assertEqual(code, 200, obs)
        saved = obs["observation"]["saved_experiences"][-1]
        code, repeated = self.request("POST", f"/v1/sessions/{sid}/action", {
            "expected_version": obs["state_version"], "type": "replay", "target": saved["id"]})
        self.assertEqual(code, 200, repeated)
        self.assertEqual(repeated["observation"]["performance"]["trace_hash"], saved["trace_hash"])
        detail = self.request("GET", f"/v1/observer/sessions/{sid}")[1]
        self.assertEqual(detail["summary"]["counts"]["replays"], 1)
        self.assertEqual(self.request("GET", "/v1/players/http-v3/profile?engine_version=3")[1]["engine_version"], 3)
        self.assertEqual(self.request("GET", "/v1/players/http-v3/profile?engine_version=2")[1]["sessions"], 0)

    def test_v4_continuation_hold_and_replay_are_distinct(self):
        self.assertEqual(self.request("GET", "/v1/rules")[1]["rules_version"], 4)
        code, obs = self.request("POST", "/v1/sessions", {"player_id": "http-v4", "model_id": "script"})
        self.assertEqual(code, 200)
        self.assertEqual(obs["engine_version"], 4)
        sid = obs["session_id"]
        code, obs = self.request("POST", f"/v1/sessions/{sid}/action", {
            "expected_version": 0, "type": "perform", "target": "resonance_1", "params": {"release_tick": 8}})
        self.assertEqual(code, 200, obs)
        first = obs["observation"]["saved_experiences"][0]["id"]
        run_id = obs["observation"]["current_run"]["run_id"]
        for kind, target in (("extend", run_id), ("replay", first), ("hold", run_id)):
            code, obs = self.request("POST", f"/v1/sessions/{sid}/action", {
                "expected_version": obs["state_version"], "type": kind, "target": target})
            self.assertEqual(code, 200, obs)
        self.assertEqual(obs["observation"]["current_run"]["tick"], 72)
        self.assertEqual(obs["observation"]["performance"]["frames"][0]["tick"], 48)
        view = self.request("GET", f"/v1/observer/sessions/{sid}")[1]
        self.assertEqual(view["summary"]["counts"]["holds"], 1)
        self.assertEqual(view["summary"]["counts"]["replays"], 1)

    def test_auth_applies_to_status_and_api(self):
        self.server.token = "test-access-token"
        code, value = self.request("GET", "/v1/status")
        self.assertEqual((code, value["error"]["code"]), (401, "UNAUTHORIZED"))
        self.assertEqual(self.request("GET", "/v1/status", headers={"Authorization": "Bearer test-access-token"})[0], 200)
        self.assertEqual(self.request("GET", "/")[0], 200)

    def test_remote_binding_requires_token(self):
        with self.assertRaises(ValueError):
            make_server(self.service, host="0.0.0.0", port=0)

    def test_bad_input_does_not_crash_or_create_session(self):
        for raw in ('{"player_id":"x","model_id":NaN}', '{"player_id":"x","player_id":"y","model_id":"z"}', '[]', '{'):
            code, value = self.request("POST", "/v1/sessions", raw=raw)
            self.assertEqual(code, 400, value)
        self.assertEqual(self.request("GET", "/v1/status")[1]["active_sessions"], 0)
        self.assertEqual(self.request("POST", "/v1/sessions", raw="x" * 65537)[0], 413)
        self.assertEqual(self.request("POST", "/v1/sessions", raw="{}", headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("GET", "/v1/status?unknown=1")[0], 400)
        self.assertEqual(self.request("GET", "/missing")[0], 404)

    def test_origin_and_rebinding_are_rejected(self):
        self.assertEqual(self.request("POST", "/v1/sessions", {}, headers={"Origin": "https://foreign.example"})[0], 403)
        self.assertEqual(self.request("GET", "/v1/status", headers={"Origin": "http://[invalid"})[0], 403)
        self.assertEqual(self.request("GET", "/v1/status", headers={"Host": "foreign.example"})[0], 403)

    def test_rate_limit_and_public_contracts(self):
        self.server.rate_limit = 1
        self.assertEqual(self.request("GET", "/openapi.json")[0], 200)
        self.assertEqual(self.request("GET", "/v1/status")[0], 429)
        document = openapi()
        self.assertEqual(document["openapi"], "3.1.0")
        self.assertIn("/v1/sessions/{id}/action", document["paths"])
        for name in SCHEMAS:
            self.assertIsInstance(json_schema(name), dict)
            json.dumps(json_schema(name), allow_nan=False)
        self.assertIsNone(json_schema("missing"))

    def test_human_observer_routes_are_read_only_and_authenticated(self):
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertEqual(self.request("GET", "/observer")[0], 200)
        self.assertEqual(self.request("GET", "/assets/observer.js")[0], 200)
        _, obs = self.request("POST", "/v1/sessions", {"player_id": "observer", "model_id": "script", "client_kind": "rule-script"})
        sid = obs["session_id"]
        code, listing = self.request("GET", "/v1/observer/sessions?limit=10")
        self.assertEqual(code, 200)
        self.assertEqual(listing["sessions"][0]["session_id"], sid)
        code, detail = self.request("GET", f"/v1/observer/sessions/{sid}")
        self.assertEqual(code, 200)
        self.assertEqual(detail["summary"]["turn"], 0)
        self.assertTrue(detail["read_only"])
        self.assertEqual(self.service.observe(sid), obs)
        self.assertEqual(self.request("GET", "/v1/observer/sessions?limit=1000")[0], 400)
        self.server.token = "observer-test"
        self.assertEqual(self.request("GET", "/v1/observer/sessions")[0], 401)
        self.assertEqual(self.request("GET", f"/v1/observer/sessions/{sid}")[0], 401)

    def test_page_has_only_indicator_and_safe_polling(self):
        code, page = self.request("GET", "/status")
        self.assertEqual(code, 200)
        text = page.decode()
        self.assertIn("/v1/status", text)
        self.assertIn("controller.abort", text)
        self.assertIn("show('waiting', true)", text)
        self.assertNotIn("<button", text)
        self.assertNotIn("<input", text)
        self.assertNotIn("<canvas", text)


if __name__ == "__main__":
    unittest.main()
