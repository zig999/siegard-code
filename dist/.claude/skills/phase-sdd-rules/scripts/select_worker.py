#!/usr/bin/env python3
"""
select_worker.py — Worker router for the sdd phase.

Returns the worker sub-agent name for a given task type.

Usage:
    python3 .claude/skills/phase-sdd-rules/scripts/select_worker.py --task-type <type>

Output (exit 0):
    {"worker": "<subagent-name>", "task_type": "<type>", "phase": "sdd"}

Output (exit 1):
    {"status": "error", "reason": "internal_error", "detail": "<message>"}
"""
import argparse
import json
import sys

PHASE_NAME = "sdd"
DEFAULT_WORKER = "u-spec-writer"

ROUTING_TABLE: dict[str, str] = {
    "spec-triage": "u-spec-triage",
    "spec-writer": "u-spec-writer",
    "spec-reviewer": "u-spec-reviewer",
    "spec-back": "u-spec-back",
    "spec-front": "u-spec-front",
    "spec-validator": "u-spec-validator",
    "spec-compliance": "u-spec-compliance",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-type", required=True)
    args = parser.parse_args()

    # task 10 (A4-F5): unknown task_type errors instead of silently routing to
    # DEFAULT_WORKER. (The documented stack default is preserved.)
    _valid_task_types = set(ROUTING_TABLE)
    if args.task_type not in _valid_task_types:
        print(json.dumps({
            "error": "unknown_task_type",
            "task_type": args.task_type,
            "valid_task_types": sorted(_valid_task_types),
        }), file=sys.stderr)
        sys.exit(1)

    worker = ROUTING_TABLE.get(args.task_type, DEFAULT_WORKER)

    print(json.dumps({
        "worker": worker,
        "task_type": args.task_type,
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
