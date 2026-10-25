# Captured scripted example

`scripted-session.json` is a compact capture from one real localhost HTTP run of `clients.continuous_player.ContinuousPlayer` through `clients.rule_agent`. Choices are prescribed interface coverage, not an independent model's preferences.

It visits all three pieces, extends a real runtime, holds a certified cycle, injects two new pulses, and exactly replays a saved first segment. Runtime and saved-record IDs belong to that historical run; new runs get new IDs.

Reproduce the coverage with a clean temporary database:

```sh
python3.11 scripts/verify_v4.py --output evidence/my-v4-check
```

Add `--example examples/my-capture.json` to write a new compact capture. Existing evidence and examples are not overwritten. Temporary services and databases are cleaned up.

Local exports are excluded from Git. Fixtures under `tests/fixtures/` contain relabeled identifiers and fixed historical state/outcome digests.
