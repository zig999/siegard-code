#!/usr/bin/env python3
"""CLI: atomically claim a task (check-and-append under the log lock).

Serializes dispatch against concurrent orchestrator instances: the task's
status is re-derived from the log INSIDE the append lock, and task_claimed is
appended only when the task is still `ready`. A racing orchestrator that lost
the claim gets {"claimed": false, "reason": ...} (exit 0 — an expected outcome,
not an error) and MUST drop the task from its dispatch batch without spawning
a worker.

Output (single JSON line):
    {"claimed": true,  "event": {...}}                 — claim appended
    {"claimed": false, "reason": "not_ready:running"}  — lost the race / not eligible
    {"claimed": false, "reason": "task_not_found"}     — task_id not in derived state
    {"status": "error", "reason": ..., "detail": ...}  — exit 1 (invalid input, corrupt log)
"""
import argparse
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (
    CorruptedLogError,
    EventValidationError,
    IllegalTransition,
    claim_task,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Atomically claim a task: append task_claimed only if the task is ready.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--agent", required=True, help="Agent identifier emitting the claim.")
    p.add_argument("--task-id", required=True, dest="task_id", help="Task ID to claim.")
    p.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="Attempt number (default: 1).",
    )
    p.add_argument(
        "--data",
        default="{}",
        help="task_claimed payload as a JSON string (requires phase, worker_type, worker_id).",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "reason": "invalid_json", "detail": str(exc)}))
        return 1

    if not isinstance(data, dict):
        print(json.dumps({"status": "error", "reason": "invalid_json", "detail": "data must be a JSON object"}))
        return 1

    try:
        event, reason = claim_task(
            agent=args.agent,
            task_id=args.task_id,
            attempt=args.attempt,
            data=data,
        )
    except EventValidationError as exc:
        print(json.dumps({"status": "error", "reason": "validation_error", "detail": str(exc)}))
        return 1
    except (IllegalTransition, CorruptedLogError) as exc:
        print(json.dumps({"status": "error", "reason": "state_underivable", "detail": str(exc)}))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        return 1

    if event is None:
        print(json.dumps({"claimed": False, "reason": reason}))
        return 0

    print(json.dumps({"claimed": True, "event": event.to_dict()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
