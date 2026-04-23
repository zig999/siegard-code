#!/usr/bin/env python3
"""
CLI: emit a worker event to the orchestration log.

Guard-rail: only task_progress, task_completed, and task_failed are allowed.
Any other event type is rejected unconditionally — this is a security boundary,
not a soft validation.

Agent identity is read exclusively from the ORCH_WORKER_ID environment variable.
The caller cannot override it.
"""
import argparse
import json
import os
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (
    EventType,
    EventValidationError,
    UnknownEventType,
    append_event,
)

# The exact set of types workers are allowed to emit.
_ALLOWED_KINDS: dict[str, str] = {
    "progress":  EventType.TASK_PROGRESS.value,
    "completed": EventType.TASK_COMPLETED.value,
    "failed":    EventType.TASK_FAILED.value,
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Emit a worker event (guard-railed to worker-emittable types only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--kind",
        required=True,
        choices=list(_ALLOWED_KINDS),
        help="Event kind: progress | completed | failed",
    )
    p.add_argument("--task-id", required=True, dest="task_id", help="Task ID.")
    p.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="Attempt number (default: 1).",
    )
    p.add_argument(
        "--data",
        default="{}",
        help="Event payload as a JSON object string (default: '{}').",
    )
    return p.parse_args()


def main() -> int:
    worker_id = os.environ.get("ORCH_WORKER_ID")
    if not worker_id:
        print(json.dumps({
            "status": "error",
            "reason": "missing_env",
            "detail": "ORCH_WORKER_ID environment variable is required",
        }))
        return 1

    args = _parse_args()

    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "reason": "invalid_json", "detail": str(exc)}))
        return 1

    if not isinstance(data, dict):
        print(json.dumps({
            "status": "error",
            "reason": "invalid_json",
            "detail": "data must be a JSON object",
        }))
        return 1

    if args.kind == "completed":
        artifacts = data.get("artifacts")
        if artifacts is not None:
            if not isinstance(artifacts, list):
                print(json.dumps({
                    "status": "error",
                    "reason": "validation_error",
                    "detail": "artifacts must be a JSON array",
                }))
                return 1
            for path in artifacts:
                if not isinstance(path, str):
                    print(json.dumps({
                        "status": "error",
                        "reason": "validation_error",
                        "detail": f"artifacts entries must be strings, got {type(path).__name__}",
                    }))
                    return 1
                if path.startswith("/") or path.startswith("\\"):
                    print(json.dumps({
                        "status": "error",
                        "reason": "validation_error",
                        "detail": f"artifact path must be relative, not absolute: {path!r}",
                    }))
                    return 1
                if ".." in path.replace("\\", "/").split("/"):
                    print(json.dumps({
                        "status": "error",
                        "reason": "validation_error",
                        "detail": f"artifact path must not contain '..': {path!r}",
                    }))
                    return 1

    event_type = _ALLOWED_KINDS[args.kind]

    try:
        event = append_event(
            agent=worker_id,
            event_type=event_type,
            task_id=args.task_id,
            attempt=args.attempt,
            data=data,
        )
    except (UnknownEventType, EventValidationError) as exc:
        print(json.dumps({"status": "error", "reason": "validation_error", "detail": str(exc)}))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        return 1

    print(json.dumps(event.to_dict()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
