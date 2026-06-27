#!/usr/bin/env python3
"""
select_worker.py — Worker router for the review phase.

Returns the worker sub-agent name for a given task type and optional stack.

Usage:
    python3 .claude/skills/phase-review-rules/scripts/select_worker.py \
      --task-type <type> [--stack <be|fe|fullstack>]

Output (exit 0):
    {"worker": "<subagent-name>", "task_type": "<type>", "stack": "<stack>", "phase": "review"}

Output (exit 1):
    {"status": "error", "reason": "internal_error", "detail": "<message>"}
"""
import argparse
import json
import sys

PHASE_NAME = "review"
DEFAULT_WORKER = "u-be-qa"
VALID_STACKS = {"be", "fe", "fullstack"}

# Stack-independent types: same worker regardless of stack.
_STACK_INDEPENDENT: dict[str, str] = {
    "architecture-review": "u-architecture-reviewer",
    "security-review":     "u-security-reviewer",
}

# Stack-dependent: (task_type, stack) → worker.
_STACK_ROUTING: dict[tuple[str, str], str] = {
    ("qa", "be"):        "u-be-qa",
    ("qa", "fe"):        "u-fe-qa",
    ("qa", "fullstack"): "u-be-qa",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-type", required=True)
    parser.add_argument("--stack", default="be", choices=sorted(VALID_STACKS))
    args = parser.parse_args()

    # task 10 (A4-F5): unknown task_type errors instead of silently routing to
    # DEFAULT_WORKER. (The documented stack default is preserved.)
    _valid_task_types = set(_STACK_INDEPENDENT) | {tt for (tt, _s) in _STACK_ROUTING}
    if args.task_type not in _valid_task_types:
        print(json.dumps({
            "error": "unknown_task_type",
            "task_type": args.task_type,
            "valid_task_types": sorted(_valid_task_types),
        }), file=sys.stderr)
        sys.exit(1)

    if args.task_type in _STACK_INDEPENDENT:
        worker = _STACK_INDEPENDENT[args.task_type]
    else:
        worker = _STACK_ROUTING.get((args.task_type, args.stack), DEFAULT_WORKER)

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
