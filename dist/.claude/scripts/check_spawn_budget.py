#!/usr/bin/env python3
"""
check_spawn_budget.py — How many subagent spawns has this invocation spent?

The host imposes a per-session cap on subagent spawns. When it runs out, the
Agent tool fails for a task that was ALREADY claimed, and the orchestrator sees
a worker that never reported. Observed in production:

    task_failed  reason=worker_exited_without_terminal  retryable=true
    error="Agent spawn limit (200) exhausted in session.
           Worker could not be spawned after task was claimed."

Two things make that expensive. The budget is invisible until it is gone — an
SDD fan-out over several domains can spend it mid-pipeline with no warning. And
once it is gone, every further dispatch in the same session fails the same way,
so an orchestrator that keeps looping burns attempts on a condition that cannot
change until the session ends.

This script makes the budget observable. It counts spawn attempts (`task_claimed`
— one per Agent invocation, including retries) since `--since-seq`, which the
orchestrator sets to its own `log_seq_at_spawn`: the boundary of the current
invocation, and therefore the closest deterministic proxy for "this session"
available from an append-only log that spans sessions.

Usage:
    python3 check_spawn_budget.py --since-seq <log_seq_at_spawn>
                                  [--workflow-id <wid>] [--budget 200]
                                  [--warn-ratio 0.8]

Output (stdout, always JSON):
    {
      "spawned": int,          # task_claimed events after --since-seq
      "budget": int,
      "remaining": int,
      "ratio": float,          # spawned / budget
      "state": "ok" | "low" | "exhausted"
    }

Exit codes:
    0  ok         — headroom remains
    3  low        — crossed --warn-ratio; caller SHOULD escalate E24 once
    4  exhausted  — no headroom; caller MUST stop dispatching this session
    1  error
"""
import argparse
import json
import os
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CLAUDE_DIR / "lib"))

try:
    from orch_core import read_events
except ImportError as exc:  # pragma: no cover — deployment error
    print(json.dumps({
        "status": "error",
        "reason": "internal_error",
        "detail": f"cannot import orch_core: {exc}",
    }), file=sys.stderr)
    sys.exit(1)

# Host default at the time of writing. Overridable because it is a property of
# the runtime, not of this engine — never hardcode it into a decision.
DEFAULT_BUDGET = 200
DEFAULT_WARN_RATIO = 0.8

_SPAWN_EVENT = "task_claimed"


def evaluate(since_seq: int, budget: int, warn_ratio: float,
             workflow_id: str | None = None) -> dict:
    spawned = 0
    # read_events(from_seq) yields seq >= from_seq, so start one past the boundary.
    for event in read_events(max(0, since_seq) + 1):
        if event.event_type != _SPAWN_EVENT:
            continue
        if workflow_id:
            # Namespaced task IDs carry the workflow; an un-namespaced legacy
            # task is counted (it still spent a spawn) rather than dropped.
            data_wf = (event.data or {}).get("workflow_id")
            if data_wf and data_wf != workflow_id:
                continue
        spawned += 1

    ratio = (spawned / budget) if budget > 0 else 1.0
    if spawned >= budget:
        state = "exhausted"
    elif ratio >= warn_ratio:
        state = "low"
    else:
        state = "ok"

    return {
        "spawned": spawned,
        "budget": budget,
        "remaining": max(0, budget - spawned),
        "ratio": round(ratio, 4),
        "state": state,
    }


_EXIT_BY_STATE = {"ok": 0, "low": 3, "exhausted": 4}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-seq", type=int, default=0,
                    help="count task_claimed events after this seq "
                         "(the orchestrator's log_seq_at_spawn)")
    ap.add_argument("--workflow-id", default=os.environ.get("ORCH_WORKFLOW_ID"))
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    ap.add_argument("--warn-ratio", type=float, default=DEFAULT_WARN_RATIO)
    args = ap.parse_args()

    if args.budget <= 0:
        print(json.dumps({
            "status": "error", "reason": "invalid_budget",
            "detail": "--budget must be a positive integer",
        }), file=sys.stderr)
        sys.exit(1)

    result = evaluate(args.since_seq, args.budget, args.warn_ratio,
                      args.workflow_id)
    print(json.dumps(result))
    sys.exit(_EXIT_BY_STATE[result["state"]])


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError:
        # No log yet means nothing has been spawned — full budget, not an error.
        print(json.dumps({
            "spawned": 0, "budget": DEFAULT_BUDGET, "remaining": DEFAULT_BUDGET,
            "ratio": 0.0, "state": "ok",
        }))
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 — always emit JSON for the caller
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
