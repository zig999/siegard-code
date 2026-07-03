#!/usr/bin/env python3
"""
check_all_tests_passed.py — Exit criterion: test / all_tests_passed.

Criterion met when:
  - At least one test report artifact exists from completed test-phase tasks
  - Every artifact contains result: passed

Artifact paths are resolved relative to ORCH_PROJECT_DIR (env var, default: ".").

Usage:
    python3 .claude/skills/phase-test-rules/scripts/check_all_tests_passed.py

Environment:
    ORCH_PROJECT_DIR  — project root used to resolve artifact paths (default: .)

Output (exit 0):
    {"criterion": "all_tests_passed", "met": bool, "evidence": {...}}

Output (exit 1, stderr):
    {"status": "error", "reason": "<code>", "detail": "<message>"}
"""
import json
import os
import re
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

CRITERION_ID = "all_tests_passed"
PHASE_NAME = "test"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))

_RESULT_RE = re.compile(r"^\s*result\s*:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
_PASSED_VALUE = "passed"


def evaluate() -> dict:
    state = reduce_all()
    # 5-a: scoped to ORCH_WORKFLOW_ID when set (shared-log isolation).
    all_completed = [
        t for t in scoped_phase_tasks(state, PHASE_NAME)
        if t.status == TaskStatus.COMPLETED
    ]

    if not all_completed:
        return {
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {"total": 0, "passed": 0, "failed": []},
        }

    # Tasks that completed without registering any artifact are blocking:
    # no evidence means the criterion cannot be satisfied, not vacuously passed.
    no_artifacts = [t.task_id for t in all_completed if not t.artifacts]
    if no_artifacts:
        return {
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {
                "total": len(all_completed),
                "passed": 0,
                "failed": [
                    {"task_id": tid, "result": "no_artifacts_registered"}
                    for tid in no_artifacts
                ],
            },
        }

    completed = all_completed
    failed = []
    passed_count = 0

    for task in completed:
        for rel_path in task.artifacts:
            full_path = _PROJECT_DIR / rel_path
            if not full_path.exists():
                failed.append({"task_id": task.task_id, "artifact": rel_path, "result": "file_not_found"})
                continue
            try:
                content = full_path.read_text(encoding="utf-8")
            except OSError as exc:
                failed.append({"task_id": task.task_id, "artifact": rel_path, "result": f"unreadable: {exc}"})
                continue

            match = _RESULT_RE.search(content)
            result_value = match.group(1).lower() if match else None

            if result_value == _PASSED_VALUE:
                passed_count += 1
            else:
                failed.append({
                    "task_id": task.task_id,
                    "artifact": rel_path,
                    "result": result_value or "field_absent",
                })

    return {
        "criterion": CRITERION_ID,
        "met": len(failed) == 0,
        "evidence": {
            "total": len(completed),
            "passed": passed_count,
            "failed": failed,
        },
    }


def main() -> None:
    result = evaluate()
    # task 10 (A4-F6, Option B): uniform gate schema — emit the full superset.
    result.setdefault("check", result.get("criterion"))
    result.setdefault("status", "ok" if result.get("met") else "blocked")
    result.setdefault("timestamp", now_iso())
    print(json.dumps(result))
    # M6: fail-closed exit so the gate is not prompt-trusted — parity with
    # check_all_test_tasks_terminal.py. Orchestrator-test reads the JSON; CI/operators
    # read the exit code, which must reflect a blocked criterion.
    if not result.get("met"):
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
