#!/usr/bin/env python3
"""
check_all_test_tasks_terminal.py — Exit criterion: test / all_test_tasks_terminal.

Criterion met when:
  - At least one test-phase task exists
  - Every test-phase task has status completed
  - Zero DLQ tasks (a failed task is not a passing test run)

Usage:
    python3 .claude/skills/phase-test-rules/scripts/check_all_test_tasks_terminal.py

Output (exit 0):
    {"criterion": "all_test_tasks_terminal", "met": bool, "evidence": {...}}

Output (exit 1, stderr):
    {"status": "error", "reason": "<code>", "detail": "<message>"}
"""
import json
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[3]
_LIB = _CLAUDE_DIR / "lib"
sys.path.insert(0, str(_LIB))

try:
    from orch_core import TaskStatus, reduce_all, now_iso, scoped_phase_tasks
except ImportError as exc:
    print(json.dumps({
        "status": "error",
        "reason": "internal_error",
        "detail": f"cannot import orch_core: {exc}",
    }), file=sys.stderr)
    sys.exit(1)

CRITERION_ID = "all_test_tasks_terminal"
PHASE_NAME = "test"
TERMINAL = {TaskStatus.COMPLETED}
DLQ_STATES = {TaskStatus.DLQ}


def evaluate() -> dict:
    state = reduce_all()
    # 5-a: scoped to ORCH_WORKFLOW_ID when set (shared-log isolation).
    test_tasks = scoped_phase_tasks(state, PHASE_NAME)

    if not test_tasks:
        return {
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {"total": 0, "terminal": 0, "non_terminal": [], "dlq": [], "dlq_blocks_criterion": False},
        }

    dlq_tasks = [
        {"task_id": t.task_id, "status": t.status}
        for t in test_tasks
        if t.status in DLQ_STATES
    ]
    non_terminal = [
        {"task_id": t.task_id, "status": t.status}
        for t in test_tasks
        if t.status not in TERMINAL and t.status not in DLQ_STATES
    ]
    terminal_count = len(test_tasks) - len(non_terminal) - len(dlq_tasks)

    # prod-hardening task 07 (A4-F4): DLQ blocks the test->done transition
    # deterministically — a failed task is not a passing test run. This intent
    # previously lived only in the orchestrator prompt; it is now in the verdict.
    met = len(non_terminal) == 0 and len(dlq_tasks) == 0

    return {
        "criterion": CRITERION_ID,
        "met": met,
        "evidence": {
            "total": len(test_tasks),
            "terminal": terminal_count,
            "non_terminal": non_terminal,
            "dlq": dlq_tasks,
            "dlq_blocks_criterion": len(dlq_tasks) > 0,
        },
    }


def main() -> None:
    result = evaluate()
    # task 10 (A4-F6, Option B): uniform gate schema — emit the full superset.
    result.setdefault("check", result.get("criterion"))
    result.setdefault("status", "ok" if result.get("met") else "blocked")
    result.setdefault("timestamp", now_iso())
    print(json.dumps(result))
    if not result["met"]:
        sys.exit(1)   # task 07: fail-closed exit so the gate is not prompt-trusted


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
