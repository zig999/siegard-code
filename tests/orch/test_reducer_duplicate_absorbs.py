"""C3/C4/C5, 2026-07-15 post-fix audit — reducer absorbs for the three residual
log-poison vectors. All three were reproduced against v2.20.0: a single event,
legally produced by racing writers that each derived state outside the log
lock, landed in the append-only log and made every future reduce_all() raise
IllegalTransition — an irreducible log, recoverable only by destructive
truncation.

  C3 "Poison D"  — a live worker's late GENUINE task_failed lands on SCHEDULED
      (the reaper/hook synthesize a failure and schedule the retry atomically,
      so a false-positive stale reap leaves the task SCHEDULED while the worker
      is still running). v2.20.0 reconciled only the task_completed twin.
  C4 "Poison C"  — two concurrent requeue_due_tasks.py ticks (dual-meta window)
      both promote the same due SCHEDULED task: the second task_retried lands
      on PENDING/READY. Same shape for a duplicate task_dlq.
  C5             — dual synthesizers: the second synthesized task_failed was
      no-op'd WITHOUT recording its seq in task.evidence, so the racing
      scheduler's task_scheduled_retry citing that seq failed the
      duplicate-absorb membership check and raised.

Absorbing a duplicate of an already-recorded episode is a pure no-op (nothing
flips state), recorded loudly in state.anomalies (P8 — fail loud, not fail
dead). Genuinely corrupt histories still raise — asserted below.
"""
import orch_core
from orch_core import (
    IllegalTransition,
    TaskStatus,
    append_event,
    reduce_all,
)
import pytest

_WF = "wf_absorbs"


def _seed_phase(phase="dev"):
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": _WF,
        "phases": [{"name": phase, "order": 1, "required": True}]})
    append_event("orchestrator", "phase_entered",
                 data={"phase": phase, "order": 1, "workflow_id": _WF})


def _create_claim(tid, phase="dev", task_type="impl"):
    append_event("orchestrator", "task_created", task_id=tid, data={
        "phase": phase, "deps": [], "tier": "standard", "type": task_type,
        "spec": "s", "workflow_id": _WF})
    append_event("orchestrator", "task_claimed", task_id=tid, data={
        "phase": phase, "worker_type": "w", "worker_id": "w1"})


def _synth_fail_and_schedule(tid, phase="dev", attempt=1):
    """The reaper/hook's atomic pair: synthesized failure + scheduled retry."""
    failed = append_event("stale-monitor", "task_failed", task_id=tid, attempt=attempt,
                          data={"phase": phase, "reason": "stale_timeout",
                                "retryable": True})
    append_event("stale-monitor", "task_scheduled_retry", task_id=tid, attempt=attempt,
                 data={"phase": phase, "next_retry_at": "2020-01-01T00:00:00.000Z",
                       "backoff_seconds": 1, "previous_failure_seq": failed.seq})
    return failed


def _anomaly_reasons(state):
    return [a.get("reason") for a in state.anomalies]


# ------------------------------------------------------------ C3 ("Poison D")

def test_late_genuine_failure_on_scheduled_is_absorbed(tmp_orch):
    _seed_phase()
    _create_claim("t1")
    _synth_fail_and_schedule("t1")
    # Worker was alive all along (false-positive stale reap) and genuinely fails:
    append_event("w1", "task_failed", task_id="t1", attempt=1,
                 data={"phase": "dev", "reason": "validation_failed", "retryable": True})

    state = reduce_all()  # must not raise
    assert state.tasks["t1"].status == TaskStatus.SCHEDULED
    assert state.tasks["t1"].next_retry_at is not None  # scheduled retry intact
    assert "late_failure_on_scheduled_absorbed" in _anomaly_reasons(state)


def test_failure_for_unreached_attempt_on_scheduled_still_raises(tmp_orch):
    """Boundary: a task_failed for an attempt the task never reached is genuine
    corruption, not a duplicate episode — the validator stays a feature."""
    _seed_phase()
    _create_claim("t1")
    _synth_fail_and_schedule("t1")
    append_event("w1", "task_failed", task_id="t1", attempt=5,
                 data={"phase": "dev", "reason": "validation_failed", "retryable": True})
    with pytest.raises(IllegalTransition):
        reduce_all()


def test_straggler_failure_after_promotion_still_noop(tmp_orch):
    """Existing guard preserved: after task_retried advanced the attempt, an old
    worker's late failure (older attempt) stays an idempotent no-op."""
    _seed_phase()
    _create_claim("t1")
    _synth_fail_and_schedule("t1")
    append_event("orchestrator", "task_retried", task_id="t1", attempt=2,
                 data={"phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": 0})
    append_event("w1", "task_failed", task_id="t1", attempt=1,
                 data={"phase": "dev", "reason": "validation_failed", "retryable": True})
    state = reduce_all()
    assert state.tasks["t1"].status in (TaskStatus.PENDING, TaskStatus.READY)


# ------------------------------------------------------------------------ C5

def test_duplicate_failed_records_evidence_so_second_scheduler_absorbs(tmp_orch):
    """Dual synthesizers: reaper and SubagentStop hook both synthesize the
    failure. The second task_failed is no-op'd but MUST record its seq in
    evidence — the hook then cites that seq in its own task_scheduled_retry and
    the duplicate-absorb matches on evidence membership. Before this fix the
    membership check missed and the second schedule poisoned the log."""
    _seed_phase()
    _create_claim("t1")
    append_event("stale-monitor", "task_failed", task_id="t1", attempt=1,
                 data={"phase": "dev", "reason": "stale_timeout", "retryable": True})
    dup = append_event("hook", "task_failed", task_id="t1", attempt=1,
                       data={"phase": "dev", "reason": "worker_exited_without_terminal",
                             "retryable": True})
    # First scheduler wins (cites the first failure's seq — not asserted here);
    # the losing scheduler cites the seq of ITS OWN (no-op'd) failure event:
    append_event("stale-monitor", "task_scheduled_retry", task_id="t1", attempt=1,
                 data={"phase": "dev", "next_retry_at": "2020-01-01T00:00:00.000Z",
                       "backoff_seconds": 1, "previous_failure_seq": dup.seq - 1})
    append_event("hook", "task_scheduled_retry", task_id="t1", attempt=1,
                 data={"phase": "dev", "next_retry_at": "2020-01-01T00:00:01.000Z",
                       "backoff_seconds": 2, "previous_failure_seq": dup.seq})

    state = reduce_all()  # must not raise
    assert state.tasks["t1"].status == TaskStatus.SCHEDULED
    reasons = _anomaly_reasons(state)
    assert "duplicate_task_failed_absorbed" in reasons
    assert "duplicate_scheduled_retry_absorbed" in reasons


def test_scheduled_retry_with_unknown_seq_still_raises(tmp_orch):
    """Boundary: a task_scheduled_retry citing a seq that is NOT a recorded
    failure of this task remains corruption and raises."""
    _seed_phase()
    _create_claim("t1")
    _synth_fail_and_schedule("t1")
    append_event("x", "task_scheduled_retry", task_id="t1", attempt=1,
                 data={"phase": "dev", "next_retry_at": "2020-01-01T00:00:01.000Z",
                       "backoff_seconds": 2, "previous_failure_seq": 999})
    with pytest.raises(IllegalTransition):
        reduce_all()


# ------------------------------------------------------------ C4 ("Poison C")

def test_duplicate_task_retried_is_absorbed(tmp_orch):
    """Two concurrent requeue ticks both promoted the same due SCHEDULED task."""
    _seed_phase()
    _create_claim("t1")
    _synth_fail_and_schedule("t1")
    for _ in range(2):
        append_event("orchestrator", "task_retried", task_id="t1", attempt=2,
                     data={"phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": 0})

    state = reduce_all()  # must not raise
    assert state.tasks["t1"].status in (TaskStatus.PENDING, TaskStatus.READY)
    assert state.tasks["t1"].attempts == 2  # applied exactly once
    assert "duplicate_task_retried_absorbed" in _anomaly_reasons(state)


def test_task_retried_on_never_failed_task_still_raises(tmp_orch):
    """Boundary: task_retried for a task with no failure history is corruption."""
    _seed_phase()
    _create_claim("t1")
    append_event("orchestrator", "task_retried", task_id="t1", attempt=1,
                 data={"phase": "dev", "previous_attempt": 0, "scheduled_retry_seq": 0})
    with pytest.raises(IllegalTransition):
        reduce_all()


def test_duplicate_task_dlq_is_absorbed(tmp_orch):
    """Two concurrent requeue ticks both routed the same lingering FAILED task."""
    _seed_phase()
    _create_claim("t1")
    append_event("w1", "task_failed", task_id="t1", attempt=1,
                 data={"phase": "dev", "reason": "validation_failed", "retryable": False})
    for _ in range(2):
        append_event("stale-monitor", "task_dlq", task_id="t1",
                     data={"phase": "dev", "reason": "non_retryable",
                           "last_error": "boom"})

    state = reduce_all()  # must not raise
    assert state.tasks["t1"].status == TaskStatus.DLQ
    assert "duplicate_task_dlq_absorbed" in _anomaly_reasons(state)


def test_task_dlq_on_completed_task_still_raises(tmp_orch):
    """Boundary: routing a COMPLETED task to DLQ remains corruption."""
    _seed_phase()
    _create_claim("t1")
    append_event("w1", "task_completed", task_id="t1", attempt=1,
                 data={"phase": "dev", "artifacts": []})
    append_event("stale-monitor", "task_dlq", task_id="t1",
                 data={"phase": "dev", "reason": "non_retryable", "last_error": "x"})
    with pytest.raises(IllegalTransition):
        reduce_all()
