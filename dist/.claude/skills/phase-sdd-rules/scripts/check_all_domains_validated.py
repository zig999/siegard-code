#!/usr/bin/env python3
"""
check_all_domains_validated.py — Exit criterion: sdd / all_domains_validated.

Criterion met when:
  - SPECS_DIR/_validation/ exists and contains at least one in-scope file
  - No in-scope .yaml or .md file contains Status: INVALID

Scope (fix F1): with --workflow-id, an `/u-improve` restricts the check to the
domains the change actually touches (scope.py — derived from triage
affected_specs). Untouched domains inherit their last recorded verdict, so a
stale INVALID in an unrelated domain no longer blocks the change (the F3
symptom). For u-spec / greenfield / un-derivable scope, scope.py returns None
and the check stays global — every domain must be VALID (prior behavior).
Out-of-scope INVALID domains are reported as non-blocking evidence for audit.

Usage:
    python3 .claude/skills/phase-sdd-rules/scripts/check_all_domains_validated.py [--workflow-id <wid>]

Environment:
    ORCH_PROJECT_DIR  — project root (default: .)
    SPECS_DIR         — specs directory, relative to ORCH_PROJECT_DIR (default: specs)

Output (exit 0 when status=ok, exit 1 when status=blocked):
    {"status": "ok" | "blocked", "check": "all_domains_validated",
     "timestamp": "<ISO-8601>", "evidence": {...}}
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scope import affected_domains, domain_of_validation_file  # noqa: E402

CHECK_ID = "all_domains_validated"

_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_SPECS_DIR = _PROJECT_DIR / os.environ.get("SPECS_DIR", "specs")
_VALIDATION_DIR = _SPECS_DIR / "_validation"

_STATUS_RE = re.compile(r"^\s*[Ss]tatus\s*:\s*(\S+)", re.MULTILINE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate(workflow_id: str | None = None) -> dict:
    scope = affected_domains(_PROJECT_DIR, workflow_id) if workflow_id else None
    if not _VALIDATION_DIR.exists():
        return {
            "status": "blocked",
            "check": CHECK_ID,
            "criterion": CHECK_ID,
            "met": False,
            "timestamp": _now_iso(),
            "evidence": {
                "validation_dir": str(_VALIDATION_DIR),
                "exists": False,
                "total": 0,
                "passing": 0,
                "failing": [],
            },
        }

    all_files = sorted(_VALIDATION_DIR.glob("*.yaml")) + sorted(_VALIDATION_DIR.glob("*.md"))

    # Partition by change scope. scope is None → global (every file in scope,
    # prior behavior). A file whose domain is outside the scope is not gated;
    # a file with no domain prefix is always in scope (global report).
    in_scope, out_of_scope = [], []
    for f in all_files:
        dom = domain_of_validation_file(f.name)
        if scope is None or dom is None or dom in scope:
            in_scope.append(f)
        else:
            out_of_scope.append(f)

    scope_evidence = {
        "scoped": scope is not None,
        "scope_domains": sorted(scope) if scope is not None else None,
    }

    if not in_scope:
        return {
            "status": "blocked",
            "check": CHECK_ID,
            "criterion": CHECK_ID,
            "met": False,
            "timestamp": _now_iso(),
            "evidence": {
                "validation_dir": str(_VALIDATION_DIR),
                "exists": True,
                "total": 0,
                "passing": 0,
                "failing": [],
                "out_of_scope_invalid": [],
                **scope_evidence,
            },
        }

    def _status_of(f: Path) -> str | None:
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            return "UNREADABLE"
        match = _STATUS_RE.search(content)
        return match.group(1).upper() if match else None

    failing = []
    passing_count = 0
    for f in in_scope:
        sv = _status_of(f)
        if sv == "UNREADABLE":
            failing.append({"file": f.name, "reason": "unreadable"})
        elif sv == "INVALID":
            failing.append({"file": f.name, "status": "INVALID"})
        else:
            passing_count += 1

    # Out-of-scope INVALID domains are surfaced for audit but do NOT block —
    # they were not touched by this change (fix F1/F3).
    out_of_scope_invalid = [
        {"file": f.name, "status": "INVALID"}
        for f in out_of_scope
        if _status_of(f) == "INVALID"
    ]

    met = len(failing) == 0
    return {
        "status": "ok" if met else "blocked",
        "check": CHECK_ID,
        "criterion": CHECK_ID,
        "met": met,
        "timestamp": _now_iso(),
        "evidence": {
            "validation_dir": str(_VALIDATION_DIR),
            "exists": True,
            "total": len(in_scope),
            "passing": passing_count,
            "failing": failing,
            "out_of_scope_invalid": out_of_scope_invalid,
            **scope_evidence,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workflow-id", default=None)
    args = ap.parse_args()
    result = evaluate(args.workflow_id)
    print(json.dumps(result))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({
            "status": "blocked",
            "check": CHECK_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evidence": {"error": "internal_error", "detail": str(exc)},
        }), file=sys.stderr)
        sys.exit(1)
