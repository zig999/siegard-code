#!/usr/bin/env python3
"""CLI: detect workflow mode (new vs resume) for /u-spec entry point."""
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import CorruptedLogError, IllegalTransition, reduce_all

LOG_PATH = Path(".orch/log.jsonl")


def main() -> int:
    if not LOG_PATH.exists():
        print(json.dumps({"mode": "new", "workflow_id": None}))
        return 0

    try:
        state = reduce_all()
    except CorruptedLogError as exc:
        print(json.dumps({"status": "error", "reason": "corrupted_log", "detail": str(exc)}))
        return 1
    except IllegalTransition as exc:
        print(json.dumps({"status": "error", "reason": "illegal_transition", "detail": str(exc)}))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        return 1

    if state.last_seq == 0:
        print(json.dumps({"mode": "new", "workflow_id": None}))
        return 0

    has_sdd = state.current_phase == "sdd" or "sdd" in state.phases
    if has_sdd:
        print(json.dumps({
            "mode": "resume",
            "workflow_id": state.workflow_id,
            "last_seq": state.last_seq,
        }))
    else:
        print(json.dumps({
            "mode": "new",
            "workflow_id": state.workflow_id,
            "last_seq": state.last_seq,
        }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
