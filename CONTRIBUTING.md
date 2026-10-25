# Contributing to AICosy

Read [README.md](README.md), [AGENTS.md](AGENTS.md), and the relevant versioned rule contract before changing behavior. Python 3.11+ and the standard library are the runtime baseline. Discuss new dependencies before adding them.

Keep deterministic transitions in the versioned engine. The service owns transactions, identities, activity and persistence; adapters delegate to it. Observer projections are read-only. Preserve old engines and saved-session replay when adding new rules. Partition profiles, memory and metrics by engine version and normal/research mode.

Label scripted checks, random agents, mock providers and caller-declared model identities accurately. A replay count, preference score or model self-report does not establish subjective pleasure. Never fabricate player activity or hidden activations.

Use focused, headless checks for changed paths. The repository's small standard-library checks run with:

```sh
python3.11 -m unittest tests.test_continuous_engine tests.test_continuous_service -v
```

Do not introduce stress suites, extra workers, project copies or visible test windows. Temporary databases, servers and dedicated test processes must have guaranteed cleanup. Report separately what was checked in code, through the protocol, in persistence and in the interface.

Keep pull requests scoped. Describe the behavior, compatibility impact, checks actually run, and remaining gaps. Do not commit local databases, raw research exports, transcripts containing credentials, `.env` files, logs or generated build output. Public examples belong in `examples/` and must use curated, clearly labelled data.

This project uses the [MIT license](LICENSE). Check the actual terms and required attribution before introducing third-party code or assets.
