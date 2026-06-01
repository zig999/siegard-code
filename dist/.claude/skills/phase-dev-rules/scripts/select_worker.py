#!/usr/bin/env python3
"""
select_worker.py — Worker router for the dev phase.

Returns the worker sub-agent name for a given task type and stack.
Stack is resolved by orchestrator-dev from handoff-manifest.yaml (Decision D2).

Usage:
    python3 .claude/skills/phase-dev-rules/scripts/select_worker.py \
      --task-type <type> --stack <be|fe|fullstack>

Output (exit 0):
    {"worker": "<subagent-name>", "task_type": "<type>", "stack": "<stack>", "phase": "dev"}

Output (exit 1):
    {"status": "error", "reason": "internal_error", "detail": "<message>"}
"""
import argparse
import json
import sys

PHASE_NAME = "dev"
DEFAULT_WORKER = "u-be-developer"
VALID_STACKS = {"be", "fe", "fullstack", "fullstack_be", "fullstack_fe"}

# (task_type, stack) → worker.
# For fullstack projects, orchestrator-dev spawns two planning tasks with explicit split
# stacks (fullstack_be and fullstack_fe) so both planners run in parallel. The legacy
# "fullstack" key is kept as a safe fallback for resume cycles on pre-existing sessions.
ROUTING_TABLE: dict[tuple[str, str], str] = {
    ("planning", "be"):           "u-be-planner",
    ("planning", "fe"):           "u-fe-planner",
    ("planning", "fullstack_be"): "u-be-planner",
    ("planning", "fullstack_fe"): "u-fe-planner",
    ("planning", "fullstack"):    "u-be-planner",   # legacy fallback only
    ("impl", "be"):               "u-be-developer",
    ("impl", "fe"):               "u-fe-developer",
    ("impl", "fullstack"):        "u-be-developer",
    ("spec", "be"):               "u-be-developer",
    ("spec", "fe"):               "u-fe-spec-writer",
    ("spec", "fullstack"):        "u-fe-spec-writer",
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
