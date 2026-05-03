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
VALID_STACKS = {"be", "fe", "fullstack"}

# (task_type, stack) → worker. Missing stack falls back to "be".
# NOTE: "fullstack" routes to BE workers by design — the dev phase processes one stack
# per invocation. For fullstack projects, run the dev phase twice: first with stack=be,
# then with stack=fe. The orchestrator-dev derives the stack from handoff-manifest.yaml.
ROUTING_TABLE: dict[tuple[str, str], str] = {
    ("planning", "be"):        "u-be-planner",
    ("planning", "fe"):        "u-fe-planner",
    ("planning", "fullstack"): "u-be-planner",
    ("impl", "be"):            "u-be-developer",
    ("impl", "fe"):            "u-fe-developer",
    ("impl", "fullstack"):     "u-be-developer",
    ("spec", "be"):            "u-be-developer",
    ("spec", "fe"):            "u-fe-spec-writer",
    ("spec", "fullstack"):     "u-fe-spec-writer",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-type", required=True)
    parser.add_argument("--stack", default="be", choices=sorted(VALID_STACKS))
    args = parser.parse_args()

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
