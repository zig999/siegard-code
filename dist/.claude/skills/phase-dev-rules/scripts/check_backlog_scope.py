#!/usr/bin/env python3
"""
check_backlog_scope.py — post-planner backlog scope guard (fix L4).

On an `/u-improve` with `planner_required: true`, the planner receives the
handoff manifest — which enumerates EVERY on-disk domain — and only prose
hints about the change scope. Nothing deterministic prevented it from
generating Task Contracts for domains the change never touched, silently
re-broadening the exact scope that fixes F1/L1/L3 narrowed on the SDD side.

This guard closes that door: orchestrator-dev runs it after the planning task
completes and BEFORE creating any impl task. It derives the change scope from
triage (lib/spec_scope.py — the same single source the SDD gates use), scans
each Task Contract's file for `domains/<slug>/` references, and blocks the
backlog when any TC references ONLY out-of-scope domains.

Conservative attribution (mirrors every scope-aware gate):
  - scope is None (u-spec / greenfield / underivable) → trivially ok.
  - TC with NO domain references (front-only, infra, session-local paths)
    → allowed: cannot attribute, do not block.
  - TC referencing at least one in-scope domain → allowed (out-of-scope
    mentions alongside are context, e.g. an integration note).
  - TC whose references are ALL out-of-scope → violation.
  - TC file unreadable → allowed, but surfaced under `unreadable` evidence.

Usage:
    python3 .claude/skills/phase-dev-rules/scripts/check_backlog_scope.py \
        --backlog <session_dir>/backlog/backlog.json --workflow-id <wid>

Environment:
    ORCH_PROJECT_DIR  — project root (default: .)

Output (exit 0 when status=ok, exit 1 when status=blocked):
    {"status": "ok"|"blocked", "check": "backlog_scope", "scoped": bool,
     "scope_domains": [...]|null, "tcs_checked": N,
     "violations": [{"task_id", "tc_file", "out_of_scope_domains": [...]}],
     "unreadable": [...]}
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from spec_scope import affected_domains, domains_in_text  # noqa: E402

CHECK_ID = "backlog_scope"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result(status: str, **fields) -> dict:
    return {"status": status, "check": CHECK_ID, "timestamp": _now_iso(), **fields}


def evaluate(backlog_path: Path, workflow_id: str) -> dict:
    project_dir = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
    scope = affected_domains(project_dir, workflow_id)

    scope_evidence = {
        "scoped": scope is not None,
        "scope_domains": sorted(scope) if scope is not None else None,
    }

    if scope is None:
        # u-spec / greenfield / underivable — every domain is in scope.
        return _result("ok", tcs_checked=0, violations=[], unreadable=[],
                       **scope_evidence)

    try:
        backlog = json.loads(backlog_path.read_text(encoding="utf-8"))
        if not isinstance(backlog, list):
            raise ValueError("backlog is not a JSON array")
    except Exception as exc:  # noqa: BLE001 — planner artifact defect
        return _result(
            "blocked", reason="backlog_unreadable",
            detail={"path": str(backlog_path), "error": str(exc)},
            tcs_checked=0, violations=[], unreadable=[], **scope_evidence,
        )

    violations: list[dict] = []
    unreadable: list[str] = []
    for tc in backlog:
        if not isinstance(tc, dict):
            continue
        task_id = str(tc.get("task_id", "<missing task_id>"))
        tc_file = str(tc.get("spec", ""))
        # Scan the backlog entry itself plus the TC file body.
        text = json.dumps(tc)
        if tc_file:
            try:
                text += "\n" + (project_dir / tc_file).read_text(encoding="utf-8")
            except OSError:
                unreadable.append(tc_file)
        refs = domains_in_text(text)
        if refs and refs.isdisjoint(scope):
            violations.append({
                "task_id": task_id,
                "tc_file": tc_file,
                "out_of_scope_domains": sorted(refs),
            })

    met = len(violations) == 0
    return _result(
        "ok" if met else "blocked",
        tcs_checked=len(backlog),
        violations=violations,
        unreadable=unreadable,
        **scope_evidence,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backlog", required=True)
    ap.add_argument("--workflow-id", required=True)
    args = ap.parse_args()
    result = evaluate(Path(args.backlog), args.workflow_id)
    print(json.dumps(result))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "blocked", "check": CHECK_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evidence": {"error": "internal_error", "detail": str(exc)},
        }), file=sys.stderr)
        sys.exit(1)
