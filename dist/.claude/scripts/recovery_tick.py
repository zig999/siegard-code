#!/usr/bin/env python3
"""
recovery_tick.py — Unstick a workflow at session start, without an orchestrator.

The gap this closes. Every recovery mechanism in the engine — promoting a due
`task_scheduled_retry`, reaping a silent worker, resolving a lingering FAILED —
runs ONLY inside a phase orchestrator's dispatch loop (`requeue_due_tasks.py` is
called from Step 5.0 in all four). The detector, by contrast, is the session Stop
hook. So the failure mode is structural:

    seq 5  23:09:25  task_claimed          triage
    seq 6  23:19:36  task_failed           agent=stale-monitor  reason=stale_timeout
    seq 7  23:19:36  task_scheduled_retry  next_retry_at=23:20:02
                     <- end of log. The retry never happened.

`on_stop.py` scheduled a recovery at the exact moment the only actuator able to
execute it ceased to exist. Nothing was broken; nothing was coming either.

This script is the actuator that does not need an orchestrator. It runs from the
SessionStart hook, so simply opening a session in the project resumes whatever
was left mid-flight — no `/u-supervise` loop required, nothing for the operator to
remember.

Fail-soft by construction: a SessionStart hook that raises would break the
session it is supposed to help, so every path returns exit 0 and reports through
stdout JSON. A project with no `.orch/` is a no-op.

Usage:
    python3 recovery_tick.py [--workflow-id ID] [--now ISO] [--dry-run]

Output (stdout, always JSON, always exit 0):
    {
      "status": "noop" | "recovered" | "attention" | "error",
      "phase": "<active phase>" | null,
      "workflow_id": "<id>" | null,
      "retried": [...], "scheduled": [...], "dlq_routed": [...], "reaped": [...],
      "non_terminal": <int>,
      "escalated": "<code>" | null,
      "detail": "<human-readable one-liner>"
    }
"""
import argparse
import json
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CLAUDE_DIR / "lib"))
sys.path.insert(0, str(_CLAUDE_DIR / "scripts"))

# Emitted when work is left non-terminal and nothing is driving it. The point is
# that the LOG says so: a passive file nobody reads is how 63 minutes were lost.
ESCALATION_CODE = "E26_workflow_left_unattended"


def _noop(detail: str) -> dict:
    return {
        "status": "noop", "phase": None, "workflow_id": None,
        "retried": [], "scheduled": [], "dlq_routed": [], "reaped": [],
        "non_terminal": 0, "escalated": None, "detail": detail,
    }


def run(workflow_id: str | None, now: str | None, dry_run: bool) -> dict:
    import orch_core
    from orch_core import (
        EventType, TaskStatus, append_event, now_iso, read_events, reduce_all,
    )

    if not orch_core.LOG_PATH.exists():
        return _noop("no orchestration log — nothing to recover")

    now = now or now_iso()
    state = reduce_all()

    active = next(
        (name for name, ph in state.phases.items()
         if ph.status not in (
             orch_core.PhaseStatus.COMPLETED, orch_core.PhaseStatus.EXIT_APPROVED)),
        None,
    )
    wf = workflow_id or state.workflow_id

    result = {
        "status": "noop", "phase": active, "workflow_id": wf,
        "retried": [], "scheduled": [], "dlq_routed": [], "reaped": [],
        "non_terminal": 0, "escalated": None, "detail": "",
    }

    non_terminal = [
        t for t in state.tasks.values()
        if t.status not in (TaskStatus.COMPLETED, TaskStatus.SKIPPED,
                            TaskStatus.DLQ)
        and (wf is None or t.workflow_id in (None, wf))
    ]
    result["non_terminal"] = len(non_terminal)

    if not non_terminal:
        result["detail"] = "no non-terminal tasks — nothing to recover"
        return result

    if dry_run:
        result["status"] = "attention"
        result["detail"] = (
            f"{len(non_terminal)} non-terminal task(s) in phase {active!r} "
            "(dry run — no events emitted)"
        )
        return result

    # 1. Reap workers that are silent past their own threshold. Deterministic and
    #    task-type aware; emits task_failed + schedules the retry atomically.
    try:
        result["reaped"] = orch_core.reap_stale_tasks(now=now)
    except Exception as exc:  # noqa: BLE001 — never break the session
        result["detail"] = f"reaper skipped: {exc}"

    # 2. Promote due retries and resolve lingering FAILED tasks — the step that
    #    previously existed only inside an orchestrator loop.
    try:
        import requeue_due_tasks
        out = requeue_due_tasks.requeue(now=now, phase=active, workflow_id=wf)
        result["retried"] = out.get("retried", [])
        result["scheduled"] = out.get("scheduled", [])
        result["dlq_routed"] = out.get("dlq_routed", [])
    except Exception as exc:  # noqa: BLE001
        result["detail"] = f"{result['detail']} requeue skipped: {exc}".strip()

    acted = bool(result["reaped"] or result["retried"] or result["dlq_routed"])

    # 3. Make the state visible IN THE LOG. Work left non-terminal with nobody
    #    driving it is an escalable condition, not a normal resting state — and an
    #    escalation is visible to whoever reads the log, which a passive
    #    last_error.json is not.
    already = any(
        e.event_type == EventType.ESCALATION.value
        and (e.data or {}).get("code") == ESCALATION_CODE
        for e in read_events()
    )
    if not already:
        try:
            ev = append_event(
                agent="recovery-tick",
                event_type=EventType.ESCALATION.value,
                data={
                    "code": ESCALATION_CODE,
                    "severity": "warning",
                    "reason": (
                        f"{len(non_terminal)} task(s) left non-terminal in phase "
                        f"{active!r} with no orchestrator driving them. Session start "
                        "promoted what it could; the phase still needs an orchestrator "
                        "to continue."
                    ),
                    "evidence": [state.last_seq],
                    "phase": active,
                    "workflow_id": wf,
                    "suggested_actions": [
                        "re-invoke the meta-orchestrator to resume the phase",
                        f"or start supervision so this cannot recur: /loop 5m /u-supervise {wf}",
                        "inspect the non-terminal tasks: python3 .claude/skills/orch-state/scripts/summary.py",
                    ],
                },
            )
            result["escalated"] = ESCALATION_CODE
            result["evidence_seq"] = ev.seq
        except Exception as exc:  # noqa: BLE001
            result["detail"] = f"{result['detail']} escalation skipped: {exc}".strip()

    result["status"] = "recovered" if acted else "attention"
    result["detail"] = (
        f"{len(non_terminal)} non-terminal task(s) in phase {active!r}; "
        f"reaped={len(result['reaped'])} retried={len(result['retried'])} "
        f"dlq={len(result['dlq_routed'])}"
    ).strip()
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow-id", default=None)
    ap.add_argument("--now", default=None, help="ISO timestamp override (tests)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(json.dumps(run(args.workflow_id, args.now, args.dry_run)))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        # A SessionStart hook that fails must not take the session with it.
        print(json.dumps({
            "status": "error", "phase": None, "workflow_id": None,
            "retried": [], "scheduled": [], "dlq_routed": [], "reaped": [],
            "non_terminal": 0, "escalated": None, "detail": str(exc),
        }))
    sys.exit(0)
