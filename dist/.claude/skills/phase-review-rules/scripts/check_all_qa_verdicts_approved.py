#!/usr/bin/env python3
"""
check_all_qa_verdicts_approved.py — Exit criterion: review / all_qa_verdicts_approved.

Criterion met when:
  - At least one QA verdict artifact exists from completed review-phase tasks
  - Every verdict artifact contains verdict: approved or verdict: approved_with_reservations

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
    from orch_core import TaskStatus, reduce_all
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
_APPROVED_VALUES = {"approved", "approved_with_reservations"}


def _collect_artifact_paths(state) -> list[str]:
    paths: list[str] = []
    for task in state.tasks.values():
        if task.phase != PHASE_NAME or task.status != TaskStatus.COMPLETED:
            continue
        paths.extend(task.artifacts)
    return paths


def evaluate() -> dict:
    state = reduce_all()
    artifact_paths = _collect_artifact_paths(state)

    if not artifact_paths:
        return {
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {"total": 0, "approved": 0, "not_approved": []},
        }

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
