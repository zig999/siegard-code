#!/usr/bin/env python3
"""
check_sdd_artifacts_committed.py — Exit criterion: sdd / sdd_artifacts_committed.

SIEGARD-05. The SDD phase produces spec artifacts (openapi.yaml, *.spec.md,
*.back.md, component specs, *-validation files, error-codes.md, the
handoff-manifest itself). Historically no phase committed them, so they stayed
untracked and could be lost. This criterion blocks the dev handoff until every
artifact listed in the handoff-manifest is committed to git.

Criterion met when, in the project repo:
  - handoff-manifest.yaml exists, and
  - every artifact path it lists (backend_package / frontend_package `path:`,
    domain `compliance_report:`, feature/flow `path:`) is git-tracked, and
  - none of those paths has uncommitted changes (`git status --porcelain` clean
    for each path).

Environment:
    ORCH_PROJECT_DIR   — project root / git repo (default: ".")
    SPECS_DIR          — specs dir relative to project root (default: "specs")

Output schema (per GATE_SCHEMA_UNIFORMITY): always {status, check, timestamp};
legacy {criterion, met, evidence} preserved for orchestrator-sdd compatibility.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CRITERION_ID = "sdd_artifacts_committed"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_SPECS_DIR = _PROJECT_DIR / os.environ.get("SPECS_DIR", "specs")
_MANIFEST_FILE = _SPECS_DIR / "handoff-manifest.yaml"

# Captures the value of `path:` and `compliance_report:` lines (list item or mapping).
_ARTIFACT_RE = re.compile(r"^\s*-?\s*(?:path|compliance_report)\s*:\s*(\S+)\s*$", re.MULTILINE)


def _git(args: list[str]) -> tuple[int, str]:
    # M2: bound the call and surface failures — a timeout/exec error returns rc=1 so
    # callers fail closed instead of reading empty stdout as "clean".
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(_PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 1, ""
    return proc.returncode, proc.stdout.strip()


def _is_git_repo() -> bool:
    rc, out = _git(["rev-parse", "--is-inside-work-tree"])
    return rc == 0 and out == "true"


def _manifest_artifact_paths() -> list[str]:
    text = _MANIFEST_FILE.read_text(encoding="utf-8")
    paths: list[str] = []
    seen: set[str] = set()
    for value in _ARTIFACT_RE.findall(text):
        # Skip template placeholders (<relative-path>) and quoted empties.
        if "<" in value or ">" in value:
            continue
        v = value.strip().strip('"').strip("'")
        if v and v not in seen:
            seen.add(v)
            paths.append(v)
    return paths


def evaluate() -> dict:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not _is_git_repo():
        return {
            "status": "error",
            "reason": "not_a_git_repo",
            "detail": f"{_PROJECT_DIR} is not inside a git work tree",
        }
    if not _MANIFEST_FILE.exists():
        return {
            "status": "blocked",
            "check": CRITERION_ID,
            "timestamp": timestamp,
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {"reason": "manifest_missing", "manifest": str(_MANIFEST_FILE)},
        }

    artifacts = _manifest_artifact_paths()
    untracked: list[str] = []
    uncommitted: list[str] = []
    committed = 0

    for rel in artifacts:
        rc_tracked, _ = _git(["ls-files", "--error-unmatch", rel])
        if rc_tracked != 0:
            untracked.append(rel)
            continue
        # M2: a failed status read must fail closed (treat as uncommitted), not be
        # mistaken for a clean tree because stdout came back empty.
        rc_status, dirty = _git(["status", "--porcelain", "--", rel])
        if rc_status != 0 or dirty:
            uncommitted.append(rel)
        else:
            committed += 1

    met = not untracked and not uncommitted
    return {
        "status": "ok" if met else "blocked",
        "check": CRITERION_ID,
        "timestamp": timestamp,
        "criterion": CRITERION_ID,
        "met": met,
        "evidence": {
            "total_artifacts": len(artifacts),
            "committed": committed,
            "untracked": untracked,
            "uncommitted_changes": uncommitted,
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
