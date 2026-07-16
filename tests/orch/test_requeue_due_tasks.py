"""Tests for requeue_due_tasks.py (recommendation #4, 2026-07-15 workflow audit —
"A1: busy-spin backoff + lost retry").

Covers the pure `requeue()` core: promoting due SCHEDULED tasks, resolving lingering
FAILED tasks (schedule or DLQ), phase/workflow scoping, and the --protect-task-types
exclusion that keeps sdd's rejection-cycle task types (spec-writer, spec-validator)
untouched so their own lower-threshold escalation still fires.
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "dist" / ".claude" / "scripts"

_spec = importlib.util.spec_from_file_location("requeue_due_tasks", SCRIPTS / "requeue_due_tasks.py")
requeue_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(requeue_mod)

_NOW = "2026-01-01T00:00:00.000Z"
_PAST = "2020-01-01T00:00:00.000Z"


def _seed_phase(orch_core, phase="dev", wf="wf-req"):
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": wf, "phases": [{"name": phase, "order": 1, "required": True}]})
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": phase, "order": 1, "workflow_id": wf})


def _create_claim_fail(orch_core, tid, phase="dev", task_type="impl", attempt=1,
                        reason="validation_failed", retryable=True, wf="wf-req"):
    orch_core.append_event(
        agent="orchestrator", event_type="task_created", task_id=tid,
        data={"phase": phase, "tier": "standard", "type": task_type, "spec": "s",
              "deps": [], "workflow_id": wf})
    orch_core.append_event(
        agent="orchestrator", event_type="task_claimed", task_id=tid,
        data={"phase": phase, "worker_type": "w", "worker_id": "w1"})
    failed = orch_core.append_event(
        agent="w1", event_type="task_failed", task_id=tid, attempt=attempt,
        data={"phase": phase, "reason": reason, "retryable": retryable})
    return failed


def test_promotes_due_scheduled_task_to_retried(tmp_orch):
    import orch_core
    _seed_phase(orch_core)
    f = _create_claim_fail(orch_core, "t1")
    orch_core.append_event(
        agent="o", event_type="task_scheduled_retry", task_id="t1",
        data={"phase": "dev", "next_retry_at": _PAST, "backoff_seconds": 1,
              "previous_failure_seq": f.seq})

    out = requeue_mod.requeue(now=_NOW)
    assert out["retried"] == ["t1"]
    state = orch_core.reduce_all()
    assert state.tasks["t1"].status in (orch_core.TaskStatus.READY, orch_core.TaskStatus.PENDING)


def test_does_not_promote_scheduled_task_not_yet_due(tmp_orch):
    import orch_core
    _seed_phase(orch_core)
    f = _create_claim_fail(orch_core, "t1")
    future = "2099-01-01T00:00:00.000Z"
    orch_core.append_event(
        agent="o", event_type="task_scheduled_retry", task_id="t1",
        data={"phase": "dev", "next_retry_at": future, "backoff_seconds": 1,
              "previous_failure_seq": f.seq})

    out = requeue_mod.requeue(now=_NOW)
    assert out["retried"] == []
    assert out["earliest_pending_retry_at"] == future
    state = orch_core.reduce_all()
    assert state.tasks["t1"].status == orch_core.TaskStatus.SCHEDULED


def test_lingering_failed_retryable_task_gets_scheduled(tmp_orch):
    """The Step 5.5 gap: a worker-reported failure with no schedule yet, from a
    turn that ended before Step 5.5 ran."""
    import orch_core
    _seed_phase(orch_core)
    _create_claim_fail(orch_core, "t1", attempt=1)  # standard tier: max_attempts=3

    out = requeue_mod.requeue(now=_NOW)
    assert out["scheduled"] == ["t1"]
    state = orch_core.reduce_all()
    assert state.tasks["t1"].status == orch_core.TaskStatus.SCHEDULED
    assert state.tasks["t1"].next_retry_at is not None


def test_lingering_failed_exhausted_task_routes_to_dlq(tmp_orch):
    import orch_core
    _seed_phase(orch_core)
    _create_claim_fail(orch_core, "t1", attempt=3)  # standard tier max_attempts=3 -> exhausted

    out = requeue_mod.requeue(now=_NOW)
    assert out["dlq_routed"] == ["t1"]
    state = orch_core.reduce_all()
    assert state.tasks["t1"].status == orch_core.TaskStatus.DLQ


def test_lingering_failed_non_retryable_routes_to_dlq(tmp_orch):
    import orch_core
    _seed_phase(orch_core)
    _create_claim_fail(orch_core, "t1", attempt=1, reason="schema_violation", retryable=False)

    out = requeue_mod.requeue(now=_NOW)
    assert out["dlq_routed"] == ["t1"]
    state = orch_core.reduce_all()
    assert state.tasks["t1"].status == orch_core.TaskStatus.DLQ


def test_phase_scoping_ignores_other_phases(tmp_orch):
    import orch_core
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": "wf-req",
              "phases": [{"name": "dev", "order": 1, "required": True},
                         {"name": "review", "order": 2, "required": True}]})
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": "dev", "order": 1, "workflow_id": "wf-req"})
    _create_claim_fail(orch_core, "dev_t1", phase="dev", attempt=1)

    out = requeue_mod.requeue(now=_NOW, phase="review")
    assert out == {"retried": [], "scheduled": [], "dlq_routed": [],
                   "earliest_pending_retry_at": None, "waited_seconds": 0.0}
    state = orch_core.reduce_all()
    assert state.tasks["dev_t1"].status == orch_core.TaskStatus.FAILED  # untouched


def test_workflow_id_scoping_ignores_other_workflows(tmp_orch):
    import orch_core
    _seed_phase(orch_core, wf="wf-a")
    _create_claim_fail(orch_core, "t1", attempt=1, wf="wf-a")

    out = requeue_mod.requeue(now=_NOW, phase="dev", workflow_id="wf-b")
    assert out == {"retried": [], "scheduled": [], "dlq_routed": [],
                   "earliest_pending_retry_at": None, "waited_seconds": 0.0}
    state = orch_core.reduce_all()
    assert state.tasks["t1"].status == orch_core.TaskStatus.FAILED  # untouched


def test_protected_task_type_left_failed_for_own_escalation(tmp_orch):
    """sdd's rejection-cycle check (spec-validator >= 2 attempts) fires at a LOWER
    threshold than the tier's generic max_attempts (3) — without protection this
    script would schedule another retry and let it reach attempt 3, silently
    skipping the human escalation."""
    import orch_core
    _seed_phase(orch_core, phase="sdd")
    _create_claim_fail(orch_core, "sv1", phase="sdd", task_type="spec-validator", attempt=2)

    out = requeue_mod.requeue(
        now=_NOW, phase="sdd", protect_task_types=frozenset({"spec-writer", "spec-validator"}))
    assert out == {"retried": [], "scheduled": [], "dlq_routed": [],
                   "earliest_pending_retry_at": None, "waited_seconds": 0.0}
    state = orch_core.reduce_all()
    assert state.tasks["sv1"].status == orch_core.TaskStatus.FAILED


def test_unprotected_spec_validator_would_be_rescheduled(tmp_orch):
    """Contrast case proving the protection above is load-bearing, not a no-op."""
    import orch_core
    _seed_phase(orch_core, phase="sdd")
    _create_claim_fail(orch_core, "sv1", phase="sdd", task_type="spec-validator", attempt=2)

    out = requeue_mod.requeue(now=_NOW, phase="sdd")
    assert out["scheduled"] == ["sv1"]
    state = orch_core.reduce_all()
    assert state.tasks["sv1"].status == orch_core.TaskStatus.SCHEDULED


# ---------------------------------------------------------------- wait window

class TestWaitWindow:
    """--wait-window (2026-07-15 post-fix audit, "double-resume tax").

    A reap-and-schedule pass leaves the retry ~24-36s in the future; without the
    wait, the invocation ends "blocked on backoff" and dispatching the retry
    costs a full supervisor cycle (heartbeat threshold + tick interval, 15-25
    min) or a second human invocation. Within the window, the tick waits out
    the backoff and promotes in the same call.
    """

    def _sleep_recorder(self, monkeypatch):
        calls = []
        monkeypatch.setattr(requeue_mod.time, "sleep", calls.append)
        return calls

    def _schedule(self, orch_core, f, retry_at):
        orch_core.append_event(
            agent="o", event_type="task_scheduled_retry", task_id="t1",
            data={"phase": "dev", "next_retry_at": retry_at, "backoff_seconds": 30,
                  "previous_failure_seq": f.seq})

    def test_waits_out_near_backoff_and_promotes_same_call(self, tmp_orch, monkeypatch):
        import orch_core
        sleeps = self._sleep_recorder(monkeypatch)
        _seed_phase(orch_core)
        f = _create_claim_fail(orch_core, "t1")
        self._schedule(orch_core, f, "2026-01-01T00:00:30.000Z")  # due 30s after _NOW

        out = requeue_mod.requeue(now=_NOW, wait_window_s=90.0)
        assert out["retried"] == ["t1"]
        assert out["waited_seconds"] == 30.0
        assert sleeps == [30.0]
        assert out["earliest_pending_retry_at"] is None
        state = orch_core.reduce_all()
        assert state.tasks["t1"].status in (orch_core.TaskStatus.READY, orch_core.TaskStatus.PENDING)

    def test_does_not_wait_beyond_window(self, tmp_orch, monkeypatch):
        import orch_core
        sleeps = self._sleep_recorder(monkeypatch)
        _seed_phase(orch_core)
        f = _create_claim_fail(orch_core, "t1")
        self._schedule(orch_core, f, "2026-01-01T00:05:00.000Z")  # due 300s after _NOW

        out = requeue_mod.requeue(now=_NOW, wait_window_s=90.0)
        assert out["retried"] == []
        assert out["waited_seconds"] == 0.0
        assert sleeps == []
        assert out["earliest_pending_retry_at"] == "2026-01-01T00:05:00.000Z"

    def test_does_not_wait_when_work_is_dispatchable(self, tmp_orch, monkeypatch):
        """A READY sibling means the loop has real work — never block it."""
        import orch_core
        sleeps = self._sleep_recorder(monkeypatch)
        _seed_phase(orch_core)
        f = _create_claim_fail(orch_core, "t1")
        self._schedule(orch_core, f, "2026-01-01T00:00:30.000Z")
        orch_core.append_event(
            agent="orchestrator", event_type="task_created", task_id="t2",
            data={"phase": "dev", "tier": "standard", "type": "impl", "spec": "s",
                  "deps": [], "workflow_id": "wf-req"})  # promotes to READY

        out = requeue_mod.requeue(now=_NOW, wait_window_s=90.0)
        assert sleeps == []
        assert out["waited_seconds"] == 0.0
        assert out["earliest_pending_retry_at"] == "2026-01-01T00:00:30.000Z"

    def test_default_is_disabled(self, tmp_orch, monkeypatch):
        import orch_core
        sleeps = self._sleep_recorder(monkeypatch)
        _seed_phase(orch_core)
        f = _create_claim_fail(orch_core, "t1")
        self._schedule(orch_core, f, "2026-01-01T00:00:30.000Z")

        out = requeue_mod.requeue(now=_NOW)
        assert sleeps == []
        assert out["retried"] == []
        assert out["waited_seconds"] == 0.0
