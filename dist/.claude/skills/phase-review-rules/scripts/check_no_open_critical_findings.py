#!/usr/bin/env python3
"""
check_no_open_critical_findings.py — Exit criterion: review / no_open_critical_findings.

Criterion met when:
  - No completed review-phase artifact contains a critical-equivalent severity.

A critical finding is detected when the file contains, on its own line (case-insensitive):
  severity: critical   (QA / security artifacts — named scale)
  severity: P0         (architecture artifacts — P0/P1/P2 scale; P0 "blocks
                        architectural integrity" and is the critical-equivalent)
Matching both scales lets this one gate govern the highest-severity finding from QA,
security, AND architecture reviewers (A1 / SIEGARD code review).

Artifact paths are resolved relative to ORCH_PROJECT_DIR (env var, default: ".").

Usage:
    python3 .claude/skills/phase-review-rules/scripts/check_no_open_critical_findings.py

Environment:
    ORCH_PROJECT_DIR  — project root used to resolve artifact paths (default: .)

Output (exit 0):
    {"criterion": "no_open_critical_findings", "met": bool, "evidence": {...}}

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

CRITERION_ID = "no_open_critical_findings"
PHASE_NAME = "review"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))

# A1: `critical` (named scale) OR `P0` (architecture P0/P1/P2 scale). The $-anchor keeps
# the match to a bare value, so `severity: P1` / `severity: high` do not trip the gate.
_CRITICAL_RE = re.compile(r"^\s*severity\s*:\s*(?:critical|p0)\s*$", re.MULTILINE | re.IGNORECASE)


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

    with_critical = []
    clean_count = 0

    for rel_path in artifact_paths:
        full_path = _PROJECT_DIR / rel_path
        if not full_path.exists():
            with_critical.append({"artifact": rel_path, "reason": "file_not_found"})
            continue
        try:
            content = full_path.read_text(encoding="utf-8")
        except OSError as exc:
            with_critical.append({"artifact": rel_path, "reason": f"unreadable: {exc}"})
            continue

        if _CRITICAL_RE.search(content):
            with_critical.append({"artifact": rel_path, "reason": "critical_finding_present"})
        else:
            clean_count += 1

    return {
        "criterion": CRITERION_ID,
        "met": len(with_critical) == 0,
        "evidence": {
            "total": len(artifact_paths),
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
