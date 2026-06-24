#!/usr/bin/env python3
"""
classify_run_status.py — Rec B: distinguish "halt for human" from "genuine failure".

The field analysis found that operators read a stopped workflow as "it failed" when
in many cases the run is simply at a NORMAL human-decision gate (E99 approval/confirm)
or the stop is one root failure that cascaded into many DLQ entries. This conflation
inflates the perceived failure rate. This tool reads the event log and reports, in one
place, WHY a run is at rest:

  - run_status:
      awaiting_human  — active escalation is an E99 gate (or a pending human-input
                        gate). The run is waiting on YOU; nothing is broken.
      failed          — active escalation is a genuine critical failure (E04/E05/E06/
                        E07/E10/E11/E12/E13/E20/E21). Something broke; act on it.
      needs_review    — active escalation is a warning (E08/E09/E19).
      no_pending_escalation — no unresolved escalation; run is running/complete.
  - dlq: failed tasks split into ROOTS (true failures) vs CASCADED (failed only
         because a dependency was in DLQ — `cascade_from_dep`). Fixing the roots
         usually clears the cascade, so "12 DLQ tasks" is often "1 root + 11 cascade".

Classification is by escalation SEVERITY + the E99 special-case, so new codes are
handled without editing this script.

Usage:
    python3 .claude/scripts/classify_run_status.py [--project-dir <dir>]

Output (exit 0): a JSON object (see keys above). Exit 1 on internal error.
"""
import argparse
import json
import os
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[1]
_LIB = _CLAUDE_DIR / "lib"
sys.path.insert(0, str(_LIB))

try:
    from orch_core import read_events, reduce_all, TaskStatus
except ImportError as exc:
    print(json.dumps({"status": "error", "reason": "internal_error",
                      "detail": f"cannot import orch_core: {exc}"}), file=sys.stderr)
    sys.exit(1)

_CASCADE_REASON = "cascade_from_dep"


def _classify(code: str, severity: str) -> str:
    code = code or ""
    severity = (severity or "").lower()
    if code.startswith("E99"):
        return "awaiting_human"
    if severity == "critical":
        return "failed"
    if severity == "warning":
        return "needs_review"
    return "info"


def _scan_log():
    """Single pass over the log. Returns (escalations, resolved_seqs, dlq_reasons).

    dlq_reasons maps task_id -> reason from its task_dlq event — the authoritative
    DLQ reason. (The reducer does NOT copy this onto TaskState.last_failure_reason,
    and cascade DLQ has no prior task_failed, so reading the event is required to
    tell a cascaded task from a true root failure.)
    """
    escalations = []
    resolved = set()
    dlq_reasons: dict[str, str] = {}
    for ev in read_events():
        if ev.event_type == "escalation":
            d = ev.data or {}
            code = d.get("code", "")
            severity = d.get("severity", "")
            escalations.append({
                "seq": ev.seq,
                "code": code,
                "severity": severity,
                "reason": d.get("reason", ""),
                "class": _classify(code, severity),
                "suggested_actions": d.get("suggested_actions", []),
            })
        elif ev.event_type == "human_response":
            tgt = (ev.data or {}).get("escalation_seq")
            if tgt is not None:
                resolved.add(tgt)
        elif ev.event_type == "task_dlq" and ev.task_id:
            dlq_reasons[ev.task_id] = (ev.data or {}).get("reason") or "unknown"
    return escalations, resolved, dlq_reasons


def _dlq_summary(state, dlq_reasons: dict) -> dict:
    roots, cascaded = [], []
    by_reason: dict[str, int] = {}
    for task in state.tasks.values():
        if task.status != TaskStatus.DLQ:
            continue
        reason = dlq_reasons.get(task.task_id) or getattr(task, "last_failure_reason", None) or "unknown"
        by_reason[reason] = by_reason.get(reason, 0) + 1
        entry = {"task_id": task.task_id, "phase": task.phase, "reason": reason}
        (cascaded if reason == _CASCADE_REASON else roots).append(entry)
    return {
        "total": len(roots) + len(cascaded),
        "roots": roots,            # true failures — fix these first
        "cascaded": cascaded,      # failed only because a dep was in DLQ
        "by_reason": by_reason,
    }


def evaluate(project_dir: str) -> dict:
    os.environ["ORCH_PROJECT_DIR"] = project_dir
    state = reduce_all()
    escalations, resolved, dlq_reasons = _scan_log()

    active = None
    for esc in reversed(escalations):
        if esc["seq"] not in resolved:
            active = esc
            break

    run_status = active["class"] if active else "no_pending_escalation"
    dlq = _dlq_summary(state, dlq_reasons)

    if run_status == "awaiting_human":
        summary = (f"Run is at a human-decision gate ({active['code']}) — waiting on you, "
                   f"not a failure. Respond to resume.")
    elif run_status == "failed":
        summary = (f"Genuine failure: {active['code']} — {active['reason'][:140]}. "
                   f"DLQ roots: {len(dlq['roots'])}, cascaded: {len(dlq['cascaded'])}.")
    elif run_status == "needs_review":
        summary = f"Warning gate ({active['code']}): {active['reason'][:140]}."
    else:
        summary = "No pending escalation — run is in progress or complete."

    return {
        "status": "ok",
        "run_status": run_status,
        "active_escalation": active,
        "escalation_count": len(escalations),
        "escalations_by_class": _by_class(escalations),
        "dlq": dlq,
        "summary": summary,
    }


def _by_class(escalations) -> dict:
    out: dict[str, int] = {}
    for e in escalations:
        out[e["class"]] = out.get(e["class"], 0) + 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default=os.environ.get("ORCH_PROJECT_DIR", "."))
    args = parser.parse_args()
    print(json.dumps(evaluate(args.project_dir)))


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError:
        print(json.dumps({"status": "error", "reason": "log_missing",
                          "detail": "orchestration log not found — run orchestrator first"}),
              file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}),
              file=sys.stderr)
        sys.exit(1)
