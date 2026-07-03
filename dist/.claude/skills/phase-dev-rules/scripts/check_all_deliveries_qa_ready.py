#!/usr/bin/env python3
"""
check_all_deliveries_qa_ready.py — Exit criterion: dev / all_deliveries_qa_ready.

Criterion met when:
  - At least one delivery artifact is found in task_completed events for the dev phase
  - Every delivery.md artifact contains the pattern: qa_ready: true

Artifact paths are resolved relative to ORCH_PROJECT_DIR (env var, default: ".").

Usage:
    python3 .claude/skills/phase-dev-rules/scripts/check_all_deliveries_qa_ready.py

Environment:
    ORCH_PROJECT_DIR  — project root used to resolve artifact paths (default: .)

Output schema (per GATE_SCHEMA_UNIFORMITY in specs/principles.md):
  Always emits {status, check, timestamp} for uniform gate consumption.
  Legacy fields {criterion, met, evidence} preserved for orchestrator-dev compatibility.

Output (exit 0 when met):
    {"status": "ok", "check": "all_deliveries_qa_ready", "timestamp": "<ISO8601>",
     "criterion": "all_deliveries_qa_ready", "met": true, "evidence": {...}}

Output (exit 1 when blocked or error):
    {"status": "blocked", "check": "all_deliveries_qa_ready", "timestamp": "<ISO8601>",
     "criterion": "all_deliveries_qa_ready", "met": false, "evidence": {...}}
    {"status": "error", "reason": "<code>", "detail": "<message>"}
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[3]
_LIB = _CLAUDE_DIR / "lib"
sys.path.insert(0, str(_LIB))

try:
    from orch_core import TaskStatus, reduce_all, scoped_phase_tasks
except ImportError as exc:
    print(json.dumps({
        "status": "error",
        "reason": "internal_error",
        "detail": f"cannot import orch_core: {exc}",
    }), file=sys.stderr)
    sys.exit(1)

CRITERION_ID = "all_deliveries_qa_ready"
PHASE_NAME = "dev"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))

_QA_READY_RE = re.compile(r"^\s*qa_ready\s*:\s*true\s*$", re.MULTILINE | re.IGNORECASE)
# M3: an explicit qa_ready: false anywhere blocks, even if a stray `true` (an example
# or prose) appears elsewhere — fail-closed against the first-match-wins gap.
_QA_NOT_READY_RE = re.compile(r"^\s*qa_ready\s*:\s*false\s*$", re.MULTILINE | re.IGNORECASE)


def _collect_delivery_paths(state) -> list[str]:
    """Returns artifact paths from completed dev-phase tasks.

    5-a: scoped to ORCH_WORKFLOW_ID when set — deliveries from another workflow
    in the shared log must not enter (or block) this workflow's gate."""
    paths: list[str] = []
    for task in scoped_phase_tasks(state, PHASE_NAME):
        if task.status != TaskStatus.COMPLETED:
            continue
        for artifact in task.artifacts:
            if "delivery" in Path(artifact).name.lower():
                paths.append(artifact)
    return paths


def evaluate() -> dict:
    state = reduce_all()
    delivery_paths = _collect_delivery_paths(state)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not delivery_paths:
        return {
            "status": "blocked",
            "check": CRITERION_ID,
            "timestamp": timestamp,
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {"total": 0, "ready": 0, "not_ready": []},
        }

    not_ready = []
    ready_count = 0

    for rel_path in delivery_paths:
        full_path = _PROJECT_DIR / rel_path
        if not full_path.exists():
            not_ready.append({"artifact": rel_path, "reason": "file_not_found"})
            continue
        try:
            content = full_path.read_text(encoding="utf-8")
        except OSError as exc:
            not_ready.append({"artifact": rel_path, "reason": f"unreadable: {exc}"})
            continue

        if _QA_NOT_READY_RE.search(content):
            not_ready.append({"artifact": rel_path, "reason": "qa_ready_false"})
        elif _QA_READY_RE.search(content):
            ready_count += 1
        else:
            not_ready.append({"artifact": rel_path, "reason": "qa_ready_not_true"})

    met = len(not_ready) == 0
    return {
        "status": "ok" if met else "blocked",
        "check": CRITERION_ID,
        "timestamp": timestamp,
        "criterion": CRITERION_ID,
        "met": met,
        "evidence": {
            "total": len(delivery_paths),
            "ready": ready_count,
            "not_ready": not_ready,
        },
    }


def main() -> None:
    result = evaluate()
    print(json.dumps(result))
    if result.get("status") == "blocked":
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
