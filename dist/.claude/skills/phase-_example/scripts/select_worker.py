#!/usr/bin/env python3
"""
select_worker.py — Phase worker router.

Returns the worker sub-agent name for a given task type.
Replace the ROUTING_TABLE with the actual task type → worker mappings for this phase.

Usage:
    python3 scripts/select_worker.py --task-type <type>

Output (exit 0):
    {"worker": "<subagent-name>", "task_type": "<type>", "phase": "<phase>"}

Output (exit 1):
    {"status": "error", "reason": "unknown_task_type", "detail": "<message>"}
"""
import argparse
import json
import sys

# Replace with actual phase name and routing table.
PHASE_NAME = "{name}"
DEFAULT_WORKER = "{worker-default}"

ROUTING_TABLE: dict[str, str] = {
    # "{task_type}": "{worker-subagent-name}",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-type", required=True)
    args = parser.parse_args()

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
