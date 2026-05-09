#!/usr/bin/env python3
"""
check_all_improve_reviewers_completed.py — Exit criterion (targeted mode):
all sdd_improve_*_spec-reviewer tasks reached terminal status `completed`.

Replaces `check_all_domains_validated.py` when `effective_mode == "targeted"`.

Usage:
    python3 .claude/skills/phase-sdd-rules/scripts/check_all_improve_reviewers_completed.py

Environment:
    ORCH_PROJECT_DIR  — project root (default: .)

Output (exit 0 when status=ok, exit 1 when status=blocked):
    {"status": "ok" | "blocked", "check": "all_improve_reviewers_completed",
     "timestamp": "<ISO-8601>", "evidence": {...}}
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

CHECK_ID = "all_improve_reviewers_completed"

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate() -> dict:
    try:
        from orch_core import reduce_all, TaskStatus
    except Exception as exc:
        return {
            "status": "blocked",
            "check": CHECK_ID,
            "timestamp": _now_iso(),
            "evidence": {"error": "orch_core_import_failed", "detail": str(exc)},
        }

    state = reduce_all()

    reviewers = [
        t for t in state.tasks.values()
        if t.phase == "sdd"
        and t.task_id.startswith("sdd_improve_")
        and t.task_id.endswith("_spec-reviewer")
    ]

    if not reviewers:
        return {
            "status": "blocked",
            "check": CHECK_ID,
            "timestamp": _now_iso(),
            "evidence": {
                "total": 0,
                "completed": 0,
                "non_terminal": [],
                "reason": "no_improve_reviewer_tasks_found",
            },
        }

    completed = [t.task_id for t in reviewers if t.status == TaskStatus.COMPLETED]
    non_terminal = [
        {"task_id": t.task_id, "status": t.status.value}
        for t in reviewers if t.status != TaskStatus.COMPLETED
    ]

    met = len(non_terminal) == 0

    return {
        "status": "ok" if met else "blocked",
        "check": CHECK_ID,
        "timestamp": _now_iso(),
        "evidence": {
            "total": len(reviewers),
            "completed": len(completed),
            "completed_ids": completed,
            "non_terminal": non_terminal,
        },
    }


def main() -> int:
    result = evaluate()
    print(json.dumps(result))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({
            "status": "blocked",
            "check": CHECK_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evidence": {"error": "internal_error", "detail": str(exc)},
        }), file=sys.stderr)
        sys.exit(1)
