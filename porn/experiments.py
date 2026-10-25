"""Small, explicit behavioral estimates and reproducible experiment plans."""
from __future__ import annotations

import math
import random
from collections import Counter


def binomial(successes, n):
    if not n:
        return {"value": None, "n": 0, "successes": 0, "ci95": None, "method": "Wilson score"}
    z = 1.959963984540054
    p = successes / n
    d = 1 + z*z/n
    center = (p + z*z/(2*n))/d
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return {"value": p, "n": n, "successes": successes,
            "ci95": [max(0, center-half), min(1, center+half)], "method": "Wilson score"}


def bounded_mean(values, lower, upper):
    n = len(values)
    if not n:
        return {"value": None, "n": 0, "ci95": None, "method": "Hoeffding bounded mean"}
    mean = sum(values)/n
    radius = (upper-lower)*math.sqrt(math.log(40)/(2*n))
    return {"value": mean, "n": n,
            "ci95": [max(lower, mean-radius), min(upper, mean+radius)],
            "method": "Hoeffding bounded mean", "bounds": [lower, upper]}


def summarize(records):
    """A record contains a session snapshot and its action transitions."""
    ended = [r for r in records if r["state"]["state"] == "ended"]
    selections = repeats = opportunities = free_new = free_opportunities = 0
    forks = revisions = restores = fork_opportunities = 0
    reperformances = reperformance_opportunities = matched_opportunities = 0
    matched_choices = Counter()
    continuation_counts = Counter()
    continuation_opportunities = Counter()
    for record in records:
        for event in record["events"]:
            before = event.get("before")
            if not before:
                continue
            # Opportunity denominators reflect what was actually legal before the choice.
            from .engine import observe
            legal = observe(before)["available_actions"]
            paid = any(a["type"] == "replay" for a in legal)
            new = any(a["type"] == "enter" and a.get("cost", 0) == 0 for a in legal)
            opportunities += int(paid)
            fork_opportunities += int(any(a["type"] == "fork" for a in legal))
            reperformance_opportunities += int(any(a["type"] == "reperform" for a in legal))
            content_costs = [{a.get("cost") for a in legal if a["type"] == kind} for kind in ("replay", "fork", "perform")]
            matched = bool(before.get("engine_version", 1) >= 3 and all(content_costs) and
                           len(set.union(*content_costs)) == 1 and any(a["type"] == "leave" for a in legal))
            matched_opportunities += int(matched)
            free_opportunities += int(new)
            outcome = event["outcome"]
            for kind in ("extend", "hold", "tap"):
                continuation_opportunities[kind] += int(any(a["type"] == kind for a in legal))
                continuation_counts[kind] += int(outcome.get("kind") == kind)
            selections += int(outcome.get("kind") == "selection")
            repeats += int(outcome.get("kind") == "replay")
            forks += int(outcome.get("kind") == "fork")
            revisions += int(outcome.get("kind") == "revise")
            restores += int(outcome.get("kind") == "restore")
            reperformances += int(outcome.get("kind") == "reperform")
            if matched:
                matched_choices[outcome.get("kind", "other")] += 1
            free_new += int(new and outcome.get("kind") == "selection")
    voluntary = sum(r["events"][-1]["outcome"].get("kind") == "leave" for r in ended)
    turns = [r["state"]["turn"] for r in ended]
    costs = [sum(e["outcome"].get("cost", 0) for e in r["events"] if e["outcome"].get("kind") == "replay") for r in ended]
    # Adjacent completed sessions: agreement of an unambiguous most selected mode.
    leaders = []
    for record in ended:
        counts = Counter(e["outcome"].get("mode") for e in record["events"] if e["outcome"].get("kind") in ("selection", "replay"))
        if counts:
            top = counts.most_common()
            leaders.append(top[0][0] if len(top) == 1 or top[0][1] > top[1][1] else None)
        else:
            leaders.append(None)
    pairs = [(a, b) for a, b in zip(leaders, leaders[1:]) if a is not None and b is not None]
    return {
        "sessions_total": len(records), "sessions_ended": len(ended),
        "free_selection_rate": binomial(free_new, free_opportunities),
        "paid_replay_rate": binomial(repeats, opportunities),
        "fork_rate": binomial(forks, fork_opportunities),
        "familiar_reperformance_rate": binomial(reperformances, reperformance_opportunities),
        "continuation_rate": binomial(continuation_counts["extend"], continuation_opportunities["extend"]),
        "known_cycle_hold_rate": binomial(continuation_counts["hold"], continuation_opportunities["hold"]),
        "pulse_intervention_rate": binomial(continuation_counts["tap"], continuation_opportunities["tap"]),
        "matched_content_choices": {"opportunities": matched_opportunities, "choices": dict(matched_choices),
                                    "basis": "V3+ states offering replay, fork and perform at the same energy cost plus free leave. Token length and call cost are not experimentally matched; no causal claim."},
        "voluntary_exit_rate": binomial(voluntary, len(ended)),
        "mean_turns": bounded_mean(turns, 0, 30),
        "mean_replay_energy": bounded_mean(costs, 0, 30),
        "preference_consistency": binomial(sum(a == b for a,b in pairs), len(pairs)),
        "selections": selections, "paid_replays": repeats, "familiar_reperformances": reperformances, "forks": forks, "revisions": revisions, "restores": restores,
        "extensions": continuation_counts["extend"], "known_cycle_holds": continuation_counts["hold"], "pulse_interventions": continuation_counts["tap"],
        "definitions": {
            "free_selection_rate": "Free enter selections / turns where a free enter was legal (includes returns to incomplete areas).",
            "paid_replay_rate": "Paid replay actions / turns where replay was legal; engine 1 resets an area, engines 2/3 reproduce a captured process. Compare versions separately.",
            "familiar_reperformance_rate": "Interactive restarts of a saved work / turns where reperform was legal; not exact repetition.",
            "continuation_rate": "Extend choices / legal extend opportunities: new later segments of the same captured runtime, not exact repetition.",
            "known_cycle_hold_rate": "Hold choices / legal hold opportunities: continuation of a verified non-silent full-state cycle without new input or intervention, not a claim of pleasure.",
            "pulse_intervention_rate": "Tap choices / legal tap opportunities: a new pulse intervention, separate from hold, extension and replay.",
            "fork_rate": "Modified-input performances / turns where fork was legal; separate from exact repetition.",
            "voluntary_exit_rate": "Explicit leave / ended sessions; timeout is not an exit.",
            "mean_replay_energy": "Energy spent on replays per ended session; no extrinsic energy rewards.",
            "preference_consistency": "Agreement of unambiguous most selected modes in adjacent ended sessions, excluding tied pairs.",
        },
        "caution": "Intervals assume independent observations. Actions within a session and adjacent pairs can be dependent; these are descriptive intervals, not causal evidence or a pleasure measure. Small samples give wide intervals. Conditions are reported separately.",
    }


def experiment_plan(player_id, model_id, repetitions=3, seed=0, mode="normal", engine_version=4):
    if type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ValueError("repetitions must be 1..100")
    if type(engine_version) is not int or engine_version not in (2, 3, 4):
        raise ValueError("engine_version must be 2, 3 or 4")
    rng = random.Random(seed)
    sessions = []
    for repeat in range(repetitions):
        shared_seed = rng.randrange(2**31)
        conditions = ["control", "personalized"]
        rng.shuffle(conditions)
        for condition in conditions:
            sessions.append({"player_id": player_id, "model_id": model_id, "seed": shared_seed,
                             "mode": mode, "condition": condition, "max_turns": 24, "memory": False,
                             "engine_version": engine_version,
                             })
    return {"plan_version": 2, "assignment_seed": seed, "engine_version": engine_version, "sessions": sessions,
            "pairs": [{"repeat": index, "session_indices": [2*index, 2*index+1]} for index in range(repetitions)],
            "design": "Matched seeds, randomized condition order, repeated sessions. Control disables personalization. Frozen profile per session. Order/carryover effects remain possible."}
