#!/usr/bin/env python3
"""Deterministic requeue tick for the dev/review/test/sdd dispatch loop
(recommendation #4, 2026-07-15 workflow audit — "A1: busy-spin backoff + lost
retry").

Two related failure modes, both rooted in the same gap: retry-scheduling and
DLQ-routing for FAILED/SCHEDULED tasks were prompt-composed (LLM-improvised
backoff math, batch-scoped Step 5.5) instead of one deterministic entry point
callable before the dispatch loop's stop-condition check.

  1. A SCHEDULED task whose next_retry_at is already due needs task_retried to
     become READY. If the stop-condition check runs against state captured
     BEFORE this promotion, "no ready tasks" is stale and the loop bails to
     Step 6 without ever unblocking the due retry — Step 6 bounces it back to
     Step 5, ping-ponging until the 30-iteration cap fires a spurious
     "dispatch loop safety limit reached" error.
  2. A worker-reported task_failed whose Step 5.5 (batch-scoped, runs only
     after a dispatched batch) never executed because the orchestrator's turn
     ended first leaves the task FAILED with no schedule and no DLQ routing.
     Nothing else ever revisits it — it stalls forever across every future
     invocation.

This script closes both: it (a) promotes every due SCHEDULED task via
task_retried, and (b) for every lingering FAILED task with no schedule yet,
either schedules its retry (schedule_retry_if_due, retryable case) or routes
it to DLQ directly (should_retry() False) — regardless of which iteration or
session originally failed it.

Usage:
    requeue_due_tasks.py            # using the current time
    requeue_due_tasks.py --now <ISO>  # override "now" (testing)

Output (stdout, single JSON line):
    {"retried": [task_id, ...], "scheduled": [task_id, ...],
     "dlq_routed": [task_id, ...], "earliest_pending_retry_at": <iso|null>}

`earliest_pending_retry_at` lets the caller distinguish "genuinely nothing
left to do" from "healthy, just waiting on a future backoff" — the latter
should stop cleanly instead of burning the dispatch loop's iteration budget
at LLM/tool speed toward a misleading error.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from orch_core import (  # noqa: E402
    EventType,
    RetryPolicy,
    TaskStatus,
    append_event,
    load_config,
    now_iso,
    reduce_all,
    schedule_retry_if_due,
    should_retry,
    tasks_ready_for_retry,
)


def _dlq_reason(task) -> str:
    return "non_retryable" if task.last_failure_retryable is False else "max_attempts_exceeded"


def _in_scope(task, phase: str | None, workflow_id: str | None) -> bool:
    if phase is not None and task.phase != phase:
        return False
    if workflow_id is not None and task.workflow_id != workflow_id:
        return False
    return True


def requeue(
    now: str | None = None,
    phase: str | None = None,
    workflow_id: str | None = None,
    protect_task_types: frozenset[str] = frozenset(),
) -> dict:
    """protect_task_types: task_types with their OWN attempt-count escalation (e.g. sdd's
    spec-writer >=3 / spec-validator >=2 rejection-cycle check, which fires at a LOWER
    threshold than the tier's generic max_attempts). Case (b) below leaves these FAILED
    and untouched — neither rescheduling nor DLQ-routing them — so that check still sees
    them and still escalates. Without this, a spec-validator at attempts=2 (still under
    the tier's max_attempts=3) would get ANOTHER retry scheduled here, letting it reach
    attempt 3 and skip the human escalation the rejection-cycle check exists to raise.
    """
    now = now or now_iso()
    cfg = load_config()
    retried: list[str] = []
    scheduled: list[str] = []
    dlq_routed: list[str] = []

    # (a) promote every SCHEDULED task whose next_retry_at is already due.
    state = reduce_all()
    for task in tasks_ready_for_retry(state, now):
        if not _in_scope(task, phase, workflow_id):
            continue
        try:
            append_event(
                agent="orchestrator",
                event_type=EventType.TASK_RETRIED.value,
                task_id=task.task_id,
                attempt=task.attempts + 1,
                data={
                    "phase": task.phase,
                    "previous_attempt": task.attempts,
                    "scheduled_retry_seq": task.evidence[-1] if task.evidence else 0,
                },
            )
            retried.append(task.task_id)
        except Exception:  # noqa: BLE001 — a requeue tick must never raise
            continue

    # (b) resolve every lingering FAILED task with no schedule yet: schedule a
    # retry (retryable) or route straight to DLQ (should_retry() False) — the
    # gap Step 5.5 leaves open when the orchestrator's turn ends before it runs.
    state = reduce_all()
    for task in list(state.tasks.values()):
        if task.status != TaskStatus.FAILED:
            continue
        if not _in_scope(task, phase, workflow_id):
            continue
        if task.task_type in protect_task_types:
            continue
        policy = RetryPolicy.for_task(task.task_type or "", task.tier, cfg)
        if should_retry(task, policy):
            previous_failure_seq = task.evidence[-1] if task.evidence else 0
            scheduled_at = schedule_retry_if_due(task.task_id, previous_failure_seq, now, cfg)
            if scheduled_at:
                scheduled.append(task.task_id)
        else:
            try:
                append_event(
                    agent="stale-monitor",
                    event_type=EventType.TASK_DLQ.value,
                    task_id=task.task_id,
                    data={
                        "phase": task.phase,
                        "reason": _dlq_reason(task),
                        "last_error": task.last_failure_reason or "unknown",
                    },
                )
                dlq_routed.append(task.task_id)
            except Exception:  # noqa: BLE001
                continue

    state = reduce_all()
    pending = [t.next_retry_at for t in state.tasks.values()
               if t.status == TaskStatus.SCHEDULED and t.next_retry_at
               and _in_scope(t, phase, workflow_id)]
    earliest = min(pending) if pending else None

    return {
        "retried": retried,
        "scheduled": scheduled,
        "dlq_routed": dlq_routed,
        "earliest_pending_retry_at": earliest,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic retry/DLQ requeue tick.")
    ap.add_argument("--now", default=None, help="ISO 8601 override for current time (testing).")
    ap.add_argument("--phase", default=None,
                    help="Restrict to this phase's tasks (each phase orchestrator passes "
                         "its own phase; omit to process every phase).")
    ap.add_argument("--workflow-id", default=None,
                    help="Restrict to this workflow's tasks (defense-in-depth for a shared "
                         "log with multiple namespaced workflows; omit to process every "
                         "workflow currently in this phase).")
    ap.add_argument("--protect-task-types", default="",
                    help="Comma-separated task_types to leave FAILED untouched (their own "
                         "attempt-count escalation handles them, e.g. sdd's spec-writer / "
                         "spec-validator rejection-cycle check).")
    args = ap.parse_args()
    protect = frozenset(t for t in args.protect_task_types.split(",") if t)
    print(json.dumps(requeue(args.now, args.phase, args.workflow_id, protect)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "detail": str(exc)}), file=sys.stderr)
        sys.exit(1)
