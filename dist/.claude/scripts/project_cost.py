#!/usr/bin/env python3
"""
project_cost.py — What will this SDD phase cost, before the first worker is spawned?

The asymmetry this removes. The `triage` already knows everything needed to price
the phase: the mode, the affected specs, the domains. It never reported it, and
the one surface that would have — the E99 confirmation gate, which prints
`estimated_task_contracts` — is skipped whenever `bypass_e99` is set, i.e. on
every `/u-improve`. Since `/u-improve` is the only usable entry point on a
populated repository, the operator in practice never saw a number before
committing to the run.

Measured consequence: a change of three type-level items spent **56 min of sdd
across 10 workers**, and the price only became visible afterwards.

The model. Wall clock tracks the number of dispatched workers far more closely
than it tracks the size of the change:

    workflow A  full      2 domains  10 workers  56.0 min   5.6 min/worker
    workflow B  full      3 domains  18 workers  ~106 min   5.9 min/worker
    workflow C  targeted  1 domain    7 workers  48.3 min   6.9 min/worker

`workers x ~6 min` therefore predicts the phase, and — importantly — it explains
why the "fast" path saves so much less than expected: targeted mode drops
pipeline stages but is capped at 1 concurrent worker, so it trades parallelism
for the stages it skips.

Estimates are a floor: they exclude human gate waits and inter-phase latency.

Usage:
    python3 project_cost.py --triage <path/to/triage.json> [--json-only]

Output (stdout, JSON, exit 0):
    {
      "mode": "standard" | "targeted" | "skip",
      "workers": int,
      "wall_clock_minutes": int,
      "concurrency": int,
      "breakdown": {"<label>": int, ...},
      "basis": "<one-line explanation>"
    }

Exit codes:
    0  projection produced
    1  triage.json missing or unreadable
"""
import argparse
import json
import sys
from pathlib import Path

# Measured across three real workflows (5.6 / 5.9 / 6.9 min per dispatched
# worker). Includes the ~1.4 min of per-task orchestration overhead — reduce,
# claim, dispatch, verify — that is charged whatever the worker does.
WALL_CLOCK_MINUTES_PER_WORKER = 6

# Concurrency ceilings owned by the sdd state machine (sm_runner --machine sdd
# --state select_batch). Mirrored here for the projection only; the dispatcher
# remains the authority.
CONCURRENCY = {"standard": 2, "targeted": 1}

STANDARD_STAGES_PER_DOMAIN = 4      # writer -> reviewer -> back -> validator
TARGETED_STAGES_PER_SPEC = 2        # domain worker -> reviewer
GLOBAL_WORKERS = 2                  # triage + compliance
TARGETED_GLOBAL_WORKERS = 1         # triage only (no cross-domain compliance)
FRONT_LEG_WORKERS = 2               # spec-front + front validator


def project(triage: dict) -> dict:
    trigger = triage.get("trigger", "u-spec")
    mode_hint = triage.get("mode_hint", "full")
    change_type = triage.get("type", "spec_change_required")
    stack = triage.get("stack", "be")
    domains = triage.get("domains") or []
    affected = triage.get("affected_specs") or []

    if change_type == "implementation_only":
        return {
            "mode": "skip", "workers": 1,
            "wall_clock_minutes": WALL_CLOCK_MINUTES_PER_WORKER,
            "concurrency": 1,
            "breakdown": {"triage": 1},
            "basis": "implementation_only — the spec pipeline is skipped entirely",
        }

    # `effective_mode` mirrors orchestrator-sdd: an /u-improve with a fast-track
    # hint runs targeted; everything else runs the standard pipeline.
    targeted = trigger == "u-improve" and str(mode_hint).startswith("fast-track")
    mode = "targeted" if targeted else "standard"

    breakdown: dict[str, int] = {}
    if targeted:
        # Fan-out is per affected_specs ENTRY, not per domain: three spec files in
        # one domain produce three worker pairs. This is what made a "fast-track"
        # phase dispatch 6 workers for a single domain.
        units = max(1, len(affected))
        breakdown["triage"] = TARGETED_GLOBAL_WORKERS
        breakdown["per_spec_pairs"] = units * TARGETED_STAGES_PER_SPEC
    else:
        n_domains = max(1, len(domains) or len(affected) or 1)
        breakdown["triage_and_compliance"] = GLOBAL_WORKERS
        breakdown["domain_back_legs"] = n_domains * STANDARD_STAGES_PER_DOMAIN
        if stack in ("fe", "fullstack"):
            breakdown["front_leg"] = FRONT_LEG_WORKERS

    workers = sum(breakdown.values())
    concurrency = CONCURRENCY[mode]

    # Deliberately NOT divided by concurrency. That is the counter-intuitive part
    # of the measurements, and dividing makes the estimate worse:
    #
    #   workflow A  10 workers, 2 concurrent -> 56.0 min actual
    #               workers x 6      = 60 min   (~7% high)
    #               workers x 6 / 2  = 30 min   (~46% LOW)
    #
    # Parallelism buys much less than it looks like it should, because a batch is
    # turn-synchronous: the orchestrator spawns the batch and cannot advance until
    # every member returns, so a stage costs max(members), never mean(members),
    # and the faster domain simply waits. `concurrency` is reported for context,
    # not applied as a divisor.
    minutes = workers * WALL_CLOCK_MINUTES_PER_WORKER

    return {
        "mode": mode,
        "workers": workers,
        "wall_clock_minutes": minutes,
        "concurrency": concurrency,
        "breakdown": breakdown,
        "basis": (
            f"{workers} worker(s) at ~{WALL_CLOCK_MINUTES_PER_WORKER} min each "
            f"({concurrency} dispatched concurrently, which does not divide the "
            "total — a batch is turn-synchronous, so a stage costs its slowest "
            "member)"
            + (". Targeted mode is capped at 1 concurrent worker: it trades "
               "parallelism for the stages it skips, which is why it saves far "
               "less wall clock than it saves workers" if targeted else "")
            + ". Floor: excludes human gate waits and inter-phase latency."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--triage", required=True, help="path to triage.json")
    ap.add_argument("--json-only", action="store_true",
                    help="suppress the human-readable line on stderr")
    args = ap.parse_args()

    path = Path(args.triage)
    if not path.is_file():
        print(json.dumps({
            "status": "error", "reason": "triage_not_found", "detail": str(path),
        }), file=sys.stderr)
        sys.exit(1)
    try:
        triage = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "status": "error", "reason": "triage_unreadable", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)

    result = project(triage)
    print(json.dumps(result))
    if not args.json_only:
        print(
            f"sdd projection: {result['workers']} workers, "
            f"~{result['wall_clock_minutes']} min ({result['mode']} mode)",
            file=sys.stderr,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
