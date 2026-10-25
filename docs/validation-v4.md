# V4 validation and limits

Date: 2026-10-25. AICosy application 0.4.0, engine/rules 4, observation format 1. Local runtime checks and GitHub CI are recorded separately; neither is evidence of subjective experience.

## Checks completed

Before the public-name update, 43 directly related headless checks passed in approximately 0.65 seconds:

- 9 V4 checkpoint/engine checks: exact split advancement, in-flight signals, non-silent complete-state cycles, intervention invalidation, bounds, replay/display separation and captured-mode attribution.
- 4 V4 service checks: reopening SQLite mid-run, absolute frame windows, replay without replacing a live runtime, separate counters and V3/V4 memory/profile isolation.
- 3 V3 service compatibility checks, 7 shared service checks, 5 observer/partition checks, 2 historical recording checks, 3 real stdio subprocess checks and 10 HTTP checks.

Command:

```sh
python3.11 -m unittest tests.test_continuous_engine tests.test_continuous_service tests.test_experience_service tests.test_service tests.test_observer tests.test_recording_compatibility tests.test_protocols tests.test_http -v
```

Compact historical fixtures verify all 17 V1, 12 V2 and 8 V3 recorded transitions against fixed state and outcome digests. Identifiers were relabeled; raw local research exports are not published. The V2 verification helper now uses the public V1 fixture, and the original V1 TCP demonstration is explicitly archived.

## Current AICosy package check

The current AICosy revision passed 11 focused headless checks covering release configuration, new and legacy stdio names, and historical recording compatibility. A wheel was built with existing local build tools, installed offline into a temporary directory, and run outside the source checkout. The three `aicosy-*` entry points started successfully; manifest, rules, OpenAPI and both page titles identify AICosy. MCP discovery contains nine `aicosy_*` tools and accepts both legacy call prefixes. A real HTTP authentication check rejected anonymous access and accepted the configured `AICOSY_ACCESS_TOKEN`.

Wheel metadata uses `aicosy`, `aicosy team` and MIT. Its README, license and all 35 runtime/resource files match the source. The four observer assets are complete. Public-file and whole-wheel scans found no known personal attribution, project-owner account or workstation home paths. The test process and temporary installation were removed; the approximately 109 KiB wheel remains in ignored `dist/`.

The game flow was not repeated for this final naming update; the frozen engine and recording fixtures are unchanged. Earlier full-flow evidence is recorded below. Current remote CI, visible browser interaction and commercial model behavior are separate checks.

## Python package path verification

The runtime import package and source directory are now `aicosy`. The former `porn` package directory and shim module are absent. All adapters, test imports, scripts, source links and installed-resource lookups use the new path.

After the move, 25 focused headless checks passed: V4 engine/service behavior, protocol and configuration handling, and the recorded V1/V2/V3 replay paths. Nine frozen engine/dynamics/world modules remain byte-identical to the preceding commit.

A freshly built wheel was installed outside the checkout and exercised with `python -S` to exclude global and user site packages. `aicosy` imports and `GameService` resolved inside that installation, the old package could not be found, and all four resources loaded through `files("aicosy")`. The wheel contains no `porn/` directory or `porn.py`; 35 runtime/resource files match the current source. The HTTP observer, stdio adapters, 12-action rule script, replay and SQLite recovery after a service-process restart passed. Attribution remains exactly `aicosy team` and the whole-wheel identifier scan passed.

The two temporary servers exited and about 3.41 MiB of temporary installation files were removed. The current wheel remains under ignored `dist/`; its compact report stays in ignored `evidence/publication/`. No visible window or commercial model was used. Existing databases retain their established file paths and stored formats.

## Earlier release verification

The published GitHub commit was independently confirmed through the GitHub REST API. Its original wheel's 35 runtime/resource files were compared byte-for-byte with that commit, installed offline outside the checkout, and exercised through real HTTP and stdio. Its existing GitHub `python` check completed successfully. This verifies the downloaded code locally; GitHub itself does not host the running game.

Before adoption of the current AICosy name, the preceding public-name/configuration revision passed these 25 small headless checks:

```sh
python3.11 -m unittest tests.test_release_config tests.test_protocols tests.test_recording_compatibility tests.test_http tests.test_observer -v
```

The preceding revision's wheel was installed outside the checkout. Its three command entry points ran successfully. Eight HTTP routes, the then-current public name in discovery/API/pages, 12 scripted actions, observer records, deterministic replay, and SQLite recovery after a server-process restart passed. MCP discovery used that revision's canonical tool names and still accepted legacy calls. Both new and legacy access-token variables were exercised: anonymous requests were rejected and the correct test token succeeded.

The preceding wheel's metadata used its then-current distribution name, a project-only author and MIT. All four observer assets are present. All 35 runtime/resource files and the wheel's README description matched the source at that verification point. Test services exited and temporary installation directories were removed. Compact machine-readable reports for those checks stay in ignored `evidence/publication/`. These earlier results do not establish that the current AICosy package has been tested.

No runtime-blocking defect was found in either version tested at that stage. Practical prerequisites remain Python 3.11+, an available local port, and a separately connected model or the explicit rule-script demo. The README documents these paths. Building with `pip install .` may download setuptools; running directly from the source needs no third-party packages. A busy port now produces an actionable `--port 8766` message. The revised remote commit and its own CI must be checked after publication.

## Actual protocol and persistence paths

One external rule client completed a 12-action localhost HTTP flow. It exercised all three pieces, continuation, certified-cycle hold, two pulse interventions, exact replay, and free exit. Its SQLite state was closed and reopened, with identical observations and verified deterministic replay. The temporary server and database were removed.

The compact captured result is [examples/scripted-session.json](../examples/scripted-session.json). It is a prescribed software check, not a model preference trial. Reproduce it with:

```sh
python3.11 scripts/verify_v4.py --output evidence/my-v4-check
```

An integration review found and fixed a mode-attribution issue: continuing a captured resonance run after entering the creation area must still attribute that continuation to the captured run's mode. A focused regression case covers it.

## Live assistant play

The project-author assistant also played a separate 11-action session through the public HTTP interface. It chose weave and continued it to tick 48, switched to orbit, paid for one known-cycle hold, injected a pulse, paid to hold the resulting certified cycle again, then selected echo for a natural ending and left with 10 of 24 Energy.

Recorded counts: 1 ordinary extension, 2 known-cycle holds, 1 pulse intervention, 0 exact replay actions. The bounded orbit branch reached tick 96; its unresolved signal was labeled as a limit. Echo subsequently settled naturally. All 11 session transitions verified through deterministic replay.

This was task-directed play by an assistant familiar with the implementation and publication context. It had no prescribed action or hold quota, but it was not blind, independent or neutral evidence of model happiness. Its curated behavior description cannot establish a general preference or subjective feeling. Raw logs remain local.

## Observer and package

The JavaScript parses. All 70 HTML IDs are unique and all 68 referenced DOM IDs exist. A browser-free projection check used actual V4 service data: windows 24–47 and 48–71, per-frame stored quantities, a real current run at tick 72 while displaying an earlier 24-tick replay, the 16-tick cycle, and naturally settled echo with tap available. V3 records remain displayable.

A wheel was built with existing local build tools, without installing new runtime dependencies. It was installed into one small temporary package directory. Outside the checkout, imports, the V4 in-memory session and all four packaged observer assets passed; command-module help paths also passed. The final metadata uses `License-Expression: MIT`. The temporary installation, build directory and egg-info were removed. One approximately 108 KiB wheel is retained locally under `dist/`, excluded from Git.

## Limits and release state

No browser or visible test window was launched. Layout, clicking, animation and accessibility interaction have not been visually accepted in this iteration. No commercial provider key was used, no independent model cohort was run, and no hidden activation measurement exists. No stress test, multi-worker run or project copy was created.

The original remote commit and its successful CI were confirmed through the GitHub API; the repository had one branch and no tags at that verification point. These are historical observations, not a claim about the current AICosy commit, visibility or CI. See the [release checklist](release-checklist.md) for source, package and commit-identity checks before the next publication.

While the local server is running, the observer is available at [localhost](http://127.0.0.1:8765/). Reading saved histories does not simulate new activity. Raw research data and local evidence are excluded from public Git contents.
