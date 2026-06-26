#!/usr/bin/env python3
"""
select_worker.py — Worker router for the test phase.

Returns the worker sub-agent name for a given task type and optional stack.
All stacks route to the same worker — u-test-runner is stack-agnostic.

Usage:
    python3 .claude/skills/phase-test-rules/scripts/select_worker.py \
      --task-type <type> [--stack <be|fe|fullstack>]

Output (exit 0):
    {"worker": "<subagent-name>", "task_type": "<type>", "stack": "<stack>", "phase": "test"}

Output (exit 1, stderr):
    {"status": "error", "reason": "internal_error", "detail": "<message>"}
"""
import argparse
import json
import sys

PHASE_NAME = "test"
DEFAULT_WORKER = "u-test-runner"
VALID_STACKS = {"be", "fe", "fullstack"}

ROUTING_TABLE: dict[tuple[str, str], str] = {
    ("test-run", "be"):        "u-test-runner",
    ("test-run", "fe"):        "u-test-runner",
    ("test-run", "fullstack"): "u-test-runner",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-type", required=True)
    parser.add_argument("--stack", default="be", choices=sorted(VALID_STACKS))
    args = parser.parse_args()

    # task 10 (A4-F5): unknown task_type errors instead of silently routing to
    # DEFAULT_WORKER. (The documented stack default is preserved.)
    _valid_task_types = {tt for (tt, _s) in ROUTING_TABLE}
    if args.task_type not in _valid_task_types:
        print(json.dumps({
            "error": "unknown_task_type",
            "task_type": args.task_type,
            "valid_task_types": sorted(_valid_task_types),
        }), file=sys.stderr)
        sys.exit(1)

    worker = ROUTING_TABLE.get((args.task_type, args.stack), DEFAULT_WORKER)

    print(json.dumps({
        "worker": worker,
        "task_type": args.task_type,
        "stack": args.stack,
        "phase": PHASE_NAME,
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "reason": "internal_error",
            "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
