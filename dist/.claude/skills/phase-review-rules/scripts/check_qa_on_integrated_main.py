#!/usr/bin/env python3
"""
check_qa_on_integrated_main.py — Review-phase ENTRY precondition: qa_runs_on_integrated_main.

SIEGARD-06. QA must run on the integrated head, not on an isolated per-TC branch.
Reviewing an isolated branch produces false positives: e.g. a TC branch that
references a symbol introduced by a later, stacked TC fails typecheck in
isolation but is correct on the integrated main. The dev phase (SIEGARD-04)
integrates all qa_ready work into the integration branch before handing off;
this guard confirms that happened before any QA task is dispatched.

Precondition met when, in the project repo:
  - HEAD is on the integration branch (default "main"), and
  - the working tree is clean, and
  - no TC branch (feat/TC-*, fix/TC-*, refactor/TC-*) remains UNMERGED into it.

This is an entry guard (run at review Step 1), not an exit criterion. If
blocked, the dev integration (SIEGARD-04) did not complete — the Orchestrator
must not dispatch QA against partial state.

Environment:
    ORCH_PROJECT_DIR   — project root / git repo (default: ".")
    ORCH_MAIN_BRANCH   — integration branch name (default: "main")

Output: {status, check, timestamp, criterion, met, evidence}. Exit 0 met, 1 otherwise.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CRITERION_ID = "qa_runs_on_integrated_main"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_MAIN = os.environ.get("ORCH_MAIN_BRANCH", "main")

_TC_BRANCH_RE = re.compile(r"^(?:feat|fix|refactor)/TC[-/]", re.IGNORECASE)


def _git(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(_PROJECT_DIR),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout.strip()


def _is_git_repo() -> bool:
    rc, out = _git(["rev-parse", "--is-inside-work-tree"])
    return rc == 0 and out == "true"


def evaluate() -> dict:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not _is_git_repo():
        return {
            "status": "error",
            "reason": "not_a_git_repo",
            "detail": f"{_PROJECT_DIR} is not inside a git work tree",
        }

    current_branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])[1]
    on_main = current_branch == _MAIN
    clean = _git(["status", "--porcelain"])[1] == ""

    rc_unmerged, unmerged_out = _git(["branch", "--no-merged", _MAIN, "--format=%(refname:short)"])
    unmerged_tc = []
    if rc_unmerged == 0:
        unmerged_tc = [b.strip() for b in unmerged_out.splitlines()
                       if _TC_BRANCH_RE.match(b.strip())]

    met = on_main and clean and not unmerged_tc
    return {
        "status": "ok" if met else "blocked",
        "check": CRITERION_ID,
        "timestamp": timestamp,
        "criterion": CRITERION_ID,
        "met": met,
        "evidence": {
            "integration_branch": _MAIN,
            "current_branch": current_branch,
            "on_integration_branch": on_main,
            "working_tree_clean": clean,
            "unmerged_tc_branches": unmerged_tc,
        },
    }


def main() -> None:
    result = evaluate()
    print(json.dumps(result))
    if result.get("status") != "ok":
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "error",
            "reason": "internal_error",
            "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
