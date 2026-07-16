#!/usr/bin/env python3
"""Supervision advice — deterministic recommendation on whether to offer autonomous
supervision (/u-supervise, driven by /loop or /schedule) at the point a workflow yields
with phases still pending.

Pure function of the log (P2/P11/P12): no side effects, no new event types, no reducer
state. Consumed by the meta-orchestrator's phase_advanced report and, through it, by the
entry commands (/u-dev, /u-orchestrator) to render a one-time detach decision.

Why it fires ONLY at the first phase transition
-----------------------------------------------
The attended entry commands auto-advance phases inside a single turn (the re-invocation
loop re-invokes immediately on phase_advanced). In that mode the human is the supervisor,
so the only genuine decision is made ONCE, at the first advance: keep driving here, or
detach the remaining phases to an autonomous supervisor. Re-offering on every advance is
noise — the auto-loop blows straight past it. Therefore recommendation requires exactly
one phase_transitioned event for the workflow and a still-active run.

Output (single JSON line)
-------------------------
  {"recommended": bool,
   "reason": str,
   "workflow_id": str|null,
   "commands": {"attended": str, "unattended": str},
   "message": str}

Usage
-----
  supervision_advice.py [--workflow-id ID] [--loop-interval 5m]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from orch_core import (  # noqa: E402
    EventType,
    load_config,
    read_events_filtered,
    reduce_all,
)

_PHASE_TRANSITIONED = EventType.PHASE_TRANSITIONED.value

# Terminal / non-active run states where a supervisor cannot help (or is moot):
# - completed: nothing left to supervise
# - escalated: needs a human_response, not another auto-resume
# - blocked:   needs human diagnosis, not a watcher
_NON_ACTIVE_REASON = {
    "completed": "workflow_completed",
    "escalated": "awaiting_human_response",
    "blocked": "needs_human_diagnosis",
}


def _commands(workflow_id: str | None, loop_interval: str) -> dict:
    wf = workflow_id or "<workflow_id>"
    return {
        "attended": f"/loop {loop_interval} /u-supervise {wf}",
        "unattended": f"/schedule /u-supervise {wf}",
    }


def _message(cmds: dict) -> str:
    return (
        "First phase transition detected. To keep the workflow progressing without "
        "driving each phase by hand, hand the remaining phases to a supervisor: "
        f"'{cmds['attended']}' (attended — keeps this session open) or "
        f"'{cmds['unattended']}' (unattended — requires the scheduler to reach this "
        "repo). Reply 'loop', 'schedule', or 'stay' to keep driving here."
    )


def advise(
    run_status: str,
    transitions_count: int,
    workflow_id: str | None = None,
    *,
    loop_interval: str = "5m",
) -> dict:
    """Pure decision core. Recommends supervision iff the run is still active AND exactly
    one phase transition has happened (the first advance)."""
    cmds = _commands(workflow_id, loop_interval)
    base = {"workflow_id": workflow_id, "commands": cmds}

    if run_status != "active":
        reason = _NON_ACTIVE_REASON.get(run_status, f"run_status_{run_status}")
        return {"recommended": False, "reason": reason, "message": "", **base}

    if transitions_count == 0:
        return {"recommended": False, "reason": "no_transition_yet", "message": "", **base}

    if transitions_count > 1:
        # Anti-nag: the detach decision was already surfaced at the first transition.
        return {"recommended": False, "reason": "not_first_transition", "message": "", **base}

    return {
        "recommended": True,
        "reason": "first_transition_pending_phases",
        "message": _message(cmds),
        **base,
    }


def compute(workflow_id: str | None = None, loop_interval: str | None = None) -> dict:
    """Read the log and derive the recommendation. transitions_count is scoped to
    workflow_id when given: the per-project log outlives workflows, and a global
    count made the SECOND workflow's first transition read as count > 1 →
    "not_first_transition" — the detach on-ramp silently never fired again for
    that project (2026-07-15 post-fix audit, M4). phase_transitioned carries
    workflow_id as a required field; events without it (legacy logs) stay counted."""
    state = reduce_all()
    transitions = [
        e for e in read_events_filtered(event_type=_PHASE_TRANSITIONED)
        if workflow_id is None or e.data.get("workflow_id") in (None, workflow_id)
    ]
    interval = loop_interval or load_config().get("supervisor_policy", {}).get(
        "loop_interval", "5m"
    )
    return advise(
        run_status=state.run_status,
        transitions_count=len(transitions),
        workflow_id=workflow_id,
        loop_interval=interval,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Supervision detach-point advice (pure log).")
    ap.add_argument("--workflow-id", default=None,
                    help="Scope transitions_count to this workflow (prior workflows in a "
                         "shared log must not suppress the on-ramp).")
    ap.add_argument("--loop-interval", default=None, help="/loop interval, e.g. 5m (default 5m).")
    args = ap.parse_args()
    print(json.dumps(compute(args.workflow_id, args.loop_interval)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "detail": str(exc)}), file=sys.stderr)
        sys.exit(1)
