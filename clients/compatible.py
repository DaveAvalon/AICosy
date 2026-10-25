"""Optional OpenAI-compatible Chat Completions player; credentials stay in env."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from clients.common import ClientError, env_value, parser, print_result, read_json, request_json, run_agent, validate_url


class CompatiblePlayer:
    def __init__(self, *, base_url, model, api_key=None, timeout=90):
        self.base_url = validate_url(base_url)
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.last_error = None

    def reject(self, error):
        self.last_error = error

    def __call__(self, observation, rules):
        prompt = {"rules": rules, "observation": observation}
        if self.last_error:
            prompt["previous_action_error"] = self.last_error
        messages = [
            {"role": "system", "content": "You are the player of a structured game. Choose freely among the legal available_actions. You may explore, create, repeat an experience at its stated cost, change direction, or leave. Return only one JSON action object with type, optional target, and optional params, matching the chosen descriptor's parameter schema. Do not include expected_version. Game scores and choices do not establish subjective emotion."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False, allow_nan=False)},
        ]
        payload = {"model": self.model, "messages": messages, "response_format": {"type": "json_object"}}
        for attempt in range(3):
            result = request_json(self.base_url + "/chat/completions", payload, token=self.api_key, timeout=self.timeout)
            try:
                content = result["choices"][0]["message"]["content"]
                action = read_json(content)
                if not isinstance(action, dict) or "type" not in action or set(action) - {"type", "target", "params"}:
                    raise ValueError("Invalid action shape")
                self.last_error = None
                return action
            except (KeyError, IndexError, TypeError, ValueError, RecursionError):
                if attempt == 2:
                    raise ClientError("Model returned no valid JSON action after 3 attempts") from None
                payload["messages"].append({"role": "user", "content": "The response was not a valid action JSON object. Return one JSON object matching an available action."})
        raise ClientError("No action returned")


def main():
    command = parser(__doc__, player=None, model=None)
    command.add_argument("--base-url", default=env_value("AICOSY_MODEL_BASE_URL", os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")))
    command.add_argument("--model", default=env_value("AICOSY_MODEL", os.environ.get("OPENAI_MODEL")))
    command.add_argument("--api-key-env", default="AICOSY_MODEL_API_KEY")
    command.add_argument("--timeout", type=float, default=90)
    args = command.parse_args()
    if not args.model:
        command.error("--model or AICOSY_MODEL must name the model to connect")
    identity = hashlib.sha256((args.base_url.rstrip("/") + "\n" + args.model).encode()).hexdigest()[:24]
    if args.model_id is None:
        args.model_id = "compatible:" + identity
    if args.player_id is None:
        args.player_id = "compatible-player:" + identity
    if args.timeout <= 0 or args.timeout > 300:
        command.error("--timeout must be >0 and <=300 seconds")
    api_key = env_value(args.api_key_env)
    if api_key is None and args.api_key_env in ("AICOSY_MODEL_API_KEY", "AIRPORN_MODEL_API_KEY", "PORN_MODEL_API_KEY"):
        api_key = os.environ.get("OPENAI_API_KEY")
    try:
        chooser = CompatiblePlayer(base_url=args.base_url, model=args.model, api_key=api_key, timeout=args.timeout)
        print_result(run_agent(args, chooser, kind="chat-completions-model"))
    except ClientError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
