#!/usr/bin/env python3
"""
check_documentation_verified.py — Exit criterion: review / documentation_verified.

Criterion met when:
  - At least one QA verdict artifact contains "documentation_verified: true"
  - No artifact contains "documentation_verified: false"

Not met if no QA artifacts exist or none contains the documentation_verified field.

Artifact paths are resolved relative to ORCH_PROJECT_DIR (env var, default: ".").

Usage:
    python3 .claude/skills/phase-review-rules/scripts/check_documentation_verified.py

Environment:
    ORCH_PROJECT_DIR  — project root used to resolve artifact paths (default: .)

Output (exit 0):
    {"criterion": "documentation_verified", "met": bool, "evidence": {...}}

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

CRITERION_ID = "documentation_verified"
PHASE_NAME = "review"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))

_DOC_VERIFIED_RE = re.compile(
    r"^\s*documentation_verified\s*:\s*(true|false)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


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
            "evidence": {
                "total": 0,
                "verified_true": 0,
                "verified_false": [],
                "field_absent": 0,
            },
        }

    verified_true_count = 0
    verified_false = []
    field_absent_count = 0

    for rel_path in artifact_paths:
        full_path = _PROJECT_DIR / rel_path
        if not full_path.exists():
            verified_false.append({"artifact": rel_path, "reason": "file_not_found"})
            continue
        try:
            content = full_path.read_text(encoding="utf-8")
        except OSError as exc:
            verified_false.append({"artifact": rel_path, "reason": f"unreadable: {exc}"})
            continue

        match = _DOC_VERIFIED_RE.search(content)
        if match is None:
            field_absent_count += 1
        elif match.group(1).lower() == "true":
            verified_true_count += 1
        else:
            verified_false.append({
                "artifact": rel_path,
                "reason": "documentation_verified_false",
            })

    met = verified_true_count >= 1 and len(verified_false) == 0

    return {
        "criterion": CRITERION_ID,
        "met": met,
        "evidence": {
            "total": len(artifact_paths),
            "verified_true": verified_true_count,
            "verified_false": verified_false,
            "field_absent": field_absent_count,
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
