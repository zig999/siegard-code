#!/usr/bin/env python3
"""CLI: reduce event log to full OrchState JSON.

Default: strict global reduction (reduce_all) — one illegal transition anywhere
aborts. With --workflow <id>: scoped reduction (reduce_workflow) so a corrupted
sibling workflow cannot block deriving this one.
"""
import argparse
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (
    CorruptedLogError,
    IllegalTransition,
    reduce_all,
    reduce_workflow,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Reduce event log to OrchState JSON.")
    ap.add_argument(
        "--workflow",
        default=None,
        help="Scope reduction to a single workflow_id (isolates corrupted siblings).",
    )
    args = ap.parse_args()

    try:
        state = reduce_workflow(args.workflow) if args.workflow else reduce_all()
    except CorruptedLogError as exc:
        print(json.dumps({"status": "error", "reason": "corrupted_log", "detail": str(exc)}))
        return 1
    except IllegalTransition as exc:
        print(json.dumps({"status": "error", "reason": "illegal_transition", "detail": str(exc)}))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        return 1

    print(json.dumps(state.to_dict()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
