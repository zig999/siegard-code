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

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from orch_core import TaskStatus, reduce_all, now_iso, scoped_phase_tasks
    # R14a: revision supersession is SHARED with check_all_qa_verdicts_approved,
    # not copied. See read_qa_verdict.py for why a third copy is the wrong fix.
    from read_qa_verdict import drop_superseded
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


# Only `qa`-type review tasks carry documentation_verified frontmatter.
# Architecture and security reviewers are review-phase tasks too, but emit
# findings under a different contract with no such field — reading them made this
# gate see `field_absent` and block. Mirrors check_all_qa_verdicts_approved.
_QA_TASK_TYPE = "qa"


def _collect_artifact_paths(state) -> tuple[list[str], list[str]]:
    """(artifact paths of the gating QA tasks, superseded task ids).

    R14a — three scoping rules, none of which this gate had:
      * workflow-scoped (5-a): another workflow's QA must not gate this one;
      * qa-type only: other reviewers have no documentation_verified field;
      * latest revision only (F7): after a return_to_dev, `review_<base>` and
        `review_<base>_r1` are both complete, and reading the superseded one —
        typically the rejected pre-revision artifact — blocked with a spurious
        E08.

    F7 landed in the sibling gate in v2.6.0 and was never ported here, so the
    defect stayed live for four minor versions and a downstream project
    hand-patched its own copy of this file.
    """
    completed = [
        task for task in scoped_phase_tasks(state, PHASE_NAME)
        if task.status == TaskStatus.COMPLETED
        and task.task_type == _QA_TASK_TYPE
    ]
    kept, superseded = drop_superseded(completed)
    paths: list[str] = []
    for task in kept:
        paths.extend(task.artifacts)
    return paths, superseded


def evaluate() -> dict:
    state = reduce_all()
    artifact_paths, superseded_ids = _collect_artifact_paths(state)

    if not artifact_paths:
        return {
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {
                "total": 0,
                "verified_true": 0,
                "verified_false": [],
                "field_absent": 0,
                "superseded": superseded_ids,
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
            # Named explicitly so an operator debugging a block can see which
            # artifacts were excluded as replaced, rather than wondering why a
            # completed QA task is not counted.
            "superseded": superseded_ids,
        },
    }


def main() -> None:
    result = evaluate()
    # task 10 (A4-F6, Option B): uniform gate schema — emit the full superset.
    result.setdefault("check", result.get("criterion"))
    result.setdefault("status", "ok" if result.get("met") else "blocked")
    result.setdefault("timestamp", now_iso())
    print(json.dumps(result))
    # R01b: fail-closed exit — the review phase's four criteria printed
    # `met: false` and exited 0, so any caller branching on the exit code read a
    # block as a pass. orchestrator-review compensated by reading the JSON, which
    # is exactly the prompt-trust that P7/P11 forbid; the test phase had the same
    # shape and emitted phase_exit_criterion_met over a blocked gate in production.
    # Parity with phase-test-rules/check_all_tests_passed.py (M6).
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
