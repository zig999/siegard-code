#!/usr/bin/env python3
"""Exit criterion: all test-phase tasks are in a terminal status (completed or dlq)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))

from orch_core import reduce_all, TaskStatus

TERMINAL = {TaskStatus.COMPLETED, TaskStatus.DLQ}


def main() -> None:
    orch_dir = os.path.join(os.environ.get("ORCH_PROJECT_DIR", "."), ".orch")
    log_path = os.path.join(orch_dir, "log.jsonl")

    if not os.path.exists(log_path):
        print(json.dumps({"status": "error", "reason": "log_missing", "detail": log_path}))
        sys.exit(1)

    state = reduce_all()
    test_tasks = [t for t in state.tasks.values() if t.phase == "test"]

    if not test_tasks:
        print(json.dumps({
            "criterion": "all_test_tasks_terminal",
            "met": False,
            "evidence": {"total": 0, "terminal": 0, "non_terminal": []},
        }))
        sys.exit(0)

    non_terminal = [t.task_id for t in test_tasks if t.status not in TERMINAL]

    print(json.dumps({
        "criterion": "all_test_tasks_terminal",
        "met": len(non_terminal) == 0,
        "evidence": {
            "total": len(test_tasks),
            "terminal": len(test_tasks) - len(non_terminal),
            "non_terminal": non_terminal,
        },
    }))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        sys.exit(1)
