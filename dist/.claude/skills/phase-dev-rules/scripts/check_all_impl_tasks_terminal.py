#!/usr/bin/env python3
"""
check_all_impl_tasks_terminal.py — Exit criterion: dev / all_impl_tasks_terminal.

Criterion met when:
  - At least one dev-phase task exists
  - Every dev-phase task has status completed or dlq

Usage:
    python3 .claude/skills/phase-dev-rules/scripts/check_all_impl_tasks_terminal.py

Output (exit 0):
    {"criterion": "all_impl_tasks_terminal", "met": bool, "evidence": {...}}

Output (exit 1):
    {"status": "error", "reason": "<code>", "detail": "<message>"}
"""
import json
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[3]
_LIB = _CLAUDE_DIR / "lib"
sys.path.insert(0, str(_LIB))

try:
    from orch_core import TaskStatus, reduce_all
except ImportError as exc:
    print(json.dumps({
        "status": "error",
        "reason": "internal_error",
        "detail": f"cannot import orch_core: {exc}",
    }), file=sys.stderr)
    sys.exit(1)

CRITERION_ID = "all_impl_tasks_terminal"
PHASE_NAME = "dev"
TERMINAL = {TaskStatus.COMPLETED, TaskStatus.DLQ}


def evaluate() -> dict:
    state = reduce_all()

    dev_tasks = [t for t in state.tasks.values() if t.phase == PHASE_NAME]

    if not dev_tasks:
        return {
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {"total": 0, "terminal": 0, "non_terminal": []},
        }

    non_terminal = [
        {"task_id": t.task_id, "status": t.status}
        for t in dev_tasks
        if t.status not in TERMINAL
    ]
    terminal_count = len(dev_tasks) - len(non_terminal)

    return {
        "criterion": CRITERION_ID,
        "met": len(non_terminal) == 0,
        "evidence": {
            "total": len(dev_tasks),
            "terminal": terminal_count,
            "non_terminal": non_terminal,
        },
    }


def main() -> None:
    print(json.dumps(evaluate()))


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError:
        print(json.dumps({
            "status": "error",
            "reason": "log_missing",
            "detail": "orchestration log not found — run orchestrator first",
        }), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "reason": "internal_error",
            "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
