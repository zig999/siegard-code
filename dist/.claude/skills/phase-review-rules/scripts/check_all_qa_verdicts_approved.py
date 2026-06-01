#!/usr/bin/env python3
"""
check_all_qa_verdicts_approved.py — Exit criterion: review / all_qa_verdicts_approved.

Criterion met when:
  - At least one QA verdict artifact exists from completed review-phase tasks
  - Every verdict artifact contains verdict: approved

Artifact paths are resolved relative to ORCH_PROJECT_DIR (env var, default: ".").

Usage:
    python3 .claude/skills/phase-review-rules/scripts/check_all_qa_verdicts_approved.py

Environment:
    ORCH_PROJECT_DIR  — project root used to resolve artifact paths (default: .)

Output (exit 0):
    {"criterion": "all_qa_verdicts_approved", "met": bool, "evidence": {...}}

Output (exit 1):
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
    from orch_core import TaskStatus, reduce_all, now_iso
except ImportError as exc:
    print(json.dumps({
        "status": "error",
        "reason": "internal_error",
        "detail": f"cannot import orch_core: {exc}",
    }), file=sys.stderr)
    sys.exit(1)

CRITERION_ID = "all_qa_verdicts_approved"
PHASE_NAME = "review"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))

_VERDICT_RE = re.compile(r"^\s*verdict\s*:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
_APPROVED_VALUES = {"approved"}


def _collect_completed_tasks(state) -> list:
    return [
        task for task in state.tasks.values()
        if task.phase == PHASE_NAME and task.status == TaskStatus.COMPLETED
    ]


def evaluate() -> dict:
    state = reduce_all()
    completed_tasks = _collect_completed_tasks(state)

    if not completed_tasks:
        return {
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {"total": 0, "approved": 0, "not_approved": []},
        }

    # Tasks that completed without registering any artifact are blocking:
    # no evidence means the criterion cannot be satisfied, not vacuously passed.
    no_artifacts = [t.task_id for t in completed_tasks if not t.artifacts]
    if no_artifacts:
        return {
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {
                "total": len(completed_tasks),
                "approved": 0,
                "not_approved": [
                    {"artifact": tid, "reason": "no_artifacts_registered"}
                    for tid in no_artifacts
                ],
            },
        }

    artifact_paths: list[str] = []
    for task in completed_tasks:
        artifact_paths.extend(task.artifacts)

    not_approved = []
    approved_count = 0

    for rel_path in artifact_paths:
        full_path = _PROJECT_DIR / rel_path
        if not full_path.exists():
            not_approved.append({"artifact": rel_path, "reason": "file_not_found"})
            continue
        try:
            content = full_path.read_text(encoding="utf-8")
        except OSError as exc:
            not_approved.append({"artifact": rel_path, "reason": f"unreadable: {exc}"})
            continue

        match = _VERDICT_RE.search(content)
        verdict_value = match.group(1).lower() if match else None

        if verdict_value in _APPROVED_VALUES:
            approved_count += 1
        else:
            not_approved.append({
                "artifact": rel_path,
                "verdict_found": verdict_value,
                "reason": "verdict_not_approved",
            })

    return {
        "criterion": CRITERION_ID,
        "met": len(not_approved) == 0,
        "evidence": {
            "total": len(artifact_paths),
            "approved": approved_count,
            "not_approved": not_approved,
        },
    }


def main() -> None:
    result = evaluate()
    # task 10 (A4-F6, Option B): uniform gate schema — emit the full superset.
    result.setdefault("check", result.get("criterion"))
    result.setdefault("status", "ok" if result.get("met") else "blocked")
    result.setdefault("timestamp", now_iso())
    print(json.dumps(result))


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
