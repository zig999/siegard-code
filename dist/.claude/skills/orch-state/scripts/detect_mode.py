#!/usr/bin/env python3
"""CLI: detect workflow mode (new vs resume vs completed) for /u-spec entry point.

`completed` (2026-07-15 post-fix audit, 1.6): "sdd in state.phases" alone meant
mode=resume FOREVER after the first workflow — including after it finished — so a
second /u-spec on a used project could never start (the meta just re-printed the
old completion report). A terminal workflow (every required phase COMPLETED,
M3's rule) now reports mode=completed so the entry point can direct the operator
to archive/purge the finished runtime before declaring a new workflow.
"""
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import CorruptedLogError, IllegalTransition, PhaseStatus, reduce_all

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
    required = [p for p in state.phases.values() if p.required]
    all_required_completed = bool(required) and all(
        p.status == PhaseStatus.COMPLETED for p in required
    )
    if has_sdd and all_required_completed:
        print(json.dumps({
            "mode": "completed",
            "workflow_id": state.workflow_id,
            "last_seq": state.last_seq,
        }))
    elif has_sdd:
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
