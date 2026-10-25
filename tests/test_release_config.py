"""Small checks for documented configuration and authentication compatibility."""
import contextlib
import errno
import io
import os
import unittest
from unittest.mock import patch

from adapters import http
from clients import compatible
from clients.common import env_value, parser


class ReleaseConfigTests(unittest.TestCase):
    def test_new_settings_override_legacy_including_explicit_empty_values(self):
        with patch.dict(os.environ, {
            "AICOSY_SERVER": "http://127.0.0.1:9001", "AIRPORN_SERVER": "http://127.0.0.1:9002", "PORN_SERVER": "http://127.0.0.1:9003",
            "AICOSY_ACCESS_TOKEN": "", "AIRPORN_ACCESS_TOKEN": "intermediate-test-token", "PORN_ACCESS_TOKEN": "legacy-test-token",
        }, clear=True):
            args = parser("test").parse_args([])
            self.assertEqual(args.server, "http://127.0.0.1:9001")
            self.assertEqual(args.token_env, "AICOSY_ACCESS_TOKEN")
            self.assertEqual(env_value(args.token_env), "")

    def test_legacy_settings_and_explicit_custom_environment_names(self):
        with patch.dict(os.environ, {
            "PORN_SERVER": "http://127.0.0.1:9002", "PORN_ACCESS_TOKEN": "legacy-test-token",
            "CUSTOM_ACCESS": "custom-test-token",
            "PORN_CUSTOM_ACCESS": "unrelated-test-token",
        }, clear=True):
            args = parser("test").parse_args([])
            self.assertEqual(args.server, "http://127.0.0.1:9002")
            self.assertEqual(env_value(args.token_env), "legacy-test-token")
            self.assertEqual(env_value("CUSTOM_ACCESS"), "custom-test-token")
            self.assertIsNone(env_value("MISSING_CUSTOM_ACCESS"))
            self.assertIsNone(env_value("AICOSY_CUSTOM_ACCESS"))

    def test_model_client_reads_new_and_legacy_settings_without_network_calls(self):
        for prefix in ("AICOSY_", "AIRPORN_", "PORN_"):
            with self.subTest(prefix=prefix), patch.dict(os.environ, {
                prefix + "MODEL_BASE_URL": "http://127.0.0.1:9003/v1",
                prefix + "MODEL": "configuration-test-model",
                prefix + "MODEL_API_KEY": "configuration-test-key",
            }, clear=True), patch("sys.argv", ["compatible"]), \
                    patch.object(compatible, "run_agent") as run_agent, \
                    patch.object(compatible, "print_result"):
                compatible.main()
                chooser = run_agent.call_args.args[1]
                self.assertEqual(chooser.base_url, "http://127.0.0.1:9003/v1")
                self.assertEqual(chooser.model, "configuration-test-model")
                self.assertEqual(chooser.api_key, "configuration-test-key")

    def test_explicit_empty_model_key_does_not_use_another_provider_key(self):
        with patch.dict(os.environ, {
            "AICOSY_MODEL": "configuration-test-model",
            "AICOSY_MODEL_API_KEY": "",
            "PORN_MODEL_API_KEY": "legacy-test-key",
            "OPENAI_API_KEY": "other-provider-test-key",
        }, clear=True), patch("sys.argv", ["compatible"]), \
                patch.object(compatible, "run_agent") as run_agent, \
                patch.object(compatible, "print_result"):
            compatible.main()
            self.assertEqual(run_agent.call_args.args[1].api_key, "")

    def test_http_auth_setting_precedence_and_custom_name(self):
        cases = (
            ({"PORN_ACCESS_TOKEN": "legacy-test-token"}, [], "legacy-test-token"),
            ({"PORN_ACCESS_TOKEN": "legacy-test-token", "AIRPORN_ACCESS_TOKEN": "new-test-token"}, [], "new-test-token"),
            ({"PORN_ACCESS_TOKEN": "legacy-test-token", "AIRPORN_ACCESS_TOKEN": ""}, [], ""),
            ({"PORN_ACCESS_TOKEN": "legacy-test-token", "AIRPORN_ACCESS_TOKEN": "intermediate-test-token", "AICOSY_ACCESS_TOKEN": "new-test-token"}, [], "new-test-token"),
            ({"PORN_ACCESS_TOKEN": "legacy-test-token", "AIRPORN_ACCESS_TOKEN": "intermediate-test-token", "AICOSY_ACCESS_TOKEN": ""}, [], ""),
            ({"PORN_ACCESS_TOKEN": "legacy-test-token"}, ["--token-env", "MISSING_CUSTOM_ACCESS"], None),
        )
        for environment, arguments, expected in cases:
            with self.subTest(arguments=arguments, expected=expected), \
                    patch.dict(os.environ, environment, clear=True), \
                    patch("porn.service.GameService") as service, \
                    patch.object(http, "make_server") as make_server, \
                    contextlib.redirect_stderr(io.StringIO()):
                http.main(["--db", ":memory:", *arguments])
                self.assertEqual(make_server.call_args.args[3], expected)
                make_server.return_value.server_close.assert_called_once()
                service.return_value.close.assert_called_once()

    def test_busy_port_reports_the_alternate_port_and_closes_database(self):
        error = io.StringIO()
        with patch("porn.service.GameService") as service, \
                patch.object(http, "make_server", side_effect=OSError(errno.EADDRINUSE, "Address in use")), \
                contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as stopped:
            http.main(["--db", ":memory:"])
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn("--port 8766", error.getvalue())
        service.return_value.close.assert_called_once()
