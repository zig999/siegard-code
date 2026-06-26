#!/usr/bin/env python3
"""
CLI: emit a worker event to the orchestration log.

Guard-rail: only task_progress, task_completed, and task_failed are allowed.
Any other event type is rejected unconditionally — this is a security boundary,
not a soft validation.

Agent identity is resolved in priority order:
  1. ORCH_WORKER_ID environment variable (set when env is correctly exported)
  2. Workers registry (.orch/workers/*.json) matched by task_id + attempt
     (fallback when env var is lost between separate Bash calls)
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
    WORKERS_DIR,
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


def _infer_worker_id_from_registry(task_id: str, attempt: int) -> str | None:
    """
    Fallback: find worker_id from .orch/workers/ registry when ORCH_WORKER_ID
    is not set in the environment. Handles the case where env vars are lost
    between separate Bash tool calls in Claude Code.
    """
    if not WORKERS_DIR.exists():
        return None
    for f in WORKERS_DIR.glob("*.json"):
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
            if entry.get("task_id") == task_id and entry.get("attempt") == attempt:
                wid = entry.get("worker_id")
                if wid:
                    return wid
        except Exception:  # noqa: BLE001
            continue
    return None


def main() -> int:
    args = _parse_args()

    worker_id = os.environ.get("ORCH_WORKER_ID") or _infer_worker_id_from_registry(
        args.task_id, args.attempt
    )
    if not worker_id:
        print(json.dumps({
            "status": "error",
            "reason": "missing_env",
            "detail": (
                "ORCH_WORKER_ID is not set and worker_id could not be inferred from "
                f"registry. task_id={args.task_id!r} attempt={args.attempt}. "
                "Export ORCH_WORKER_ID in the same shell call as emit.py."
            ),
        }))
        return 1

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
                # Absolute paths are allowed — workers receive SESSION_DIR as absolute.
                # Only reject path traversal sequences.
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
