"""
State machine tests — TaskStatus and PhaseStatus transition tables.
Tests that valid transitions produce the correct next status and that
illegal transitions raise or leave state unchanged.
"""
import pytest


def _task_created_data(**kw) -> dict:
    base = {"phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []}
    base.update(kw)
    return base


def _setup_phase(make_event, phase: str = "sdd"):
    make_event("phase_declared", data={
        "workflow_id": "wf-test",
        "phases": [{"name": phase, "order": 1, "required": True}],
    })
    make_event("phase_entered", data={"phase": phase, "order": 1, "workflow_id": "wf-test"})


# ---------------------------------------------------------------------------
# TaskStatus transitions
# ---------------------------------------------------------------------------

class TestTaskStatusTransitions:

    def test_pending_to_running_via_task_claimed(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data={"phase": "sdd", "worker_type": "w", "worker_id": "wid"})
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.RUNNING

    def test_running_to_completed_via_task_completed(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data={"phase": "sdd", "worker_type": "w", "worker_id": "wid"})
        make_event("task_completed", task_id="t1", data={"phase": "sdd", "artifacts": []})
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.COMPLETED

    def test_running_to_failed_via_task_failed(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data={"phase": "sdd", "worker_type": "w", "worker_id": "wid"})
        make_event("task_failed", task_id="t1", data={"phase": "sdd", "reason": "internal_error", "retryable": True})
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.FAILED

    def test_failed_to_scheduled_via_scheduled_retry(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data={"phase": "sdd", "worker_type": "w", "worker_id": "wid"})
        e_fail = make_event("task_failed", task_id="t1", data={"phase": "sdd", "reason": "internal_error", "retryable": True})
        make_event("task_scheduled_retry", task_id="t1", data={
            "phase": "sdd", "next_retry_at": "2099-01-01T00:00:00.000Z",
            "backoff_seconds": 30, "previous_failure_seq": e_fail.seq,
        })
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.SCHEDULED

    def test_scheduled_to_pending_via_task_retried(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data={"phase": "sdd", "worker_type": "w", "worker_id": "wid"})
        e_fail = make_event("task_failed", task_id="t1", data={"phase": "sdd", "reason": "internal_error", "retryable": True})
        e_sched = make_event("task_scheduled_retry", task_id="t1", data={
            "phase": "sdd", "next_retry_at": "2099-01-01T00:00:00.000Z",
            "backoff_seconds": 30, "previous_failure_seq": e_fail.seq,
        })
        make_event("task_retried", task_id="t1", attempt=2, data={
            "phase": "sdd", "previous_attempt": 1, "scheduled_retry_seq": e_sched.seq,
        })
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status in (orch_core.TaskStatus.PENDING, orch_core.TaskStatus.READY)

    def test_failed_to_dlq_via_task_dlq(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data={"phase": "sdd", "worker_type": "w", "worker_id": "wid"})
        make_event("task_failed", task_id="t1", data={"phase": "sdd", "reason": "internal_error", "retryable": False})
        make_event("task_dlq", task_id="t1", data={"phase": "sdd", "reason": "max_attempts_exceeded", "last_error": "err"})
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.DLQ

    def test_pending_to_skipped_via_task_skipped(self, orch_dir, make_event):
        import orch_core
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_skipped", task_id="t1", data={"phase": "sdd", "reason": "implementation_only_no_spec_change"})
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.SKIPPED

    def test_terminal_statuses(self):
        import orch_core
        assert orch_core.TaskStatus.is_terminal(orch_core.TaskStatus.COMPLETED)
        assert orch_core.TaskStatus.is_terminal(orch_core.TaskStatus.DLQ)
        assert orch_core.TaskStatus.is_terminal(orch_core.TaskStatus.SKIPPED)
        assert not orch_core.TaskStatus.is_terminal(orch_core.TaskStatus.PENDING)
        assert not orch_core.TaskStatus.is_terminal(orch_core.TaskStatus.RUNNING)
        assert not orch_core.TaskStatus.is_terminal(orch_core.TaskStatus.FAILED)


# ---------------------------------------------------------------------------
# PhaseStatus transitions
# ---------------------------------------------------------------------------

def _setup_phases(make_event):
    make_event("phase_declared", data={
        "workflow_id": "wf-001",
        "phases": [
            {"name": "sdd", "order": 1, "required": True},
            {"name": "dev", "order": 2, "required": True},
        ],
    })


class TestPhaseStatusTransitions:

    def test_pending_to_active_via_phase_entered(self, orch_dir, make_event):
        import orch_core
        _setup_phases(make_event)
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-001"})
        s = orch_core.reduce_all()
        assert s.phases["sdd"].status == orch_core.PhaseStatus.ACTIVE

    def test_active_to_exit_approved(self, orch_dir, make_event):
        import orch_core
        _setup_phases(make_event)
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-001"})
        make_event("phase_exit_approved", data={
            "phase": "sdd", "criteria_met": ["done"], "next_phase": "dev", "workflow_id": "wf-001"
        })
        s = orch_core.reduce_all()
        assert s.phases["sdd"].status == orch_core.PhaseStatus.EXIT_APPROVED

    def test_exit_approved_to_completed_via_phase_transitioned(self, orch_dir, make_event):
        import orch_core
        _setup_phases(make_event)
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-001"})
        e_approved = make_event("phase_exit_approved", data={
            "phase": "sdd", "criteria_met": ["done"], "next_phase": "dev", "workflow_id": "wf-001"
        })
        make_event("phase_transitioned", data={
            "from_phase": "sdd", "to_phase": "dev",
            "evidence_seq": e_approved.seq, "workflow_id": "wf-001"
        })
        s = orch_core.reduce_all()
        assert s.phases["sdd"].status == orch_core.PhaseStatus.COMPLETED

    def test_active_to_paused(self, orch_dir, make_event):
        import orch_core
        _setup_phases(make_event)
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-001"})
        make_event("phase_paused", data={"phase": "sdd", "reason": "waiting"})
        s = orch_core.reduce_all()
        assert s.phases["sdd"].status == orch_core.PhaseStatus.PAUSED

    def test_paused_to_active_via_phase_resumed(self, orch_dir, make_event):
        import orch_core
        _setup_phases(make_event)
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-001"})
        e_pause = make_event("phase_paused", data={"phase": "sdd", "reason": "waiting"})
        make_event("phase_resumed", data={"phase": "sdd", "paused_seq": e_pause.seq})
        s = orch_core.reduce_all()
        assert s.phases["sdd"].status == orch_core.PhaseStatus.ACTIVE


# ---------------------------------------------------------------------------
# Event validation — required field enforcement
# ---------------------------------------------------------------------------

class TestEventValidation:

    def test_task_created_missing_phase_raises(self, orch_dir):
        import orch_core
        with pytest.raises(orch_core.EventValidationError):
            orch_core.append_event(
                "test", "task_created", task_id="t1",
                data={"tier": "standard", "type": "spec", "spec": "x", "deps": []}
                # missing "phase"
            )

    def test_task_created_invalid_tier_raises(self, orch_dir):
        import orch_core
        with pytest.raises(orch_core.EventValidationError):
            orch_core.append_event(
                "test", "task_created", task_id="t1",
                data={"phase": "sdd", "tier": "ultra", "type": "spec", "spec": "x", "deps": []}
            )

    def test_task_failed_invalid_reason_raises(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data={"phase": "sdd", "worker_type": "w", "worker_id": "wid"})
        with pytest.raises(orch_core.EventValidationError):
            orch_core.append_event(
                "test", "task_failed", task_id="t1",
                data={"phase": "sdd", "reason": "bad_custom_reason", "retryable": False}
            )

    def test_unknown_event_type_raises(self, orch_dir):
        import orch_core
        with pytest.raises(orch_core.UnknownEventType):
            orch_core.append_event("test", "totally_made_up", data={})
