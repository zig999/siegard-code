#!/usr/bin/env python3
"""
check_{criterion_name}.py — Exit criterion checker (example).

Rename this file to check_{criterion_name}.py and replace the logic below.

Each checker is independent, stateless, and has no side effects.
It reads the orchestration log via orch_core and returns a verdict.

Usage:
    python3 scripts/check_{criterion_name}.py

Output (exit 0):
    {
      "criterion": "{criterion_name}",
      "met": true,
      "evidence": {"total": N, "passing": N, "failing": []}
    }

Output (exit 1):
    {"status": "error", "reason": "<code>", "detail": "<message>"}
"""
import json
import os
import sys
from pathlib import Path

# Resolve orch_core from the shared lib directory.
_ORCH_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
sys.path.insert(0, str(_ORCH_PROJECT_DIR / ".claude" / "lib"))

try:
    from orch_core import reduce_all, TaskStatus
except ImportError as exc:
    print(json.dumps({
        "status": "error",
        "reason": "internal_error",
        "detail": f"cannot import orch_core: {exc}",
    }), file=sys.stderr)
    sys.exit(1)


CRITERION_ID = "{criterion_name}"
PHASE_NAME = "{name}"


def evaluate() -> dict:
    """
    Replace this function body with the actual criterion logic.

    Example below checks that all tasks in the phase have reached a terminal status.
    """
    state = reduce_all()

    phase_tasks = [t for t in state.tasks.values() if t.phase == PHASE_NAME]
    terminal = {TaskStatus.COMPLETED, TaskStatus.DLQ}

    passing = [t.task_id for t in phase_tasks if t.status in terminal]
    failing = [t.task_id for t in phase_tasks if t.status not in terminal]

    return {
        "criterion": CRITERION_ID,
        "met": len(failing) == 0 and len(phase_tasks) > 0,
        "evidence": {
            "total": len(phase_tasks),
            "passing": len(passing),
            "failing": failing,
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
