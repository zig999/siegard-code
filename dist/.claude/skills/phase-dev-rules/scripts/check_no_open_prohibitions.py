#!/usr/bin/env python3
"""
check_no_open_prohibitions.py — Exit criterion: dev / no_open_prohibitions.

Criterion met when:
  - No delivery.md artifact from completed dev tasks contains a non-empty
    prohibition_violations list.

A violation is present when the file contains "prohibition_violations:" followed by
at least one list item ("- " on the next non-blank line).

Artifact paths are resolved relative to ORCH_PROJECT_DIR (env var, default: ".").

Usage:
    python3 .claude/skills/phase-dev-rules/scripts/check_no_open_prohibitions.py

Environment:
    ORCH_PROJECT_DIR  — project root used to resolve artifact paths (default: .)

Output schema (per GATE_SCHEMA_UNIFORMITY in specs/principles.md):
  Always emits {status, check, timestamp} for uniform gate consumption.
  Legacy fields {criterion, met, evidence} preserved for orchestrator-dev compatibility.

Output (exit 0 when met):
    {"status": "ok", "check": "no_open_prohibitions", "timestamp": "<ISO8601>",
     "criterion": "no_open_prohibitions", "met": true, "evidence": {...}}

Output (exit 1 when blocked or error):
    {"status": "blocked", "check": "no_open_prohibitions", "timestamp": "<ISO8601>",
     "criterion": "no_open_prohibitions", "met": false, "evidence": {...}}
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
    from orch_core import TaskStatus, reduce_all
except ImportError as exc:
    print(json.dumps({
        "status": "error",
        "reason": "internal_error",
        "detail": f"cannot import orch_core: {exc}",
    }), file=sys.stderr)
    sys.exit(1)

CRITERION_ID = "no_open_prohibitions"
PHASE_NAME = "dev"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))

# Matches "prohibition_violations:" followed by a list item. M1: the gap between the
# key and the first "- " item may contain blank AND comment-only lines. [ \t] (not \s)
# avoids newline-overlap, which previously let a commented violation read as clean.
_VIOLATIONS_RE = re.compile(
    r"prohibition_violations[ \t]*:[ \t]*\n"   # the key line
    r"(?:[ \t]*(?:#[^\n]*)?\n)*"                # blank or comment-only lines
    r"[ \t]*-\s+\S",                            # first list item
    re.MULTILINE,
)


def _collect_delivery_paths(state) -> list[str]:
    paths: list[str] = []
    for task in state.tasks.values():
        if task.phase != PHASE_NAME:
            continue
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

    violations: list[dict] = []
    clean_count = 0

    for rel_path in delivery_paths:
        full_path = _PROJECT_DIR / rel_path
        if not full_path.exists():
            violations.append({"artifact": rel_path, "reason": "file_not_found"})
            continue
        try:
            content = full_path.read_text(encoding="utf-8")
        except OSError as exc:
            violations.append({"artifact": rel_path, "reason": f"unreadable: {exc}"})
            continue

        if _VIOLATIONS_RE.search(content):
            violations.append({"artifact": rel_path, "reason": "prohibition_violations_present"})
        else:
            clean_count += 1

    met = len(violations) == 0
    return {
        "status": "ok" if met else "blocked",
        "check": CRITERION_ID,
        "timestamp": timestamp,
        "criterion": CRITERION_ID,
        "met": met,
        "evidence": {
            "total": len(delivery_paths),
            "clean": clean_count,
            "violations": violations,
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
