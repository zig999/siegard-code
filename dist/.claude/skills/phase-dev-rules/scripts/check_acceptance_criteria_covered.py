#!/usr/bin/env python3
"""
check_acceptance_criteria_covered.py — Exit criterion: dev / acceptance_criteria_covered.

Rec #11 (lighter form — no new AC-ID convention). Independent gate over the
delivery-gate `acceptance_criteria` block of every completed dev task: surfaces
coverage gaps at the END OF DEV instead of letting them slip silently into review
(where they would only be caught as QA Quality BUGs, one round later and more
expensive to fix). This does not trust the dev's self-declaration to be acted on
downstream — it blocks the dev→review transition while any gap remains.

Criterion met when, for every completed dev task's delivery.md:
  - a delivery-gate `acceptance_criteria` block is present, AND
  - its `uncovered` list is empty, AND
  - `covered == total`.

Artifact paths are resolved relative to ORCH_PROJECT_DIR (env var, default: ".").

Output schema (per GATE_SCHEMA_UNIFORMITY): always {status, check, timestamp};
legacy {criterion, met, evidence} preserved for orchestrator-dev compatibility.
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

CRITERION_ID = "acceptance_criteria_covered"
PHASE_NAME = "dev"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))

# Capture the acceptance_criteria block: from its column-0 key to the next
# column-0 line (next gate key, or the closing fence / markdown body).
_AC_BLOCK_RE = re.compile(r"(?ms)^acceptance_criteria:[ \t]*\n(.*?)(?=^\S|\Z)")
_TOTAL_RE = re.compile(r"^\s+total:\s*(\d+)", re.MULTILINE)
_COVERED_RE = re.compile(r"^\s+covered:\s*(\d+)", re.MULTILINE)
# An uncovered list item: `uncovered:` followed (after optional comment/blank
# lines) by an indented `- <something>`.
_UNCOVERED_ITEM_RE = re.compile(
    r"uncovered\s*:\s*(?:#[^\n]*)?\n(?:\s*(?:#[^\n]*)?\n)*\s+-\s+\S",
    re.MULTILINE,
)


def _collect_delivery_paths(state) -> list[str]:
    paths: list[str] = []
    for task in state.tasks.values():
        if task.phase != PHASE_NAME or task.status != TaskStatus.COMPLETED:
            continue
        for artifact in task.artifacts:
            if "delivery" in Path(artifact).name.lower():
                paths.append(artifact)
    return paths


def _inspect(content: str) -> dict | None:
    """Returns a violation dict for this delivery, or None when fully covered."""
    block_match = _AC_BLOCK_RE.search(content)
    if not block_match:
        return {"reason": "ac_block_missing"}
    block = block_match.group(1)

    if _UNCOVERED_ITEM_RE.search(block):
        return {"reason": "uncovered_criteria_present"}

    total_m = _TOTAL_RE.search(block)
    covered_m = _COVERED_RE.search(block)
    if total_m and covered_m:
        total, covered = int(total_m.group(1)), int(covered_m.group(1))
        if covered < total:
            return {"reason": "covered_less_than_total", "covered": covered, "total": total}
    return None


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
        v = _inspect(content)
        if v:
            violations.append({"artifact": rel_path, **v})
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
            "fully_covered": clean_count,
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
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "error",
            "reason": "internal_error",
            "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
