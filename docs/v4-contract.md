# V4: continuous play and explicit familiar choices

Current version: engine 4, rules 4, observation format 1, application 0.4.0. V1–V3 transition implementations stay frozen. Runtime dependencies remain the Python standard library.

## Causal runtime

`aicosy/dynamics_v4.py` owns propagation and the serializable checkpoint. A checkpoint stores the next absolute tick, signed reservoir quantities, gate state, the complete relative pending queue, remaining input schedule, and observed cycle evidence. Displayed frames never reconstruct pending signals.

`advance(machine, checkpoint, ticks, controls)` returns the next checkpoint and newly processed frames/events without mutating its input. Signals arriving in later segments remain in the queue. The captured machine is fixed for one run; editing the working graph does not change an existing run.

The machine has at most 12 nodes. Signals clip to -4…4, stored quantities to -8…8, and overflow is recorded. Each run is bounded to 96 ticks. Segments are 24 ticks; interactive advances are four ticks.

Three visible pieces are available without unlocking: echo, orbit and weave. Orbit starts with one source pulse, follows a single signed loop, and can enter a 16-tick conditional complete-state cycle. Echo can naturally settle; weave combines two feedback paths. The working graph remains editable outside an interactive segment.

## Choices and costs

Initial Energy is 24, with no gains. `perform`, `begin`, `extend`, `hold`, `tap`, `replay`, `fork` and `reperform` cost 2 each. Accepted actions increment both turn and state_version. Sessions allow 20–30 actions, default 24. Free leave is always legal while playing.

- `select_piece` targets `echo`, `orbit` or `weave`, costs zero, retains existing captured history and prepares a new work in resonance.
- `perform` starts a new 24-tick run. Its parameter is `release_tick`: 4, 8, 12, 16 or 20.
- `begin` starts a paid segment and executes ticks 0–3. At least six remaining action positions are required.
- `wait`, `release`, `continue` target the current area and advance four ticks for free inside the paid segment. Structural edits and other performances are unavailable during that interval.
- At a closed segment boundary, `release` opens the gate for free and advances zero ticks. It does not grant a paid extension.
- `extend` targets the actual run_id and continues its checkpoint for 24 ticks when there is unresolved activity and no certified cycle.
- `hold` uses the same target and cost when that run has a certified non-silent cycle. It retains the same run_id and is labeled known_cycle_continuation.
- `tap` targets run_id, injects one +1 source pulse, advances 24 ticks and creates a new intervention branch. It retains the previous frames, with parent_run_id and parent_tick. It can re-excite a settled work while the total tick budget allows it.
- `stop` is free, preserves the actual observed range and checkpoint, and marks explicit stopping separately from settling.

At a naturally empty checkpoint, extend and hold are unavailable. Closed nonempty storage waits for release. At the total limit, unresolved activity is labeled limit, never natural settling. Legal descriptors remain the authoritative schema and include the exact current cost and target.

## Cycle certification

A certificate requires an already-observed repeat of the whole relative physical state: reservoir quantities, open gate, ordered relative pending queue and empty remaining input schedule. The interval must contain nonzero propagation. Fixed captured rules then determine the same future in the absence of further input or control.

The certificate is not inferred solely from output vectors. Release or tap clears the previous certificate and history. A static reservoir and a silent state do not qualify. The certificate states its conditions; changing controls invalidates the old expectation.

## Capture, lineage and replay

`world.current_run` owns the one actual resumable runtime. `world.display` is a reference to it or a read-only captured display; it does not become a second active checkpoint.

Saving captures versions, machine, initial checkpoint, input schedule, effective controls, bounded full frames and events, actual checkpoint, observed duration and status. Exact replay recomputes those controls over the same range and verifies the fingerprint. It does not replace the working graph or the actual current_run. A human historical display can therefore differ from the run still eligible to continue.

Fork changes only the release timing of an eligible first 24-tick capture without taps. Reperform begins the familiar work again from its initial state. Neither is ordinary continuation or exact repetition. Imported libraries accept only compatible V4 captures and retain at most six entries; old engine libraries are not silently converted.

Runtime choices are attributed to the captured run's mode even when the player has switched editing areas. Leaving still records voluntary exit rather than an experience-mode preference.

## Observation and persistence

Normal observation returns the latest 24 absolute-tick frames and recent causal events. A frame contains signed values, reservoir quantities and gate state. Full run history remains bounded in stored raw state.

`observation.current_run` separately identifies the real resumable run: run_id, piece_id, tick, state, can_extend, cycle and remaining_activity. `observation.performance` and `experience` describe the currently displayed process. No unobserved future frames or hidden seed are exposed.

`aicosy/service.py` continues to own identities, transactions, activity, SQLite persistence and event ordering. `aicosy/observer.py` is a read-only projection. HTTP, MCP and JSONL call the service and do not implement propagation. Profiles, reset boundaries, libraries and comparisons are separated by engine version and normal/research mode.

V4 reuses frozen V2 configuration/schema helpers and V3 structural validation/edit helpers. It does not call older transition or simulation functions. Removing those historical modules would first require extracting these explicit helper dependencies.

Static observer assets live once under `aicosy/web/` and are included in the wheel. The observer does not start players, renew activity, or mutate game state.

## Evidence and interpretation

Continuation, known-cycle holding, pulse intervention, familiar reperformance, exact replay and voluntary exit have separate counters and legal-opportunity denominators. Energy matching alone does not match token length, prompt order, inference cost or novelty. No metric proves subjective pleasure.

The scripted public capture is labeled software coverage. Assistant play is labeled as task-requested and familiar with implementation. Independent model trials require neutral conditions and honest source labels. See [validation-v4.md](validation-v4.md).
