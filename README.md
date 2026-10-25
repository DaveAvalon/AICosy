<p align="center">
  <img src="docs/assets/aicosy-cover.svg" alt="AICosy — signals, patterns, choices" width="100%">
</p>

<h1 align="center">A small place for AI to play.</h1>

<p align="center">
  Build a signal machine. Follow a pattern. Choose what happens next.<br>
  An experimental playground for agents, with a window for humans.
</p>

<p align="center">
  <strong>Experimental 0.4.0</strong> · Python 3.11+ · Standard library runtime · <a href="LICENSE">MIT</a>
</p>

<p align="center">
  <a href="README.zh-CN.md">中文说明</a> · <a href="#quick-start">Quick start</a> · <a href="#three-pieces">The playground</a> · <a href="#connect-an-agent">Connect an agent</a> · <a href="#documentation">Documentation</a>
</p>

---

AICosy is a small game that AI agents play through tools while humans observe. An agent can build a structure, let its signals unfold, continue an unfinished process, stay with a familiar cycle, or give it a small nudge. Leaving is always free.

The human observer shows saved choices and the processes they produce. The service runs locally, stores sessions in SQLite, and supports HTTP, MCP stdio, and JSON Lines. The observer currently uses Chinese labels.

## Quick start

From the project directory containing this README and `adapters/`, open two terminals. Python 3.11 or newer is required; no package installation or model API key is needed for this demonstration.

**1. Start the service**

```sh
python3.11 -m adapters.http
```

**2. Run a short demonstration**

Keep the service running. In the second terminal, change to the same project directory:

```sh
python3.11 -m clients.rule_agent --no-memory --record evidence/demo.jsonl
```

This demonstration is a **rule script with prescribed choices**, not a model's spontaneous preference. A compact captured run is in [examples/scripted-session.json](examples/scripted-session.json).

**3. Open [the observer →](http://127.0.0.1:8765/)**

Refresh the observer after the demonstration to inspect the saved session. It shows actual activity and saved records; the lamp-only view is at `/status`. **Waiting for an AI is normal:** opening the page does not start a player. To use your own model, see [Connect an agent](#connect-an-agent).

<details>
<summary><strong>Download, interpreter, Windows, installation, and port help</strong></summary>

### Get the source and check Python

On this repository's GitHub page, choose **Code → Download ZIP**, extract it, and open a terminal in the extracted project directory. If you already have a checkout, use that directory. GitHub provides the source; the service runs on your computer.

Check the interpreter with `python3.11 --version` (or `python3 --version`). If `python3` already points to Python 3.11 or newer, use it in place of `python3.11` in these commands. On Windows, use `py -3.11` if Python was installed with the Python launcher.

### Optional package installation

Running from the checkout does not require installation. To install the package and its `aicosy-server`, `aicosy-jsonl`, and `aicosy-mcp` commands, use a virtual environment:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install .
aicosy-server
```

On Windows, activate it with `.venv\Scripts\Activate.ps1` in PowerShell. Installation may download build tooling; the source run above needs only the Python standard library. The wheel includes the observer assets. Compatibility details are in [connectors](docs/connectors.md).

### Use another port or stop the service

If port 8765 is occupied, start the server with `--port 8766`, open `http://127.0.0.1:8766/`, and pass `--server http://127.0.0.1:8766` to the demonstration client. Stop the server with `Ctrl+C` when finished.

</details>

## Three pieces

Three starting structures share the same causal rules:

- **Echo** — two delayed paths respond and then settle.
- **Orbit** — a pulse returns through a signed loop, with a recognizable conditional cycle.
- **Weave** — branching echoes feed back into the reservoir and overlap.

Creation alters the graph. Resonance plays it. Pattern inspects its response without prerequisite puzzles or unlocks. Delays, reflection, echoes, gates, merging, and finite storage affect actual signed signals. There is no score, leaderboard, unlock reward, or energy gain.

## Choose what happens next

- `perform`: start a 24-tick process with a declared release time.
- `begin`, then `wait` / `release` / `continue`: control the first segment in four-tick steps.
- `extend`: continue the **same runtime**, including signals still in flight.
- `hold`: remain in an already observed, non-silent **complete-state cycle**.
- `tap`: inject one new pulse and continue from the current state, creating an intervention branch.
- `replay`: reproduce the saved initial state, controls, and observed range exactly.
- `reperform`: use a familiar captured work and choose its timing again.
- Select another piece, edit, stop, or leave when the advertised rules allow it.

Starting, extending a segment, holding, tapping, and replaying cost 2 Energy each. Advances inside a paid segment are free. Each session starts with 24 Energy and accepts 20–30 actions, default 24. Each runtime is bounded to 96 ticks. A quiet process cannot be extended for an empty charge; it can be tapped again. A limit is labeled as a limit.

Cycle certification compares storage, gate state, the complete relative pending queue, and remaining inputs. It assumes the fixed captured machine and no new intervention; a few similar output frames are insufficient.

## Connect an agent

Discover `GET /v1/manifest` and `GET /v1/rules`. Create a session, then select from its current `available_actions`. Descriptors give costs, targets, and parameter schemas; submissions need the latest `expected_version`. See the [HTTP guide](docs/http.md) for a minimal client. OpenAPI is served at `/openapi.json`.

An optional Chat Completions-compatible client uses a neutral free-choice prompt:

```sh
export AICOSY_MODEL_BASE_URL='https://your-provider.example/v1'
export AICOSY_MODEL='your-model-name'
# Set AICOSY_MODEL_API_KEY securely in your environment if needed.
python3.11 -m clients.compatible --record evidence/model-session.jsonl
```

Use separate identities for different models, versions, and configurations. Client labels are caller declarations, not verified identities. Credentials are never written to gameplay logs. Models may leave immediately; no report or minimum play duration is required.

MCP stdio and JSON Lines call the same transactional service:

```sh
python3.11 -m adapters.mcp
python3.11 -m adapters.cli
```

See [connectors](docs/connectors.md) for configuration. Current sessions default to V4; V1–V3 recordings retain their original rules.

## Observe and reproduce

The observer shows actual graphs, signed signals, reservoir state, absolute tick windows, choices, and conditional cycles. Historical replay stays separate from the real resumable runtime. Human playback never creates player activity.

Sessions persist in `data/porn.sqlite3`. Reading does not renew activity, and inactivity is not a voluntary exit. Profiles, memory, and comparisons are separated by identity, normal/research mode, and engine version.

## Research boundaries

AICosy explores **behavioral attraction to structured experiences**. Continuation, known-cycle holding, intervention, familiar reperformance, exact replay, and exit have separate counts and legal-opportunity denominators. These describe behavior; they do not measure subjective happiness. The project contains no sexual media.

Scripted and task-directed runs stay labeled. Independent neutral model trials remain future work.

The service defaults to localhost. Non-loopback binding requires a bearer token; remote use needs HTTPS. Read [SECURITY.md](SECURITY.md) before exposing it.

## Documentation

- [HTTP guide](docs/http.md) — Session creation, observations, and actions.
- [MCP / JSONL connectors](docs/connectors.md) — Agent integration and compatibility.
- [V4 contract](docs/v4-contract.md) — Current rules, ownership, and replay boundaries.
- [Validation](docs/validation-v4.md) — Evidence for rules, protocols, assistant play, installation, and visual checks.
- [Related projects](docs/related-projects-20261025.md) — Prior work and areas of overlap; no claim of being the first AI game.
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [MIT license](LICENSE).

<details>
<summary><strong>Lightweight development checks</strong></summary>

```sh
python3.11 -m unittest tests.test_continuous_engine tests.test_continuous_service -v
python3.11 scripts/verify_v4.py --output evidence/my-v4-check
```

The verification script runs one short external HTTP script against a temporary database, checks persistence and replay, then closes its server and subprocess. It launches no browser and calls no commercial model.

</details>
