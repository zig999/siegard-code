#!/usr/bin/env python3
"""
check_no_critical_failures.py — Exit criterion: test / no_critical_failures.

Criterion met when:
  - No test report artifact from completed test-phase tasks contains "severity: critical".

Artifact paths are resolved relative to ORCH_PROJECT_DIR (env var, default: ".").

Usage:
    python3 .claude/skills/phase-test-rules/scripts/check_no_critical_failures.py

Environment:
    ORCH_PROJECT_DIR  — project root used to resolve artifact paths (default: .)

Output (exit 0):
    {"criterion": "no_critical_failures", "met": bool, "evidence": {...}}

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

CRITERION_ID = "no_critical_failures"
PHASE_NAME = "test"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))

_CRITICAL_RE = re.compile(r"^\s*severity\s*:\s*critical\s*$", re.MULTILINE | re.IGNORECASE)


def evaluate() -> dict:
    state = reduce_all()
    # 5-a: scoped to ORCH_WORKFLOW_ID when set (shared-log isolation).
    completed = [
        t for t in scoped_phase_tasks(state, PHASE_NAME)
        if t.status == TaskStatus.COMPLETED and t.artifacts
    ]

    with_critical = []
    clean_count = 0

    for task in completed:
        for rel_path in task.artifacts:
            full_path = _PROJECT_DIR / rel_path
            if not full_path.exists():
                with_critical.append({"task_id": task.task_id, "artifact": rel_path, "reason": "file_not_found"})
                continue
            try:
                content = full_path.read_text(encoding="utf-8")
            except OSError as exc:
                with_critical.append({"task_id": task.task_id, "artifact": rel_path, "reason": f"unreadable: {exc}"})
                continue

            if _CRITICAL_RE.search(content):
                with_critical.append({"task_id": task.task_id, "artifact": rel_path, "reason": "critical_failure_present"})
            else:
                clean_count += 1

    return {
        "criterion": CRITERION_ID,
        "met": len(with_critical) == 0,
        "evidence": {
            "total": len(completed),
            "clean": clean_count,
            "with_critical": with_critical,
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
    # check_all_test_tasks_terminal.py.
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
