#!/usr/bin/env python3
"""Supervised auto-resume tick (E2 / B(b) — rec #3 follow-up to CONF-05).

Detects a stalled phase orchestrator and, within a per-phase resume budget, appends
`orchestrator_resume_requested` so the foreground `/u-supervise` command re-invokes the
meta-orchestrator. All accounting is DERIVED FROM THE LOG (P1/P2) — no reducer state and
no side-file. The two events it uses (`orchestrator_resume_requested`, `orchestrator_resumed`)
are audit-only (no reducer handler).

Why not just reuse `detect_stale_orchestrator`? That signal only checks
`orchestrator_heartbeat`. A worker running a long single dispatch (>threshold) legitimately
leaves the orchestrator loop blocked without a heartbeat, yet the phase is alive (the worker
emits `task_progress`, which advances `task.last_event_at`). Auto-resume is more aggressive
than the passive on_stop diagnostic — spawning a second meta during live dispatch is harmful —
so this tick additionally requires TOTAL PHASE SILENCE: no phase-task activity within the
threshold. Combined guards (no orchestrator_heartbeat AND no recent task activity) make a
false-positive resume during active work practically impossible.

Budget (`supervisor_policy` in `.orch/config.json`):
  - max_auto_resumes: resume ATTEMPTS (`orchestrator_resume_requested`) for the phase since
    its last `phase_entered` — counting attempts, not just completions, so a /u-supervise
    that dies before appending `orchestrator_resumed` still exhausts the budget instead of
    re-requesting forever. Exhausted -> append `escalation E23_resume_budget_exhausted`
    (halts the run, awaiting_human — a persistently stuck workflow must reach a human).
  - cooldown_seconds: skip if the last resume request/resumed for the phase is within it.
  - in_flight_ttl_seconds: a `resume_requested` with no later `resumed`/`heartbeat` is
    "in flight" and blocks a new request — UNLESS older than the TTL (expired, so a
    crashed /u-supervise never wedges auto-resume permanently).

If `run_status == escalated`, the tick is a no-op: the run is already awaiting a human.

Output (stdout, one JSON line):
  {"resume": bool, "escalate": bool, "phase": str|null, "workflow_id": str|null,
   "reason": str, "budget_remaining": int}

Usage:
    supervisor_tick.py [--workflow-id ID] [--now ISO]     # ISO override for tests
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from orch_core import (  # noqa: E402
    EventType,
    ORCHESTRATOR_STALE_SECONDS,
    TaskStatus,
    _elapsed_seconds,
    append_event,
    detect_stale_orchestrator,
    load_config,
    now_iso,
    read_events_filtered,
    reduce_all,
)

_RESUME_REQUESTED = EventType.ORCHESTRATOR_RESUME_REQUESTED.value
_RESUMED = EventType.ORCHESTRATOR_RESUMED.value
_HEARTBEAT = EventType.ORCHESTRATOR_HEARTBEAT.value
_PHASE_ENTERED = EventType.PHASE_ENTERED.value


def _phase_entered_seq(events: list, phase: str) -> int:
    """Highest seq of a `phase_entered` for `phase` (0 if none) — the window boundary
    for budget/cooldown accounting, so counts reset when the phase is (re-)entered."""
    seqs = [e.seq for e in events if e.event_type == _PHASE_ENTERED and e.data.get("phase") == phase]
    return max(seqs, default=0)


def _phase_events(events: list, phase: str, event_type: str, since_seq: int) -> list:
    return [
        e for e in events
        if e.event_type == event_type and e.data.get("phase") == phase and e.seq > since_seq
    ]


def _no(reason: str, phase: str | None, workflow_id: str | None, budget_remaining: int) -> dict:
    return {
        "resume": False, "escalate": False, "phase": phase,
        "workflow_id": workflow_id, "reason": reason, "budget_remaining": budget_remaining,
    }


def decide(state: Any, events: list, now: str, policy: dict,
           threshold: int = ORCHESTRATOR_STALE_SECONDS) -> dict:
    """Pure decision function (no I/O) — the testable core.

    Returns a dict with `resume` (append resume_requested + re-invoke), `escalate`
    (budget exhausted -> emit E23), or neither (no-op with a `reason`).
    """
    phase = state.current_phase
    workflow_id = getattr(state, "workflow_id", None)

    if phase is None:
        return _no("no_active_phase", None, workflow_id, 0)
    if getattr(state, "run_status", None) == "escalated":
        # already awaiting a human — the supervisor must not act (and must not re-emit E23).
        return _no("run_escalated_awaiting_human", phase, workflow_id, 0)
    if not policy.get("enabled", True):
        return _no("supervisor_disabled", phase, workflow_id, 0)

    # (1) orchestrator-heartbeat staleness (active phase, non-terminal tasks, no heartbeat).
    if detect_stale_orchestrator(state, events, now, threshold) is None:
        return _no("orchestrator_live_or_no_pending", phase, workflow_id, 0)

    # (2) TOTAL PHASE SILENCE: a RUNNING task that moved within the threshold means a worker
    # is still progressing (task_progress advances last_event_at only for RUNNING tasks) — do
    # NOT resume. Only RUNNING counts: a just-completed terminal task's frozen last_event_at
    # is not "ongoing work" and must not mask a stalled orchestrator that failed to dispatch.
    activity = [t.last_event_at for t in state.tasks.values()
                if t.phase == phase and t.status == TaskStatus.RUNNING and t.last_event_at]
    if any(_elapsed_seconds(now, ts) < threshold for ts in activity):
        return _no("phase_tasks_active", phase, workflow_id, 0)

    # Budget accounting, scoped to the current phase attempt (since last phase_entered).
    # Count resume ATTEMPTS (requests), not just completions: a request that never lands
    # (crashed /u-supervise) must still consume budget so the phase escalates to E23 rather
    # than re-requesting every TTL forever.
    entered_seq = _phase_entered_seq(events, phase)
    requested = _phase_events(events, phase, _RESUME_REQUESTED, entered_seq)
    resumed = _phase_events(events, phase, _RESUMED, entered_seq)
    max_resumes = int(policy.get("max_auto_resumes", 3))
    remaining = max_resumes - len(requested)
    if remaining <= 0:
        return {
            "resume": False, "escalate": True, "phase": phase,
            "workflow_id": workflow_id, "reason": "resume_budget_exhausted",
            "budget_remaining": 0,
        }

    # Cooldown: min gap between resume actions for the same phase.
    recent = resumed + requested
    cooldown = float(policy.get("cooldown_seconds", 300))
    if recent:
        last_recent = max(recent, key=lambda e: e.seq)
        if _elapsed_seconds(now, last_recent.ts) < cooldown:
            return _no("cooldown_active", phase, workflow_id, remaining)

    # In-flight guard with TTL: a resume_requested not yet followed by a resumed/heartbeat
    # is mid-flight; block a new one unless it is older than the TTL (expired -> proceed,
    # so a crashed /u-supervise never wedges auto-resume permanently).
    if requested:
        last_req = max(requested, key=lambda e: e.seq)
        satisfied = any(
            e.seq > last_req.seq
            for e in events
            if e.event_type in (_RESUMED, _HEARTBEAT) and e.data.get("phase") == phase
        )
        if not satisfied:
            ttl = float(policy.get("in_flight_ttl_seconds", 900))
            if _elapsed_seconds(now, last_req.ts) < ttl:
                return _no("resume_in_flight", phase, workflow_id, remaining)

    return {
        "resume": True, "escalate": False, "phase": phase,
        "workflow_id": workflow_id, "reason": "stalled_no_heartbeat_no_task_activity",
        "budget_remaining": remaining,
    }


def _apply(decision: dict, last_seq: int) -> None:
    """Side effects: append the request (resume) or the budget-exhausted escalation. An
    append failure propagates — main() then reports the error JSON on stderr and exits
    non-zero, rather than printing the decision as if it had been persisted."""
    phase = decision.get("phase")
    workflow_id = decision.get("workflow_id")
    if decision.get("resume"):
        append_event(
            agent="supervisor",
            event_type=_RESUME_REQUESTED,
            data={
                "phase": phase,
                "workflow_id": workflow_id,
                "reason": decision.get("reason"),
                "budget_remaining": decision.get("budget_remaining"),
            },
        )
    elif decision.get("escalate"):
        append_event(
            agent="supervisor",
            event_type=EventType.ESCALATION.value,
            data={
                "code": "E23_resume_budget_exhausted",
                "severity": "warning",
                "reason": (
                    f"Auto-resume budget exhausted for phase {phase!r}: the orchestrator "
                    "kept stalling after the configured retries. Human attention required."
                ),
                "evidence": [last_seq],
                "suggested_actions": [
                    "inspect the phase for a systemic block (worker crash loop, missing input)",
                    "resolve the block, then re-invoke /u-orchestrator to clear the escalation",
                ],
            },
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Supervised auto-resume tick.")
    ap.add_argument("--workflow-id", default=None, help="Workflow id (observability only).")
    ap.add_argument("--now", default=None, help="ISO 8601 override for current time (testing).")
    args = ap.parse_args()
    now = args.now or now_iso()

    state = reduce_all()
    events = list(read_events_filtered())
    policy = load_config().get("supervisor_policy", {})

    decision = decide(state, events, now, policy)
    last_seq = events[-1].seq if events else 0
    _apply(decision, last_seq)

    print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "detail": str(exc)}), file=sys.stderr)
        sys.exit(1)
