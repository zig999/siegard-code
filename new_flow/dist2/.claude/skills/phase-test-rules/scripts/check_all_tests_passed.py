#!/usr/bin/env python3
"""Exit criterion: every test report artifact has result: passed."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))

from orch_core import reduce_all, TaskStatus

RESULT_PATTERN = re.compile(r"^\s*result\s*:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
PASSED_VALUE = "passed"


def _read_result(path: str) -> str | None:
    try:
        text = open(path, encoding="utf-8").read()
        match = RESULT_PATTERN.search(text)
        return match.group(1).lower() if match else None
    except OSError:
        return None


def main() -> None:
    orch_dir = os.path.join(os.environ.get("ORCH_PROJECT_DIR", "."), ".orch")
    log_path = os.path.join(orch_dir, "log.jsonl")

    if not os.path.exists(log_path):
        print(json.dumps({"status": "error", "reason": "log_missing", "detail": log_path}))
        sys.exit(1)

    state = reduce_all(log_path)
    completed = [
        t for t in state.tasks.values()
        if t.phase == "test" and t.status == TaskStatus.COMPLETED and t.artifacts
    ]

    if not completed:
        print(json.dumps({
            "criterion": "all_tests_passed",
            "met": False,
            "evidence": {"total": 0, "passed": 0, "failed": []},
        }))
        sys.exit(0)

    failed = []
    passed_count = 0
    for task in completed:
        for artifact in task.artifacts:
            result = _read_result(artifact)
            if result == PASSED_VALUE:
                passed_count += 1
            else:
                failed.append({
                    "task_id": task.task_id,
                    "artifact": artifact,
                    "result": result or "field_absent",
                })

    print(json.dumps({
        "criterion": "all_tests_passed",
        "met": len(failed) == 0,
        "evidence": {
            "total": len(completed),
            "passed": passed_count,
            "failed": failed,
        },
    }))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        sys.exit(1)
