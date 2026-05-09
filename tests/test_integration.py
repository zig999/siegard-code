"""
Integration tests — full workflow sequences verified against reduce_all().

Tests that end-to-end event sequences produce the correct derived state,
exercising the complete path from append_event → log → reduce_all → OrchState.
"""
import pytest


def _task_created_data(**kw):
    base = {"phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Spec → Dev phase transition
# ---------------------------------------------------------------------------

class TestSpecDevTransition:
    """
    Simulates a full SDD → DEV phase transition:
    1. Declare phases
    2. Enter SDD
    3. Create and complete two spec tasks
    4. Mark exit criterion met, approve, transition
    5. Enter DEV phase
    6. Assert derived state: phases["sdd"].status == COMPLETED, current_phase == "dev"
    """

    def test_full_sdd_to_dev_transition(self, orch_dir, make_event):
        import orch_core

        # Step 1: Declare phases
        make_event("phase_declared", data={
            "workflow_id": "wf-int-001",
            "phases": [
                {"name": "sdd", "order": 1, "required": True},
                {"name": "dev", "order": 2, "required": True},
            ],
        })

        # Step 2: Enter SDD
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-int-001"})

        # Step 3: Create and complete two tasks
        make_event("task_created", task_id="spec-01", data=_task_created_data(phase="sdd"))
        make_event("task_claimed", task_id="spec-01",
                   data={"phase": "sdd", "worker_type": "spec-w", "worker_id": "w-01"})
        make_event("task_completed", task_id="spec-01", data={"phase": "sdd", "artifacts": ["spec1.md"]})

        make_event("task_created", task_id="spec-02", data=_task_created_data(phase="sdd"))
        make_event("task_claimed", task_id="spec-02",
                   data={"phase": "sdd", "worker_type": "spec-w", "worker_id": "w-02"})
        make_event("task_completed", task_id="spec-02", data={"phase": "sdd", "artifacts": ["spec2.md"]})

        # Step 4: Exit criterion → approve → transition
        make_event("phase_exit_criterion_met", data={"phase": "sdd", "criterion": "all_spec_tasks_done"})
        e_approved = make_event("phase_exit_approved", data={
            "phase": "sdd",
            "criteria_met": ["all_spec_tasks_done"],
            "next_phase": "dev",
            "workflow_id": "wf-int-001",
        })
        make_event("phase_transitioned", data={
            "from_phase": "sdd", "to_phase": "dev",
            "evidence_seq": e_approved.seq, "workflow_id": "wf-int-001",
        })

        # Step 5: Enter DEV
        make_event("phase_entered", data={"phase": "dev", "order": 2, "workflow_id": "wf-int-001"})

        # Assert
        state = orch_core.reduce_all()
        assert state.phases["sdd"].status == orch_core.PhaseStatus.COMPLETED
        assert state.phases["dev"].status == orch_core.PhaseStatus.ACTIVE
        assert state.current_phase == "dev"
        assert state.tasks["spec-01"].status == orch_core.TaskStatus.COMPLETED
        assert state.tasks["spec-02"].status == orch_core.TaskStatus.COMPLETED


# ---------------------------------------------------------------------------
# Retry cycle: failure → scheduled_retry → retried → completed
# ---------------------------------------------------------------------------

class TestRetryCycle:

    def test_task_succeeds_on_second_attempt(self, orch_dir, make_event):
        import orch_core

        # Need active phase for task to transition PENDING → READY
        make_event("phase_declared", data={
            "workflow_id": "wf-retry", "phases": [{"name": "sdd", "order": 1, "required": True}]
        })
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-retry"})

        make_event("task_created", task_id="t-retry", data=_task_created_data())
        make_event("task_claimed", task_id="t-retry",
                   data={"phase": "sdd", "worker_type": "w", "worker_id": "wid-01"})
        e_fail = make_event("task_failed", task_id="t-retry",
                            data={"phase": "sdd", "reason": "internal_error", "retryable": True})
        e_sched = make_event("task_scheduled_retry", task_id="t-retry", data={
            "phase": "sdd", "next_retry_at": "2099-01-01T00:00:00.000Z",
            "backoff_seconds": 30, "previous_failure_seq": e_fail.seq,
        })
        make_event("task_retried", task_id="t-retry", attempt=2, data={
            "phase": "sdd", "previous_attempt": 1, "scheduled_retry_seq": e_sched.seq,
        })
        make_event("task_claimed", task_id="t-retry", attempt=2,
                   data={"phase": "sdd", "worker_type": "w", "worker_id": "wid-02"})
        make_event("task_completed", task_id="t-retry", attempt=2,
                   data={"phase": "sdd", "artifacts": ["result.md"]})

        state = orch_core.reduce_all()
        assert state.tasks["t-retry"].status == orch_core.TaskStatus.COMPLETED
        assert state.tasks["t-retry"].attempts == 2


# ---------------------------------------------------------------------------
# DLQ cascade: dep task enters DLQ → downstream deadlock
# ---------------------------------------------------------------------------

class TestDLQCascadeDeadlock:

    def test_dlq_dep_creates_deadlock(self, orch_dir, make_event):
        import orch_core

        make_event("phase_declared", data={
            "workflow_id": "wf-dlq", "phases": [{"name": "sdd", "order": 1, "required": True}]
        })
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-dlq"})

        # t1 → DLQ; t2 depends on t1
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1",
                   data={"phase": "sdd", "worker_type": "w", "worker_id": "w01"})
        make_event("task_failed", task_id="t1",
                   data={"phase": "sdd", "reason": "internal_error", "retryable": False})
        make_event("task_dlq", task_id="t1",
                   data={"phase": "sdd", "reason": "max_attempts_exceeded", "last_error": "err"})

        make_event("task_created", task_id="t2", data=_task_created_data(deps=["t1"]))

        state = orch_core.reduce_all()
        assert state.tasks["t1"].status == orch_core.TaskStatus.DLQ
        assert state.tasks["t2"].status == orch_core.TaskStatus.PENDING
        assert orch_core.detect_deadlock(state) is True


# ---------------------------------------------------------------------------
# P2 invariant: reduce_all on identical log is identical
# ---------------------------------------------------------------------------

class TestReduceAllIdempotency:

    def test_identical_state_on_repeated_reduce(self, orch_dir, make_event):
        import orch_core

        make_event("phase_declared", data={
            "workflow_id": "wf-idem", "phases": [{"name": "sdd", "order": 1, "required": True}]
        })
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-idem"})
        for i in range(3):
            make_event("task_created", task_id=f"t{i}", data=_task_created_data())
        make_event("task_claimed", task_id="t0",
                   data={"phase": "sdd", "worker_type": "w", "worker_id": "w0"})
        make_event("task_completed", task_id="t0", data={"phase": "sdd", "artifacts": []})

        s1 = orch_core.reduce_all()
        s2 = orch_core.reduce_all()
        s3 = orch_core.reduce_all()

        for s in (s2, s3):
            assert s.last_seq == s1.last_seq
            assert set(s.tasks.keys()) == set(s1.tasks.keys())
            for tid in s.tasks:
                assert s.tasks[tid].status == s1.tasks[tid].status


# ---------------------------------------------------------------------------
# Escalation flow
# ---------------------------------------------------------------------------

class TestEscalationFlow:

    def test_escalation_sets_run_status_escalated(self, orch_dir, make_event):
        import orch_core

        make_event("escalation", data={
            "code": "E03",
            "severity": "critical",
            "reason": "deadlock_detected",
            "evidence": [],
        })

        state = orch_core.reduce_all()
        assert state.escalation is not None
        assert state.run_status == "escalated"

    def test_human_response_clears_escalation(self, orch_dir, make_event):
        import orch_core

        e_esc = make_event("escalation", data={
            "code": "E03",
            "severity": "critical",
            "reason": "deadlock_detected",
            "evidence": [],
        })
        make_event("human_response", data={
            "escalation_seq": e_esc.seq,
            "action": "resume",
            "operator": "oncall@example.com",
        })

        state = orch_core.reduce_all()
        # human_response clears escalation and restores run_status
        assert state.escalation is None
        assert state.run_status == "active"
