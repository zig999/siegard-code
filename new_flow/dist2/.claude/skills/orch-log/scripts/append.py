#!/usr/bin/env python3
"""CLI: append an event to the orchestration log."""
import argparse
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (
    EventValidationError,
    UnknownEventType,
    append_event,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Append an event to the orchestration log.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--agent", required=True, help="Agent identifier emitting the event.")
    p.add_argument("--event-type", required=True, dest="event_type", help="Event type string.")
    p.add_argument("--task-id", default=None, dest="task_id", help="Task ID (optional).")
    p.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="Attempt number (default: 1).",
    )
    p.add_argument(
        "--data",
        default="{}",
        help="Event payload as a JSON string (default: '{}').",
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
        event = append_event(
            agent=args.agent,
            event_type=args.event_type,
            task_id=args.task_id,
            attempt=args.attempt,
            data=data,
        )
    except UnknownEventType as exc:
        print(json.dumps({"status": "error", "reason": "unknown_event_type", "detail": str(exc)}))
        return 1
    except EventValidationError as exc:
        print(json.dumps({"status": "error", "reason": "validation_error", "detail": str(exc)}))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        return 1

    print(json.dumps(event.to_dict()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
