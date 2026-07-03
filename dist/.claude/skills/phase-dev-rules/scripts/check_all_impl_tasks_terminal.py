#!/usr/bin/env python3
"""
check_all_impl_tasks_terminal.py — Exit criterion: dev / all_impl_tasks_terminal.

Criterion met when:
  - At least one dev-phase task exists
  - Every dev-phase task has status completed or dlq

Usage:
    python3 .claude/skills/phase-dev-rules/scripts/check_all_impl_tasks_terminal.py

Output schema (per GATE_SCHEMA_UNIFORMITY in specs/principles.md):
  Always emits {status, check, timestamp} for uniform gate consumption.
  Legacy fields {criterion, met, evidence} preserved for orchestrator-dev compatibility.

Output (exit 0 when met):
    {"status": "ok", "check": "all_impl_tasks_terminal", "timestamp": "<ISO8601>",
     "criterion": "all_impl_tasks_terminal", "met": true, "evidence": {...}}

Output (exit 1 when blocked or error):
    {"status": "blocked", "check": "all_impl_tasks_terminal", "timestamp": "<ISO8601>",
     "criterion": "all_impl_tasks_terminal", "met": false, "evidence": {...}}
    {"status": "error", "reason": "<code>", "detail": "<message>"}
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[3]
_LIB = _CLAUDE_DIR / "lib"
sys.path.insert(0, str(_LIB))

try:
    from orch_core import TaskStatus, reduce_all, scoped_phase_tasks
except ImportError as exc:
    print(json.dumps({
        "status": "error",
        "reason": "internal_error",
        "detail": f"cannot import orch_core: {exc}",
    }), file=sys.stderr)
    sys.exit(1)

CRITERION_ID = "all_impl_tasks_terminal"
PHASE_NAME = "dev"
TERMINAL = {TaskStatus.COMPLETED}
DLQ_STATES = {TaskStatus.DLQ}


def evaluate() -> dict:
    state = reduce_all()

    # 5-a: scoped to ORCH_WORKFLOW_ID when set — another workflow's non-terminal
    # task in the shared log must not block this workflow's exit.
    dev_tasks = scoped_phase_tasks(state, PHASE_NAME)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not dev_tasks:
        return {
            "status": "blocked",
            "check": CRITERION_ID,
            "timestamp": timestamp,
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {"total": 0, "terminal": 0, "non_terminal": [], "dlq": []},
        }

    dlq_tasks = [
        {"task_id": t.task_id, "status": t.status}
        for t in dev_tasks
        if t.status in DLQ_STATES
    ]
    non_terminal = [
        {"task_id": t.task_id, "status": t.status}
        for t in dev_tasks
        if t.status not in TERMINAL and t.status not in DLQ_STATES
    ]
    terminal_count = len(dev_tasks) - len(non_terminal) - len(dlq_tasks)

    # Criterion met when zero non-terminal tasks remain.
    # DLQ is a terminal state — no further retries occur; orchestrator escalates separately.
    met = len(non_terminal) == 0

    return {
        "status": "ok" if met else "blocked",
        "check": CRITERION_ID,
        "timestamp": timestamp,
        "criterion": CRITERION_ID,
        "met": met,
        "evidence": {
            "total": len(dev_tasks),
            "terminal": terminal_count,
            "non_terminal": non_terminal,
            "dlq": dlq_tasks,
            "dlq_blocks_criterion": len(dlq_tasks) > 0,
        },
    }


def main() -> None:
    result = evaluate()
    print(json.dumps(result))
    if result.get("status") == "blocked":
        sys.exit(1)


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
