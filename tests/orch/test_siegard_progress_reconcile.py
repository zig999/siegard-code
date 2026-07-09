"""SIEGARD F1 + F2 — reaper false-positive: root cause + safety net.

F1 — task_progress heartbeat resets the staleness timer. task_progress had NO
     reducer handler, so task.last_event_at advanced only on state transitions
     (task_claimed, ...). A live worker emitting only progress checkpoints was
     reaped as stale. _handle_task_progress now advances last_event_at, matching
     the contract stale_tasks' docstring already promised.

F2 — false-positive reconciliation. A SYNTHESIZED terminal (stale_timeout /
     worker_exited_without_terminal, emitted by the reaper/hook — never by the
     worker) that is later contradicted by a genuine task_completed from the same
     worker at the same attempt was a false positive, not corruption. The reducer
     accepts FAILED->COMPLETED and records an anomaly instead of aborting the whole
     read-path. Kept NARROW: a completed over a worker-reported FAILED, or over a
     never-claimed task, still raises IllegalTransition.
"""
from datetime import datetime, timedelta, timezone

import orch_core


# ---------------------------------------------------------------------------
# F1 — task_progress heartbeat (apply_event with controlled timestamps)
# ---------------------------------------------------------------------------

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _at(seconds: int) -> str:
    return (_BASE + timedelta(seconds=seconds)).isoformat()


def _ev(seq, event_type, ts, *, task_id=None, attempt=1, data=None):
    """Build an Event directly (bypasses append/hash — apply_event never reads the
    hash chain, only the reducer-relevant fields)."""
    return orch_core.Event.from_dict({
        "seq": seq, "event_id": f"e{seq}", "ts": ts, "agent": "t",
        "event_type": event_type, "task_id": task_id, "attempt": attempt,
        "data": data or {}, "prev_hash": "0" * 64, "hash": "0" * 64,
    })


def _phase(state):
    """Declare + enter the 'dev' phase so created tasks promote to READY."""
    orch_core.apply_event(state, _ev(1, "phase_declared", _at(0), data={
        "workflow_id": "wf", "phases": [{"name": "dev", "order": 1, "required": True}],
    }))
    orch_core.apply_event(state, _ev(2, "phase_entered", _at(0), data={
        "phase": "dev", "order": 1, "workflow_id": "wf",
    }))


def _created(state, seq, tid, ts, task_type="", tier="standard"):
    orch_core.apply_event(state, _ev(seq, "task_created", ts, task_id=tid, data={
        "phase": "dev", "tier": tier, "type": task_type, "spec": "s", "deps": [],
    }))


def _claimed(state, seq, tid, ts, attempt=1):
    orch_core.apply_event(state, _ev(seq, "task_claimed", ts, task_id=tid, attempt=attempt, data={
        "phase": "dev", "worker_type": "u-be-developer", "worker_id": f"w{attempt}",
    }))


def _progress(state, seq, tid, ts, attempt=1):
    orch_core.apply_event(state, _ev(seq, "task_progress", ts, task_id=tid, attempt=attempt, data={
        "phase": "dev", "note": "analysis_complete",
    }))


class TestProgressHeartbeatResetsStaleTimer:

    def test_progress_advances_last_event_at(self):
        state = orch_core.OrchState()
        _phase(state)
        _created(state, 1, "t1", _at(0))
        _claimed(state, 2, "t1", _at(0))
        _progress(state, 3, "t1", _at(400))
        # Before F1 this stayed at the claim ts (_at(0)); now it tracks the heartbeat.
        assert state.tasks["t1"].last_event_at == _at(400)

    def test_worker_with_recent_progress_is_not_reaped(self):
        # type="" + tier standard => 300s threshold (no override), config-free.
        state = orch_core.OrchState()
        _phase(state)
        _created(state, 1, "t1", _at(0))
        _claimed(state, 2, "t1", _at(0))
        _progress(state, 3, "t1", _at(400))          # heartbeat at +400s
        # A control task that only claimed and went silent since _at(0).
        _created(state, 4, "t2", _at(0))
        _claimed(state, 5, "t2", _at(0))

        stale = orch_core.stale_tasks(state, _at(500), config={})
        stale_ids = {t.task_id for t in stale}
        # t1: now - last_progress = 100s < 300s  -> alive (this is the F1 fix).
        assert "t1" not in stale_ids
        # t2: now - claim = 500s > 300s -> correctly reaped.
        assert "t2" in stale_ids

    def test_worker_liveness_gate_respects_heartbeat(self):
        state = orch_core.OrchState()
        _phase(state)
        _created(state, 1, "t1", _at(0))
        _claimed(state, 2, "t1", _at(0))
        _progress(state, 3, "t1", _at(400))
        assert orch_core.worker_liveness_expired(state.tasks["t1"], _at(500), {}) is False
        assert orch_core.worker_liveness_expired(state.tasks["t1"], _at(800), {}) is True

    def test_progress_on_failed_task_is_noop(self):
        state = orch_core.OrchState()
        _phase(state)
        _created(state, 1, "t1", _at(0))
        _claimed(state, 2, "t1", _at(0))
        orch_core.apply_event(state, _ev(3, "task_failed", _at(10), task_id="t1", data={
            "phase": "dev", "reason": "stale_timeout", "retryable": True,
        }))
        _progress(state, 4, "t1", _at(400))          # straggler progress on a dead task
        # Must not revive the timer of a task already reaped to FAILED.
        assert state.tasks["t1"].last_event_at == _at(10)

    def test_progress_for_superseded_attempt_is_noop(self):
        state = orch_core.OrchState()
        _phase(state)
        _created(state, 1, "t1", _at(0))
        _claimed(state, 2, "t1", _at(0))
        orch_core.apply_event(state, _ev(3, "task_failed", _at(5), task_id="t1", data={
            "phase": "dev", "reason": "stale_timeout", "retryable": True,
        }))
        orch_core.apply_event(state, _ev(4, "task_scheduled_retry", _at(6), task_id="t1", data={
            "phase": "dev", "next_retry_at": _at(6), "backoff_seconds": 30,
            "previous_failure_seq": 3,
        }))
        orch_core.apply_event(state, _ev(5, "task_retried", _at(7), task_id="t1", attempt=2, data={
            "phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": 4,
        }))
        _claimed(state, 6, "t1", _at(10), attempt=2)  # RUNNING on attempt 2
        _progress(state, 7, "t1", _at(400), attempt=1)  # late attempt-1 heartbeat
        # An old attempt's straggler progress must not reset the live attempt's timer.
        assert state.tasks["t1"].last_event_at == _at(10)


# ---------------------------------------------------------------------------
# F2 — false-positive reconciliation (append-based, via reduce_all)
# ---------------------------------------------------------------------------

def _ep(make_event, phase="dev", wf="wf"):
    make_event("phase_declared", data={
        "workflow_id": wf, "phases": [{"name": phase, "order": 1, "required": True}]})
    make_event("phase_entered", data={"phase": phase, "order": 1, "workflow_id": wf})


def _c(make_event, tid):
    make_event("task_created", task_id=tid, data={
        "phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": [],
    })


def _cl(make_event, tid, attempt=1):
    make_event("task_claimed", task_id=tid, attempt=attempt, data={
        "phase": "dev", "worker_type": "u-be-developer", "worker_id": f"w{attempt}",
    })


def _f(make_event, tid, reason, attempt=1):
    make_event("task_failed", task_id=tid, attempt=attempt, data={
        "phase": "dev", "reason": reason, "retryable": True,
    })


def _prog(make_event, tid, attempt=1, note="draft_written"):
    make_event("task_progress", task_id=tid, attempt=attempt, data={"phase": "dev", "note": note})


def _done(make_event, tid, attempt=1):
    make_event("task_completed", task_id=tid, attempt=attempt, data={"phase": "dev", "artifacts": []})


def _anomaly_reasons(state):
    return {a.get("reason") for a in state.anomalies}


class TestFalsePositiveReconciliation:

    def test_worker_exited_terminal_then_completed_reconciles(self, orch_dir, make_event):
        _ep(make_event)
        _c(make_event, "t1")
        _cl(make_event, "t1")
        _f(make_event, "t1", "worker_exited_without_terminal")  # synthesized by hook
        _done(make_event, "t1")                                 # live worker finishes

        state = orch_core.reduce_all()   # must NOT raise
        assert state.tasks["t1"].status == orch_core.TaskStatus.COMPLETED
        assert "reconciled_false_positive_completion" in _anomaly_reasons(state)

    def test_stale_timeout_then_completed_reconciles(self, orch_dir, make_event):
        _ep(make_event)
        _c(make_event, "t1")
        _cl(make_event, "t1")
        _f(make_event, "t1", "stale_timeout")                   # synthesized by reaper
        _done(make_event, "t1")

        state = orch_core.reduce_all()
        assert state.tasks["t1"].status == orch_core.TaskStatus.COMPLETED
        assert "reconciled_false_positive_completion" in _anomaly_reasons(state)

    def test_worker_reported_failure_then_completed_still_raises(self, orch_dir, make_event):
        """Boundary: a completed over a WORKER-reported FAILED (not synthesized) is
        genuine corruption and MUST still abort the strict reducer."""
        _ep(make_event)
        _c(make_event, "t1")
        _cl(make_event, "t1")
        _f(make_event, "t1", "validation_failed")               # worker-emitted reason
        _done(make_event, "t1")

        try:
            orch_core.reduce_all()
            assert False, "expected IllegalTransition (validation_failed is not synthesized)"
        except orch_core.IllegalTransition:
            pass

    def test_completed_over_never_claimed_still_raises(self, orch_dir, make_event):
        """Boundary: completed on a READY (never-claimed) task is corruption, not a
        false positive — no synthesized FAILED precedes it."""
        _ep(make_event)
        _c(make_event, "t1")
        _done(make_event, "t1")
        try:
            orch_core.reduce_all()
            assert False, "expected IllegalTransition (task never claimed)"
        except orch_core.IllegalTransition:
            pass

    def test_front_incident_log_reduces(self, orch_dir, make_event):
        """Reconstruction of the middleware-ifs `front` task (seq 167..173): claim,
        two progress, hook-synthesized failure, late progress, late completion — with
        NO retry advancing the attempt. Before F2 seq-173 poisoned reduce_all()."""
        _ep(make_event)
        _c(make_event, "front")
        _cl(make_event, "front")
        _prog(make_event, "front", note="context_loaded")
        _prog(make_event, "front", note="analysis_complete")
        _f(make_event, "front", "worker_exited_without_terminal")   # premature hook terminal
        _prog(make_event, "front", note="draft_written")            # worker was alive
        _done(make_event, "front")

        state = orch_core.reduce_all()   # the whole point: no longer irreducible
        assert state.tasks["front"].status == orch_core.TaskStatus.COMPLETED
        assert "reconciled_false_positive_completion" in _anomaly_reasons(state)

    def test_retried_track_still_supersedes_late_completion(self, orch_dir, make_event):
        """When a retry DID advance the attempt, the original worker's late completion
        stays a superseded no-op (existing straggler guard), NOT a reconciliation."""
        _ep(make_event)
        _c(make_event, "t1")
        _cl(make_event, "t1")
        ev = make_event("task_failed", task_id="t1", attempt=1, data={
            "phase": "dev", "reason": "stale_timeout", "retryable": True})
        make_event("task_scheduled_retry", task_id="t1", data={
            "phase": "dev", "next_retry_at": "2026-01-01T00:00:00+00:00",
            "backoff_seconds": 30, "previous_failure_seq": ev.seq})
        make_event("task_retried", task_id="t1", attempt=2, data={
            "phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": ev.seq + 1})
        _done(make_event, "t1", attempt=1)   # attempt-1 straggler; task is on attempt 2

        state = orch_core.reduce_all()
        assert state.tasks["t1"].attempts == 2
        assert state.tasks["t1"].status in (
            orch_core.TaskStatus.READY, orch_core.TaskStatus.PENDING)
        # Superseded straggler is NOT a false-positive reconciliation.
        assert "reconciled_false_positive_completion" not in _anomaly_reasons(state)
