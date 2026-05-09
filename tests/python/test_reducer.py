"""
Reducer tests — one per EventType (27 total) + idempotency + pure-function invariant.

Each test appends the minimal prerequisite events, then the event under test,
calls reduce_all(), and asserts the expected state change.
"""
import copy
import json
import os
import sys
from pathlib import Path

import pytest

# conftest.py injects LIB into sys.path before this file loads.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(orch_dir):
    import orch_core
    return orch_core.reduce_all()


def _task_created_data(**overrides) -> dict:
    base = {
        "phase": "sdd",
        "tier": "standard",
        "type": "spec",
        "spec": "Build feature X",
        "deps": [],
    }
    base.update(overrides)
    return base


def _claimed_data(**overrides) -> dict:
    base = {"phase": "sdd", "worker_type": "spec-worker", "worker_id": "wkr-001"}
    base.update(overrides)
    return base


def _setup_phase(make_event, phase: str = "sdd"):
    """Declares and enters a phase so tasks become READY automatically."""
    make_event("phase_declared", data={
        "workflow_id": "wf-test",
        "phases": [{"name": phase, "order": 1, "required": True}],
    })
    make_event("phase_entered", data={"phase": phase, "order": 1, "workflow_id": "wf-test"})


# ---------------------------------------------------------------------------
# Task lifecycle — 9 event types
# ---------------------------------------------------------------------------

class TestTaskCreated:
    def test_creates_task_in_pending_status(self, orch_dir, make_event):
        import orch_core
        make_event("task_created", task_id="t1", data=_task_created_data())
        s = orch_core.reduce_all()
        assert "t1" in s.tasks
        assert s.tasks["t1"].status == orch_core.TaskStatus.PENDING

    def test_sets_tier_and_phase(self, orch_dir, make_event):
        import orch_core
        make_event("task_created", task_id="t1", data=_task_created_data(tier="critical", phase="dev"))
        s = orch_core.reduce_all()
        assert s.tasks["t1"].tier == "critical"
        assert s.tasks["t1"].phase == "dev"

    def test_sets_deps(self, orch_dir, make_event):
        import orch_core
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_created", task_id="t2", data=_task_created_data(deps=["t1"]))
        s = orch_core.reduce_all()
        assert s.tasks["t2"].deps == ["t1"]


class TestTaskClaimed:
    def test_moves_status_to_running(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.RUNNING

    def test_sets_worker_id(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data(worker_id="wkr-42"))
        s = orch_core.reduce_all()
        assert s.tasks["t1"].worker_id == "wkr-42"


class TestTaskProgress:
    def test_does_not_change_status(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        make_event("task_progress", task_id="t1", data={"phase": "sdd", "note": "50% done"})
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.RUNNING

    def test_updates_last_event_at(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        make_event("task_progress", task_id="t1", data={"phase": "sdd", "note": "halfway"})
        s = orch_core.reduce_all()
        assert s.tasks["t1"].last_event_at is not None


class TestTaskCompleted:
    def test_moves_status_to_completed(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        make_event("task_completed", task_id="t1", data={"phase": "sdd", "artifacts": ["spec.md"]})
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.COMPLETED

    def test_stores_artifacts(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        make_event("task_completed", task_id="t1", data={"phase": "sdd", "artifacts": ["a.md", "b.md"]})
        s = orch_core.reduce_all()
        assert s.tasks["t1"].artifacts == ["a.md", "b.md"]


class TestTaskFailed:
    def test_moves_status_to_failed(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        make_event("task_failed", task_id="t1", data={
            "phase": "sdd", "reason": "internal_error", "retryable": True
        })
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.FAILED

    def test_records_failure_timestamp_for_circuit_breaker(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        make_event("task_failed", task_id="t1", data={
            "phase": "sdd", "reason": "internal_error", "retryable": True
        })
        s = orch_core.reduce_all()
        assert len(s.failure_timestamps) == 1


class TestTaskScheduledRetry:
    def test_moves_status_to_scheduled(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        e_fail = make_event("task_failed", task_id="t1", data={
            "phase": "sdd", "reason": "internal_error", "retryable": True
        })
        make_event("task_scheduled_retry", task_id="t1", data={
            "phase": "sdd",
            "next_retry_at": "2099-01-01T00:00:00.000Z",
            "backoff_seconds": 30,
            "previous_failure_seq": e_fail.seq,
        })
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.SCHEDULED


class TestTaskRetried:
    def test_increments_attempt_and_resets_to_pending(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        e_fail = make_event("task_failed", task_id="t1", data={
            "phase": "sdd", "reason": "internal_error", "retryable": True
        })
        e_sched = make_event("task_scheduled_retry", task_id="t1", data={
            "phase": "sdd",
            "next_retry_at": "2099-01-01T00:00:00.000Z",
            "backoff_seconds": 30,
            "previous_failure_seq": e_fail.seq,
        })
        make_event("task_retried", task_id="t1", attempt=2, data={
            "phase": "sdd",
            "previous_attempt": 1,
            "scheduled_retry_seq": e_sched.seq,
        })
        s = orch_core.reduce_all()
        assert s.tasks["t1"].attempts == 2
        assert s.tasks["t1"].status in (
            orch_core.TaskStatus.PENDING, orch_core.TaskStatus.READY
        )


class TestTaskDLQ:
    def test_moves_status_to_dlq(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        make_event("task_failed", task_id="t1", data={
            "phase": "sdd", "reason": "internal_error", "retryable": False
        })
        make_event("task_dlq", task_id="t1", data={
            "phase": "sdd", "reason": "max_attempts_exceeded", "last_error": "crashed"
        })
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.DLQ


class TestTaskSkipped:
    def test_moves_status_to_skipped(self, orch_dir, make_event):
        import orch_core
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_skipped", task_id="t1", data={
            "phase": "sdd", "reason": "implementation_only_no_spec_change"
        })
        s = orch_core.reduce_all()
        assert s.tasks["t1"].status == orch_core.TaskStatus.SKIPPED


# ---------------------------------------------------------------------------
# Phase lifecycle — 7 event types
# ---------------------------------------------------------------------------

def _phase_declared_data(phases=None, workflow_id="wf-001") -> dict:
    return {
        "workflow_id": workflow_id,
        "phases": phases or [
            {"name": "sdd", "order": 1, "required": True},
            {"name": "dev", "order": 2, "required": True},
        ],
    }


class TestPhaseDeclared:
    def test_populates_phases(self, orch_dir, make_event):
        import orch_core
        make_event("phase_declared", data=_phase_declared_data())
        s = orch_core.reduce_all()
        assert "sdd" in s.phases
        assert "dev" in s.phases

    def test_sets_workflow_id(self, orch_dir, make_event):
        import orch_core
        make_event("phase_declared", data=_phase_declared_data(workflow_id="wf-99"))
        s = orch_core.reduce_all()
        assert s.workflow_id == "wf-99"


class TestPhaseEntered:
    def test_sets_current_phase_and_status(self, orch_dir, make_event):
        import orch_core
        make_event("phase_declared", data=_phase_declared_data())
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-001"})
        s = orch_core.reduce_all()
        assert s.current_phase == "sdd"
        assert s.phases["sdd"].status == orch_core.PhaseStatus.ACTIVE


class TestPhaseExitCriterionMet:
    def test_records_criterion(self, orch_dir, make_event):
        import orch_core
        make_event("phase_declared", data=_phase_declared_data())
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-001"})
        make_event("phase_exit_criterion_met", data={"phase": "sdd", "criterion": "all_tasks_done"})
        s = orch_core.reduce_all()
        assert "all_tasks_done" in s.phases["sdd"].criteria_met


class TestPhaseExitApproved:
    def test_sets_status_exit_approved(self, orch_dir, make_event):
        import orch_core
        make_event("phase_declared", data=_phase_declared_data())
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-001"})
        make_event("phase_exit_approved", data={
            "phase": "sdd", "criteria_met": ["all_tasks_done"], "next_phase": "dev", "workflow_id": "wf-001"
        })
        s = orch_core.reduce_all()
        assert s.phases["sdd"].status == orch_core.PhaseStatus.EXIT_APPROVED


class TestPhaseTransitioned:
    def test_advances_current_phase(self, orch_dir, make_event):
        import orch_core
        make_event("phase_declared", data=_phase_declared_data())
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-001"})
        make_event("phase_exit_approved", data={
            "phase": "sdd", "criteria_met": ["done"], "next_phase": "dev", "workflow_id": "wf-001"
        })
        e_approved = make_event("phase_exit_approved", data={
            "phase": "sdd", "criteria_met": ["done"], "next_phase": "dev", "workflow_id": "wf-001"
        })
        make_event("phase_transitioned", data={
            "from_phase": "sdd", "to_phase": "dev",
            "evidence_seq": e_approved.seq, "workflow_id": "wf-001"
        })
        s = orch_core.reduce_all()
        assert s.phases["sdd"].status == orch_core.PhaseStatus.COMPLETED


class TestPhasePaused:
    def test_sets_status_paused(self, orch_dir, make_event):
        import orch_core
        make_event("phase_declared", data=_phase_declared_data())
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-001"})
        make_event("phase_paused", data={"phase": "sdd", "reason": "waiting_for_human"})
        s = orch_core.reduce_all()
        assert s.phases["sdd"].status == orch_core.PhaseStatus.PAUSED


class TestPhaseResumed:
    def test_sets_status_active_after_pause(self, orch_dir, make_event):
        import orch_core
        make_event("phase_declared", data=_phase_declared_data())
        make_event("phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-001"})
        e_pause = make_event("phase_paused", data={"phase": "sdd", "reason": "waiting_for_human"})
        make_event("phase_resumed", data={"phase": "sdd", "paused_seq": e_pause.seq})
        s = orch_core.reduce_all()
        assert s.phases["sdd"].status == orch_core.PhaseStatus.ACTIVE


# ---------------------------------------------------------------------------
# Improve flow — spec_pipeline_return
# ---------------------------------------------------------------------------

class TestSpecPipelineReturn:
    def test_does_not_crash_reducer(self, orch_dir, make_event):
        import orch_core
        make_event("spec_pipeline_return", data={
            "workflow_id": "wf-001",
            "session_id": "sess-abc",
            "spec_change_status": "applied",
        })
        s = orch_core.reduce_all()
        assert s.last_seq >= 1


# ---------------------------------------------------------------------------
# Dispatch governance — 3 event types
# ---------------------------------------------------------------------------

class TestDispatchDecision:
    def test_appended_without_error(self, orch_dir, make_event):
        import orch_core
        make_event("dispatch_decision", data={})
        s = orch_core.reduce_all()
        assert s.last_seq >= 1


class TestContextBudgetEvaluated:
    def test_appended_without_error(self, orch_dir, make_event):
        import orch_core
        make_event("context_budget_evaluated", data={})
        s = orch_core.reduce_all()
        assert s.last_seq >= 1


class TestOperationModeDeclared:
    def test_appended_without_error(self, orch_dir, make_event):
        import orch_core
        make_event("operation_mode_declared", data={"phase": "sdd", "mode": "full"})
        s = orch_core.reduce_all()
        assert s.last_seq >= 1


# ---------------------------------------------------------------------------
# Management — 7 event types
# ---------------------------------------------------------------------------

class TestCircuitBreakerTripped:
    def test_sets_circuit_breaker_state(self, orch_dir, make_event):
        import orch_core
        make_event("circuit_breaker_tripped", data={
            "window_start": "2026-01-01T00:00:00.000Z",
            "window_end": "2026-01-01T00:10:00.000Z",
            "failure_count": 55,
            "threshold": 50,
        })
        s = orch_core.reduce_all()
        assert s.circuit_breaker is not None


class TestEscalation:
    def test_records_escalation(self, orch_dir, make_event):
        import orch_core
        make_event("escalation", data={
            "code": "E01",
            "severity": "critical",
            "reason": "deadlock",
            "evidence": [1],
        })
        s = orch_core.reduce_all()
        assert s.escalation is not None


class TestHumanResponse:
    def test_appended_without_error(self, orch_dir, make_event):
        import orch_core
        e_esc = make_event("escalation", data={
            "code": "E01", "severity": "critical", "reason": "test", "evidence": []
        })
        make_event("human_response", data={
            "escalation_seq": e_esc.seq,
            "action": "resume",
            "operator": "ops@example.com",
        })
        s = orch_core.reduce_all()
        assert s.last_seq >= 2


class TestSnapshot:
    def test_appended_without_error(self, orch_dir, make_event):
        import orch_core
        make_event("snapshot", data={})
        s = orch_core.reduce_all()
        assert s.last_seq >= 1


class TestLogRecovered:
    def test_appended_without_error(self, orch_dir, make_event):
        import orch_core
        make_event("log_recovered", agent="ops-agent", data={
            "seq_truncated_from": 5,
            "events_removed": 2,
            "operator": "ops@example.com",
            "corrupt_file_path": ".orch/log.jsonl.bak",
        })
        s = orch_core.reduce_all()
        assert s.last_seq >= 1


class TestPreflightFailed:
    def test_appended_without_error(self, orch_dir, make_event):
        import orch_core
        make_event("preflight_failed", data={})
        s = orch_core.reduce_all()
        assert s.last_seq >= 1


class TestOrchestratorHeartbeat:
    def test_appended_without_error(self, orch_dir, make_event):
        import orch_core
        make_event("orchestrator_heartbeat", data={})
        s = orch_core.reduce_all()
        assert s.last_seq >= 1


# ---------------------------------------------------------------------------
# Idempotency — duplicate event must not change state
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_task_failed_on_already_failed_task_is_noop(self, orch_dir, make_event):
        """task_failed on an already-failed task is a no-op (C2 idempotency guard)."""
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        make_event("task_failed", task_id="t1", data={
            "phase": "sdd", "reason": "internal_error", "retryable": True
        })
        s_before = orch_core.reduce_all()
        failure_count_before = len(s_before.failure_timestamps)
        # Second task_failed on same task — should be ignored (C2 guard)
        make_event("task_failed", task_id="t1", data={
            "phase": "sdd", "reason": "internal_error", "retryable": True
        })
        s_after = orch_core.reduce_all()
        # Status stays FAILED, failure_timestamps should not double
        assert s_after.tasks["t1"].status == orch_core.TaskStatus.FAILED
        assert len(s_after.failure_timestamps) == failure_count_before


# ---------------------------------------------------------------------------
# Pure-function invariant (P2)
# ---------------------------------------------------------------------------

class TestPureFunctionInvariant:
    def test_reduce_all_called_twice_produces_identical_state(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1", data=_claimed_data())
        make_event("task_completed", task_id="t1", data={"phase": "sdd", "artifacts": []})

        s1 = orch_core.reduce_all()
        s2 = orch_core.reduce_all()

        assert s1.tasks["t1"].status == s2.tasks["t1"].status
        assert s1.last_seq == s2.last_seq
        assert s1.workflow_id == s2.workflow_id


# ---------------------------------------------------------------------------
# Unknown event type raises
# ---------------------------------------------------------------------------

class TestUnknownEventType:
    def test_apply_event_raises_for_unknown_type(self, orch_dir):
        import orch_core
        state = orch_core.OrchState()
        bad_event = orch_core.Event(
            seq=1,
            event_id="evt_TEST",
            ts="2026-01-01T00:00:00.000Z",
            agent="test",
            event_type="not_a_real_event",
            task_id=None,
            attempt=1,
            data={},
            prev_hash="GENESIS",
            hash="",
        )
        with pytest.raises(orch_core.UnknownEventType):
            orch_core.apply_event(state, bad_event)
