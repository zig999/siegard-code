#!/usr/bin/env python3
"""CLI: read events from the orchestration log."""
import argparse
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import CorruptedLogError, read_events_filtered


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Read events from the orchestration log.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--from-seq",
        type=int,
        default=0,
        dest="from_seq",
        help="Return events with seq >= FROM_SEQ (default: 0 = all).",
    )
    p.add_argument(
        "--tail",
        type=int,
        default=None,
        help="Return only the last N events (applied after other filters).",
    )
    p.add_argument(
        "--task-id",
        default=None,
        dest="task_id",
        help="Filter by task ID.",
    )
    p.add_argument(
        "--event-type",
        default=None,
        dest="event_type",
        help="Filter by event type.",
    )
    p.add_argument(
        "--phase",
        default=None,
        help="Filter by phase (matches data.phase field).",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        events = read_events_filtered(
            from_seq=args.from_seq,
            task_id=args.task_id,
            event_type=args.event_type,
            phase=args.phase,
            tail=args.tail,
        )
    except CorruptedLogError as exc:
        print(json.dumps({"status": "error", "reason": "corrupted_log", "detail": str(exc)}))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        return 1

    for event in events:
        print(json.dumps(event.to_dict()))

    return 0


if __name__ == "__main__":
    sys.exit(main())
