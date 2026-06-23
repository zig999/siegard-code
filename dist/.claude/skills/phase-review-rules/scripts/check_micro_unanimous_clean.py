#!/usr/bin/env python3
"""
check_micro_unanimous_clean.py — Auto-approval gate for the review phase.

Determines whether the orchestrator may auto-approve the review phase without
the human gate. Strict criteria — failure on ANY single rule disqualifies:

  R1  At least one completed review task exists.
  R2  Every completed review task has qa_mode == "micro".
  R3  Every QA verdict artifact reads `verdict: approved`.
  R4  No verdict artifact contains a finding with severity in {medium, high, critical}.

Severity is parsed by scanning each artifact for lines matching
`severity: <value>` (case-insensitive; YAML frontmatter or body). The maximum
severity wins.

Usage:
    python3 check_micro_unanimous_clean.py \
      --project-dir <abs path> \
      --tasks '<JSON list: [{"task_id":"...","qa_mode":"micro","verdict_path":"..."}, ...]>'

Output (stdout; exit 0 if qualifies, exit 2 if disqualified):
    {
      "qualifies": bool,
      "evidence": {
        "total_review_tasks": int,
        "all_micro": bool,
        "all_approved": bool,
        "max_finding_severity": "none"|"low"|"medium"|"high"|"critical",
        "non_micro_tasks": [...],
        "non_approved_tasks": [...],
        "tasks_with_blocking_findings": [...]
      },
      "rationale": "<one-line outcome>"
    }

Output (exit 1, stderr):
    {"status": "error", "reason": "<code>", "detail": "..."}
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

# SIEGARD BUG-2: share the canonical verdict parser with read_qa_verdict.py so this
# auto-approval gate and the exit-criteria gate can never disagree on the same
# artifact. The script's own directory carries the helper module.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from read_qa_verdict import extract_verdict  # noqa: E402


_SEVERITY_RE = re.compile(r"^\s*-?\s*severity\s*:\s*[\"']?(critical|high|medium|low)\b",
                          re.MULTILINE | re.IGNORECASE)

_SEVERITY_RANK = {
    "none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4,
}
_RANK_TO_NAME = {v: k for k, v in _SEVERITY_RANK.items()}

_BLOCKING_RANK = _SEVERITY_RANK["medium"]


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _max_severity(content: str) -> str:
    """Highest severity name found in the artifact, or 'none' if none."""
    best_rank = 0
    for m in _SEVERITY_RE.finditer(content):
        rank = _SEVERITY_RANK.get(m.group(1).lower(), 0)
        if rank > best_rank:
            best_rank = rank
    return _RANK_TO_NAME[best_rank]


def evaluate(tasks: list[dict], project_dir: Path) -> dict:
    total = len(tasks)
    if total == 0:
        return {
            "qualifies": False,
            "evidence": {
                "total_review_tasks": 0,
                "all_micro": False,
                "all_approved": False,
                "max_finding_severity": "none",
                "non_micro_tasks": [],
                "non_approved_tasks": [],
                "tasks_with_blocking_findings": [],
            },
            "rationale": "no completed review tasks — nothing to auto-approve",
        }

    non_micro = [t["task_id"] for t in tasks if t.get("qa_mode") != "micro"]
    all_micro = not non_micro

    non_approved: list[dict] = []
    blocking: list[dict] = []
    overall_max_rank = 0

    for t in tasks:
        verdict_path = t.get("verdict_path", "")
        full = project_dir / verdict_path if verdict_path else None
        content = _read_text(full) if full else None

        if content is None:
            non_approved.append({"task_id": t["task_id"], "reason": "verdict_artifact_missing"})
            continue

        verdict = extract_verdict(content)
        if verdict != "approved":
            non_approved.append({"task_id": t["task_id"], "verdict": verdict})

        sev = _max_severity(content)
        sev_rank = _SEVERITY_RANK[sev]
        if sev_rank > overall_max_rank:
            overall_max_rank = sev_rank
        if sev_rank >= _BLOCKING_RANK:
            blocking.append({"task_id": t["task_id"], "max_severity": sev})

    all_approved = not non_approved
    max_severity_name = _RANK_TO_NAME[overall_max_rank]

    qualifies = (
        all_micro
        and all_approved
        and overall_max_rank < _BLOCKING_RANK
    )

    rationale_bits = []
    if not all_micro:
        rationale_bits.append(f"non_micro={len(non_micro)}")
    if not all_approved:
        rationale_bits.append(f"non_approved={len(non_approved)}")
    if overall_max_rank >= _BLOCKING_RANK:
        rationale_bits.append(f"blocking_findings={len(blocking)} (max={max_severity_name})")

    if qualifies:
        rationale = (
            f"qualifies: {total} task(s) all micro, all approved, "
            f"max severity={max_severity_name}"
        )
    else:
        rationale = "disqualified: " + ", ".join(rationale_bits)

    return {
        "qualifies": qualifies,
        "evidence": {
            "total_review_tasks": total,
            "all_micro": all_micro,
            "all_approved": all_approved,
            "max_finding_severity": max_severity_name,
            "non_micro_tasks": non_micro,
            "non_approved_tasks": non_approved,
            "tasks_with_blocking_findings": blocking,
        },
        "rationale": rationale,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", default=os.environ.get("ORCH_PROJECT_DIR", "."))
    ap.add_argument("--tasks", required=True,
                    help='JSON list: [{"task_id":"...","qa_mode":"micro","verdict_path":"..."}]')
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    try:
        tasks = json.loads(args.tasks)
        if not isinstance(tasks, list):
            raise ValueError("tasks must be a JSON list")
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "status": "error", "reason": "bad_tasks", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)

    result = evaluate(tasks, project_dir)
    print(json.dumps(result))
    # prod-hardening task 02 (C2/A4-F2): the exit code carries the verdict so the
    # review orchestrator gates the synthesized human approval on it — exit 0 only
    # when qualifies, exit 2 when disqualified (1 is reserved for bad input/error).
    sys.exit(0 if result["qualifies"] else 2)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
