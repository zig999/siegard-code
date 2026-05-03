#!/usr/bin/env python3
"""Exit criterion: no test report artifact contains severity: critical failures."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))

from orch_core import reduce_all, TaskStatus

CRITICAL_PATTERN = re.compile(r"severity\s*:\s*critical", re.IGNORECASE)


def _has_critical(path: str) -> bool:
    try:
        return bool(CRITICAL_PATTERN.search(open(path, encoding="utf-8").read()))
    except OSError:
        return False


def main() -> None:
    orch_dir = os.path.join(os.environ.get("ORCH_PROJECT_DIR", "."), ".orch")
    log_path = os.path.join(orch_dir, "log.jsonl")

    if not os.path.exists(log_path):
        print(json.dumps({"status": "error", "reason": "log_missing", "detail": log_path}))
        sys.exit(1)

    state = reduce_all()
    completed = [
        t for t in state.tasks.values()
        if t.phase == "test" and t.status == TaskStatus.COMPLETED and t.artifacts
    ]

    with_critical = []
    for task in completed:
        for artifact in task.artifacts:
            if _has_critical(artifact):
                with_critical.append({"task_id": task.task_id, "artifact": artifact})

    print(json.dumps({
        "criterion": "no_critical_failures",
        "met": len(with_critical) == 0,
        "evidence": {
            "total": len(completed),
            "clean": len(completed) - len(with_critical),
            "with_critical": with_critical,
        },
    }))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        sys.exit(1)
