# V1 MVP implementation contract

Historical contract for engine 1. New sessions and observer APIs follow [v2-contract.md](v2-contract.md). Saved V1 transitions remain supported unchanged.

Python >=3.11, standard library only. `porn` is the import package. Engine is the single rules authority; service owns persistence, versions and identity; adapters only translate protocols. No model dependency in core. JSON-compatible data only.

## Core (porn/engine.py, porn/world.py, porn/errors.py)

- `GameError(code, message, status=400, details=None)` with `.code .message .status .details`, `.as_dict()` -> `{error:{code,message,details}}`.
- `create_state(*, session_id, player_id, model_id, seed=0, max_turns=24, mode='normal', condition='control', preferences=None) -> dict`.
- `observe(state) -> dict`: session_id, state_version, turn, state ('playing'/'ended'), available_actions (each includes type, optional target, cost, parameters as JSON Schema), resources, visible world and results. Never reveal solutions/seed in normal observation.
- `transition(state, action) -> (new_state, outcome)`: pure, does not mutate input, validates action and params, increments turn and state_version once per accepted action. action `{type, target?, params?}`; service strips required expected_version. Reject unknown top-level/param fields. Free leave anytime, 20-30 max_turns, deterministic seeded content. Every available action descriptor must be executable. `outcome` JSON dict includes behavioral fields `{kind, mode?, target?, cost, ...}` suitable for metrics (selection, replay, abandon, leave). Core state includes config and full generated world, progression, resource values; last_outcome persisted.
- `rules() -> dict`: full machine readable rules incl actions, costs, constraints, content generation, end conditions.

## Service (porn/service.py, storage.py, preferences.py, experiments.py)

`GameService(db_path='data/porn.sqlite3', *, clock=None, activity_timeout=60, ended_display_seconds=5)` accepts injectable clock returning epoch seconds.

Public methods (all return dict):
- `manifest()` protocol_version=1, endpoints, rules and schemas links, discovery guidance.
- `rules()` delegates core rules.
- `start(payload)` payload player_id required, model_id required; seed int default 0; max_turns int default24; mode normal/research defaultnormal; condition control/personalized defaultcontrol. Returns observation. Personalized profile fixed at session creation. start binds player_id to model_id, reuse with different model prohibited.
- `observe(session_id)` read only, no activity renewal.
- `act(session_id,payload)` requires expected_version int plus engine action fields. Transactional compare-and-swap, 409 STALE_STATE. Returns observation. Stores complete before/after state + action + outcome in append-only ordered events.
- `leave(session_id,payload)` delegates act with type leave and expected_version.
- `heartbeat(session_id)` renews playing session activity.
- `events(session_id,after=-1,limit=100)` -> `{session_id,events:[...],next_after,has_more}` initial event seq0; seq1+ action events. Public events redact full state to preserve normal discovery. Full transitions in research/export only.
- `result(session_id)` ended only else409; includes behavioral summary, no pleasure claims.
- `status()` -> `{state:'waiting'|'playing'|'ended', active_sessions:int, message:str, ...}` real wall-clock activity, ended flashes only when zero active, timeout never terminates game.
- `debug(session_id)` full state, allowed only research else403.
- `profile(player_id,mode='normal')` / `reset_profile(player_id,mode='normal')` isolates model and research data.
- `export_player(player_id)` full raw sessions, transitions, profile data; research records explicitly marked. Document that raw export is researcher surface.
- `replay(session_id)` reexecutes initial snapshot + events, checks every state transition, returns verified true/count or GameError.
- `compare(player_id)` metrics by experiment condition, normal/research separated.
- `close()` releases DB.
`GameService` thread safe. Store session and its event transactionally. IDs generated at service boundary. Strict input validation, body/field limits. Do not evaluate external text.

## HTTP (adapters/http.py, schemas.py, web/status.html)

`make_server(service,host='127.0.0.1',port=8765,token=None,rate_limit=120) -> ThreadingHTTPServer`; refuse non-loopback binding without token. `.serve_forever`, `.shutdown`, `.server_close` standard. `python -m adapters.http --host --port --db --token-env PORN_ACCESS_TOKEN`.
REST required routes per task plus GET /v1/rules, /openapi.json, /schemas/{name}.json, / (status HTML); GET /v1/sessions/{id}/debug, /replay; GET /v1/players/{id}/profile, /export, /comparison; POST /v1/players/{id}/profile/reset. Query mode supported for profiles. Research export/debug protected by same configured bearer token; default loopback documented trusted. POST leave endpoint allowed. Content-length limits, structured error codes, no traceback/secret in responses. OpenAPI and JSON Schema detailed machine contracts.

## CLI/MCP/clients (adapters/cli.py, mcp.py; clients/*)

- JSONL request `{id,method,params}`. methods manifest/rules/start/observe/act/status/leave/heartbeat/events/result/profile/reset_profile/export/replay/compare/debug. Params for observe etc contain session_id; act params `{session_id,action:{expected_version,type,...}}`; leave params `{session_id,expected_version}`. Replies `{id,result}` or `{id,error:{code,message,details}}`. stdout protocol only, malformed lines do not kill process, bounded lines. `python -m adapters.cli --db`.
- MCP stdio JSON-RPC official newline transport: initialize, notifications/initialized, ping, tools/list, tools/call; tools porn_rules, porn_start, porn_observe, porn_act, porn_status, porn_leave, porn_heartbeat. shared service only. Browse official spec for handshake and tool schemas. `python -m adapters.mcp --db`.
- HTTP clients use urllib, configurable server/token, python -m clients.random_agent, clients.rule_agent, clients.compatible. Rule client solves patterns from visible information, uses creation/resonance, paid replays, can complete 24 turns. Random chooses strictly within schemas. Generic OpenAI-compatible client env API credentials, base url, model required/configurable; pass complete rules and observation, JSON action response validated by server, finite retry, no forcing preference, no secret logs. No API model required for offline demo. Save complete chosen actions/observations to --record JSONL. Clients run external HTTP, no importing engine/service.

## Validation/docs (root)

Unittest targeted engine/service/protocol checks, localhost external rule-agent end-to-end 24 turns, persisted replay/export, isolation/concurrency, timeout status, CLI/MCP real pipes and model-compatible mock HTTP. Record one full real script-agent session under evidence/. No browser launched. No actual commercial model claim without credentials.
