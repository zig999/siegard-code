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

# SIEGARD BUG-2: share the canonical verdict parser with read_qa_verdict.py so the
# gate and the helper never diverge. The script's own directory carries it.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    from orch_core import TaskStatus, reduce_all, now_iso, scoped_phase_tasks
    from read_qa_verdict import extract_verdict
except ImportError as exc:
    print(json.dumps({
        "status": "error",
        "reason": "internal_error",
        "detail": f"cannot import dependency: {exc}",
    }), file=sys.stderr)
    sys.exit(1)

CRITERION_ID = "all_qa_verdicts_approved"
PHASE_NAME = "review"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))


# SIEGARD BUG-2 (extension): only `qa`-type review tasks produce approved/rejected
# verdicts. Architecture and security reviewers are ALSO review-phase tasks, but emit
# findings under a different contract — architecture-finding.yaml has no `verdict`
# field at all, and security-finding.yaml's verdict enum is
# {approved, approved_with_remediations, blocked}. Collecting their artifacts here
# read them as "unknown" and blocked the phase with a spurious E08 even after a human
# approved (forensic report seq 69: "arch review YAML lacks verdict field"). Their
# severity is governed by check_no_open_critical_findings; the qa-verdict gate scopes
# to qa tasks only.
_QA_TASK_TYPE = "qa"


def _collect_completed_tasks(state) -> list:
    # 5-a: scoped to ORCH_WORKFLOW_ID when set — another workflow's QA verdicts
    # must not satisfy (or block) this workflow's approval gate.
    return [
        task for task in scoped_phase_tasks(state, PHASE_NAME)
        if task.status == TaskStatus.COMPLETED
        and task.task_type == _QA_TASK_TYPE
    ]


# fix F7: a QA task ID is `review_{dev_task_id}`, and a dev revision appends
# `_r{n}` (orchestrator-review Step "return_to_dev"), so a re-reviewed target
# yields `review_<base>` then `review_<base>_r1`. Both complete, so the gate used
# to still read the OLD (pre-revision, often rejected) verdict and block with a
# spurious E08. Group by the base target and keep only the latest revision — the
# earlier revision's delivery was replaced and no longer gates handoff.
_REV_SUFFIX_RE = re.compile(r"_r(\d+)$")
_ALL_REV_SUFFIXES_RE = re.compile(r"(?:_r\d+)+$")


def _target_and_revision(task_id: str) -> tuple[str, int]:
    """(base target, revision number). rev 0 when there is no `_r{n}` suffix.
    Nested suffixes (`_r1_r2`) collapse to the base; revision is the last number."""
    m = _REV_SUFFIX_RE.search(task_id)
    if not m:
        return task_id, 0
    base = _ALL_REV_SUFFIXES_RE.sub("", task_id)
    return base, int(m.group(1))


def _drop_superseded(tasks: list) -> tuple[list, list]:
    """Return (kept, superseded_ids). Within each base target, keep only the tasks
    at the highest revision; older revisions are superseded (not gating)."""
    max_rev: dict[str, int] = {}
    parsed = []
    for t in tasks:
        base, rev = _target_and_revision(t.task_id)
        parsed.append((t, base, rev))
        if rev > max_rev.get(base, -1):
            max_rev[base] = rev
    kept, superseded = [], []
    for t, base, rev in parsed:
        (kept if rev == max_rev[base] else superseded).append(t if rev == max_rev[base] else t.task_id)
    return kept, superseded


def evaluate() -> dict:
    state = reduce_all()
    all_completed = _collect_completed_tasks(state)
    completed_tasks, superseded_ids = _drop_superseded(all_completed)

    if not completed_tasks:
        return {
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {"total": 0, "approved": 0, "not_approved": [],
                         "superseded": superseded_ids},
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
                "superseded": superseded_ids,
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

        verdict_value = extract_verdict(content)
        if verdict_value == "approved":
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
