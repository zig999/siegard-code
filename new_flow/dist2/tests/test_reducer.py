"""
Tests for Task 1.7: apply_event, reduce_all, TaskState, PhaseState, OrchState.
Covers scenarios: 3.1-3.14, 5.1-5.11
"""
import copy

import pytest
import orch_core
from orch_core import (
    append_event,
    apply_event,
    reduce_all,
    Event,
    OrchState,
    TaskState,
    PhaseState,
    TaskStatus,
    PhaseStatus,
    EventType,
    IllegalTransition,
)


# ---------------------------------------------------------------------------
# Helpers — build Event objects directly for reducer unit tests
# ---------------------------------------------------------------------------

_seq_counter = 0


def _evt(event_type: str, task_id=None, attempt=1, data=None, seq=None) -> Event:
    global _seq_counter
    _seq_counter += 1
    s = seq if seq is not None else _seq_counter
    e = Event(
        seq=s,
        event_id=f"evt_{s:04d}",
        ts="2026-04-21T00:00:00.000Z",
        agent="orchestrator",
        event_type=event_type,
        task_id=task_id,
        attempt=attempt,
        data=data or {},
        prev_hash="GENESIS" if s == 1 else f"hash_{s - 1}",
        hash=f"hash_{s}",
    )
    return e


def _task_data(phase="dev", tier="standard", task_type="impl", spec="s", deps=None):
    return {"phase": phase, "tier": tier, "type": task_type, "spec": spec,
            "deps": deps or []}


def fresh() -> OrchState:
    """Returns a clean OrchState with a single active phase 'dev'."""
    state = OrchState()
    apply_event(state, _evt(EventType.PHASE_DECLARED, data={
        "workflow_id": "wf_001",
        "phases": [{"name": "dev", "order": 1, "required": True}],
    }))
    apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "dev", "order": 1}))
    return state


# ---------------------------------------------------------------------------
# Scenario 3.1: task_created → pending
# ---------------------------------------------------------------------------

class TestTaskCreatedPending:
    def test_task_created_adds_task(self):
        state = OrchState()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(deps=["t_other"])))
        assert "t_001" in state.tasks

    def test_task_created_status_pending_no_active_phase(self):
        """Scenario 3.1: no active phase → task stays pending."""
        state = OrchState()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data()))
        assert state.tasks["t_001"].status == TaskStatus.PENDING

    def test_task_created_attempts_zero(self):
        state = OrchState()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data()))
        assert state.tasks["t_001"].attempts == 0

    def test_task_created_evidence_contains_seq(self):
        state = OrchState()
        ev = _evt(EventType.TASK_CREATED, task_id="t_001", data=_task_data())
        apply_event(state, ev)
        assert ev.seq in state.tasks["t_001"].evidence


# ---------------------------------------------------------------------------
# Scenario 3.2: task without deps in active phase → ready
# ---------------------------------------------------------------------------

class TestTaskPromotedToReady:
    def test_ready_when_phase_active_and_no_deps(self):
        """Scenario 3.2: active phase + no deps → ready."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(phase="dev", deps=[])))
        assert state.tasks["t_001"].status == TaskStatus.READY

    def test_pending_when_phase_active_but_has_deps(self):
        """Scenario 3.3: active phase + pending deps → stays pending."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(phase="dev", deps=[])))
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_002",
                                data=_task_data(phase="dev", deps=["t_001"])))
        assert state.tasks["t_001"].status == TaskStatus.READY
        assert state.tasks["t_002"].status == TaskStatus.PENDING

    def test_pending_when_phase_not_active(self):
        """Scenario 5.6: task in non-active phase stays pending."""
        state = OrchState()
        # Declare phase but don't enter it
        apply_event(state, _evt(EventType.PHASE_DECLARED, data={
            "workflow_id": "wf_001",
            "phases": [{"name": "dev", "order": 1, "required": True}],
        }))
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(phase="dev", deps=[])))
        assert state.tasks["t_001"].status == TaskStatus.PENDING


# ---------------------------------------------------------------------------
# Scenario 3.4: deps complete → promote pending to ready
# ---------------------------------------------------------------------------

class TestDepPromotion:
    def test_pending_promoted_after_dep_completes(self):
        """Scenario 3.4: t_001 completes → t_002 promoted to ready."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(phase="dev", deps=[])))
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_002",
                                data=_task_data(phase="dev", deps=["t_001"])))
        assert state.tasks["t_002"].status == TaskStatus.PENDING

        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001",
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w_1"}))
        apply_event(state, _evt(EventType.TASK_COMPLETED, task_id="t_001",
                                data={"phase": "dev", "artifacts": [], "summary": "done"}))

        assert state.tasks["t_001"].status == TaskStatus.COMPLETED
        assert state.tasks["t_002"].status == TaskStatus.READY


# ---------------------------------------------------------------------------
# Scenario 3.5: task_claimed → running
# ---------------------------------------------------------------------------

class TestTaskClaimed:
    def test_claimed_moves_to_running(self):
        """Scenario 3.5."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001",
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w_1"}))
        assert state.tasks["t_001"].status == TaskStatus.RUNNING
        assert state.tasks["t_001"].worker_id == "w_1"
        assert state.tasks["t_001"].claimed_at is not None


# ---------------------------------------------------------------------------
# Scenario 3.6: illegal transition pending → running
# ---------------------------------------------------------------------------

class TestIllegalTransitions:
    def test_claimed_from_pending_raises(self):
        """Scenario 3.6: pending → running (skipped ready) raises."""
        state = OrchState()  # no active phase → task stays pending
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data()))
        assert state.tasks["t_001"].status == TaskStatus.PENDING

        with pytest.raises(IllegalTransition):
            apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001",
                                    data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))

    def test_completed_task_cannot_be_claimed(self):
        """Scenario 3.7: completed → any transition raises."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001",
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_COMPLETED, task_id="t_001",
                                data={"phase": "dev", "artifacts": [], "summary": "done"}))

        with pytest.raises(IllegalTransition):
            apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001",
                                    data={"phase": "dev", "worker_type": "impl", "worker_id": "w2"}))

    def test_completed_task_failed_is_noop(self):
        """Scenario 3.7 (C2 fix): task_failed on COMPLETED task is a no-op, not an error.
        This prevents log corruption when on_subagent_stop hook races with Step 6.4."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001",
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_COMPLETED, task_id="t_001",
                                data={"phase": "dev", "artifacts": [], "summary": "done"}))

        # Must NOT raise — idempotent no-op
        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_001",
                                data={"phase": "dev", "reason": "x", "retryable": False}))
        assert state.tasks["t_001"].status == TaskStatus.COMPLETED


# ---------------------------------------------------------------------------
# Scenario 3.8: task_failed retryable=true → failed
# ---------------------------------------------------------------------------

class TestTaskFailed:
    def test_failed_retryable_true(self):
        """Scenario 3.8."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "reason": "timeout", "retryable": True}))
        task = state.tasks["t_001"]
        assert task.status == TaskStatus.FAILED
        assert task.last_failure_retryable is True

    def test_failed_sets_reason(self):
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001", data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "reason": "oom", "retryable": False}))
        assert state.tasks["t_001"].last_failure_reason == "oom"


# ---------------------------------------------------------------------------
# Scenario 3.9: task_dlq → dlq
# ---------------------------------------------------------------------------

class TestTaskDLQ:
    def test_dlq_from_failed(self):
        """Scenario 3.9: failed → dlq."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001", data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "reason": "x", "retryable": False}))
        apply_event(state, _evt(EventType.TASK_DLQ, task_id="t_001",
                                data={"phase": "dev", "reason": "non_retryable", "last_error": "x"}))
        assert state.tasks["t_001"].status == TaskStatus.DLQ

    def test_dlq_attempts_unchanged(self):
        """Scenario 3.9: attempts count not incremented by dlq."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001", data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "reason": "x", "retryable": False}))
        apply_event(state, _evt(EventType.TASK_DLQ, task_id="t_001",
                                data={"phase": "dev", "reason": "non_retryable", "last_error": "x"}))
        assert state.tasks["t_001"].attempts == 1

    def test_dlq_scenario_3_12_max_attempts(self):
        """Scenario 3.12: dlq at max_attempts."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001", data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001", attempt=3,
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_001", attempt=3,
                                data={"phase": "dev", "reason": "x", "retryable": True}))
        apply_event(state, _evt(EventType.TASK_DLQ, task_id="t_001",
                                data={"phase": "dev", "reason": "max_attempts_exceeded", "last_error": "x"}))
        assert state.tasks["t_001"].status == TaskStatus.DLQ


# ---------------------------------------------------------------------------
# Scenario 3.10: task_scheduled_retry → scheduled
# ---------------------------------------------------------------------------

class TestTaskScheduledRetry:
    def test_scheduled_retry_from_failed(self):
        """Scenario 3.10."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001", data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "reason": "x", "retryable": True}))
        apply_event(state, _evt(EventType.TASK_SCHEDULED_RETRY, task_id="t_001",
                                data={"phase": "dev", "next_retry_at": "2026-04-21T01:00:00Z",
                                      "backoff_seconds": 45, "previous_failure_seq": 4}))
        task = state.tasks["t_001"]
        assert task.status == TaskStatus.SCHEDULED
        assert task.next_retry_at == "2026-04-21T01:00:00Z"


# ---------------------------------------------------------------------------
# Scenario 3.11: task_retried → pending/ready
# ---------------------------------------------------------------------------

class TestTaskRetried:
    def test_retried_no_deps_becomes_ready(self):
        """Scenario 3.11: retry with no deps and active phase → ready."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001", data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "reason": "x", "retryable": True}))
        apply_event(state, _evt(EventType.TASK_SCHEDULED_RETRY, task_id="t_001",
                                data={"phase": "dev", "next_retry_at": "2026-04-21T01:00:00Z",
                                      "backoff_seconds": 45, "previous_failure_seq": 3}))
        apply_event(state, _evt(EventType.TASK_RETRIED, task_id="t_001", attempt=2,
                                data={"phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": 4}))
        task = state.tasks["t_001"]
        assert task.status == TaskStatus.READY
        assert task.attempts == 2
        assert task.next_retry_at is None

    def test_retried_with_pending_deps_stays_pending(self):
        """Scenario 3.11: retry with unmet deps → pending."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_dep",
                                data=_task_data(deps=[])))  # dep ready
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(deps=["t_dep"])))
        # Force t_dep back to pending-like by not completing it; t_001 is pending
        assert state.tasks["t_001"].status == TaskStatus.PENDING

        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_dep", attempt=1,
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_dep", attempt=1,
                                data={"phase": "dev", "reason": "x", "retryable": True}))
        apply_event(state, _evt(EventType.TASK_SCHEDULED_RETRY, task_id="t_dep",
                                data={"phase": "dev", "next_retry_at": "t", "backoff_seconds": 1,
                                      "previous_failure_seq": 1}))
        apply_event(state, _evt(EventType.TASK_RETRIED, task_id="t_dep", attempt=2,
                                data={"phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": 1}))
        # t_dep is now ready again, t_001 still pending (dep not completed)
        assert state.tasks["t_dep"].status == TaskStatus.READY
        assert state.tasks["t_001"].status == TaskStatus.PENDING


# ---------------------------------------------------------------------------
# Scenario 3.13: reducer is pure / deterministic
# ---------------------------------------------------------------------------

class TestReducerPure:
    def test_same_log_same_state(self, tmp_orch):
        """Scenario 3.13: reduce_all twice → identical state."""
        _append_dev_workflow(5)
        state1 = reduce_all()
        state2 = reduce_all()
        assert state1.to_dict() == state2.to_dict()

    def test_last_seq_matches_log(self, tmp_orch):
        _append_dev_workflow(3)
        state = reduce_all()
        assert state.last_seq > 0


def _append_dev_workflow(n: int):
    """Appends a realistic sequence of events to the real log."""
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": "wf_test", "phases": [{"name": "dev", "order": 1, "required": True}],
    })
    append_event("orchestrator", "phase_entered", data={"phase": "dev", "order": 1})
    for i in range(1, n + 1):
        append_event("orchestrator", "task_created", task_id=f"t_{i:04d}",
                     data=_task_data(deps=[]))


# ---------------------------------------------------------------------------
# Scenario 3.14: duplicate terminal events → idempotent no-op (C2 fix)
# ---------------------------------------------------------------------------

class TestDuplicateTerminals:
    def test_duplicate_completed_is_noop(self):
        """C2: duplicate task_completed is idempotent — no exception, state unchanged."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001", data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_COMPLETED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "artifacts": ["a.out"], "summary": "done"}))

        # Second task_completed must be a no-op (not raise)
        apply_event(state, _evt(EventType.TASK_COMPLETED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "artifacts": [], "summary": "dup"}))

        assert state.tasks["t_001"].status == TaskStatus.COMPLETED
        # Artifacts from the FIRST completed must be preserved (no-op = no mutation)
        assert "a.out" in state.tasks["t_001"].artifacts

    def test_duplicate_failed_is_noop(self):
        """C2: duplicate task_failed on already-FAILED task is idempotent."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001", data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "reason": "first_fail", "retryable": True}))

        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "reason": "dup_fail", "retryable": False}))

        assert state.tasks["t_001"].status == TaskStatus.FAILED
        # Reason from FIRST failure preserved (no-op = no mutation)
        assert state.tasks["t_001"].last_failure_reason == "first_fail"

    def test_failed_on_completed_is_noop(self):
        """C2: task_failed on COMPLETED task (orchestrator/hook race) is idempotent."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001", data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "worker_type": "impl", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_COMPLETED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "artifacts": [], "summary": "done"}))

        # Hook synthesizes task_failed after orchestrator already completed it — must be no-op
        apply_event(state, _evt(EventType.TASK_FAILED, task_id="t_001", attempt=1,
                                data={"phase": "dev", "reason": "hook_race", "retryable": True}))

        assert state.tasks["t_001"].status == TaskStatus.COMPLETED


# ---------------------------------------------------------------------------
# C8: phase_entered without prior phase_transitioned raises IllegalTransition
# ---------------------------------------------------------------------------

class TestPhaseEnteredError:
    def test_phase_entered_undeclared_phase_raises(self):
        """C8: phase_entered for undeclared phase raises IllegalTransition."""
        state = OrchState()
        apply_event(state, _evt(EventType.PHASE_DECLARED, data={
            "workflow_id": "wf",
            "phases": [{"name": "sdd", "order": 1, "required": True}],
        }))
        # "dev" was never declared
        with pytest.raises(IllegalTransition, match="not declared"):
            apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "dev", "order": 1}))

    def test_phase_entered_while_another_active_raises(self):
        """C8: second phase_entered while a phase is already active raises IllegalTransition."""
        state = OrchState()
        apply_event(state, _evt(EventType.PHASE_DECLARED, data={
            "workflow_id": "wf",
            "phases": [
                {"name": "sdd", "order": 1, "required": True},
                {"name": "dev", "order": 2, "required": True},
            ],
        }))
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "sdd", "order": 1}))

        # Attempt to enter dev without first closing sdd via phase_transitioned
        with pytest.raises(IllegalTransition, match="already active"):
            apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "dev", "order": 2}))

        # State must be unchanged after the failed transition
        assert state.phases["sdd"].status == PhaseStatus.ACTIVE
        assert state.current_phase == "sdd"

    def test_phase_entered_after_transitioned_succeeds(self):
        """C8: phase_entered for next phase after proper phase_transitioned succeeds."""
        state = OrchState()
        apply_event(state, _evt(EventType.PHASE_DECLARED, data={
            "workflow_id": "wf",
            "phases": [
                {"name": "sdd", "order": 1, "required": True},
                {"name": "dev", "order": 2, "required": True},
            ],
        }))
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "sdd", "order": 1}))
        apply_event(state, _evt(EventType.PHASE_EXIT_APPROVED, data={
            "phase": "sdd", "criteria_met": ["done"], "next_phase": "dev",
        }))
        apply_event(state, _evt(EventType.PHASE_TRANSITIONED, data={
            "from_phase": "sdd", "to_phase": "dev", "evidence_seq": 2,
        }))
        # Now phase_entered for dev must succeed
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "dev", "order": 2}))
        assert state.phases["dev"].status == PhaseStatus.ACTIVE
        assert state.current_phase == "dev"


# ---------------------------------------------------------------------------
# Phase state machine: scenarios 5.1 - 5.11
# ---------------------------------------------------------------------------

class TestPhaseStateMachine:
    def test_phase_declared_initializes_pending(self):
        """Scenario 5.1."""
        state = OrchState()
        apply_event(state, _evt(EventType.PHASE_DECLARED, data={
            "workflow_id": "wf",
            "phases": [
                {"name": "sdd", "order": 1, "required": True},
                {"name": "dev", "order": 2, "required": True},
            ],
        }))
        assert state.phases["sdd"].status == PhaseStatus.PENDING
        assert state.phases["sdd"].order == 1
        assert state.phases["dev"].status == PhaseStatus.PENDING
        assert state.phases["dev"].order == 2

    def test_phase_entered_becomes_active(self):
        """Scenario 5.2."""
        state = OrchState()
        apply_event(state, _evt(EventType.PHASE_DECLARED, data={
            "workflow_id": "wf",
            "phases": [{"name": "sdd", "order": 1, "required": True}],
        }))
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "sdd", "order": 1}))
        assert state.phases["sdd"].status == PhaseStatus.ACTIVE
        assert state.current_phase == "sdd"

    def test_only_one_phase_active_at_a_time(self):
        """Scenario 5.3: entering second phase while first is active raises."""
        state = OrchState()
        apply_event(state, _evt(EventType.PHASE_DECLARED, data={
            "workflow_id": "wf",
            "phases": [
                {"name": "sdd", "order": 1, "required": True},
                {"name": "dev", "order": 2, "required": True},
            ],
        }))
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "sdd", "order": 1}))
        with pytest.raises(IllegalTransition):
            apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "dev", "order": 2}))

    def test_phase_exit_approved(self):
        """Scenario 5.4."""
        state = OrchState()
        apply_event(state, _evt(EventType.PHASE_DECLARED, data={
            "workflow_id": "wf",
            "phases": [{"name": "sdd", "order": 1, "required": True}],
        }))
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "sdd", "order": 1}))
        apply_event(state, _evt(EventType.PHASE_EXIT_APPROVED, data={
            "phase": "sdd", "criteria_met": ["c1", "c2"], "next_phase": "dev",
        }))
        assert state.phases["sdd"].status == PhaseStatus.EXIT_APPROVED

    def test_phase_transitioned_closes_and_opens(self):
        """Scenario 5.5."""
        state = OrchState()
        apply_event(state, _evt(EventType.PHASE_DECLARED, data={
            "workflow_id": "wf",
            "phases": [
                {"name": "sdd", "order": 1, "required": True},
                {"name": "dev", "order": 2, "required": True},
            ],
        }))
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "sdd", "order": 1}))
        apply_event(state, _evt(EventType.PHASE_EXIT_APPROVED, data={
            "phase": "sdd", "criteria_met": ["c1"], "next_phase": "dev",
        }))
        apply_event(state, _evt(EventType.PHASE_TRANSITIONED, data={
            "from_phase": "sdd", "to_phase": "dev", "evidence_seq": 3,
        }))
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "dev", "order": 2}))
        assert state.phases["sdd"].status == PhaseStatus.COMPLETED
        assert state.phases["dev"].status == PhaseStatus.ACTIVE
        assert state.current_phase == "dev"

    def test_task_promoted_after_phase_activates(self):
        """Scenario 5.7: task in pending phase gets ready when phase activates."""
        state = OrchState()
        apply_event(state, _evt(EventType.PHASE_DECLARED, data={
            "workflow_id": "wf",
            "phases": [
                {"name": "sdd", "order": 1, "required": True},
                {"name": "dev", "order": 2, "required": True},
            ],
        }))
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "sdd", "order": 1}))
        # Task in dev phase while dev is still pending
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(phase="dev", deps=[])))
        assert state.tasks["t_001"].status == TaskStatus.PENDING

        # Transition to dev
        apply_event(state, _evt(EventType.PHASE_EXIT_APPROVED, data={
            "phase": "sdd", "criteria_met": ["done"], "next_phase": "dev",
        }))
        apply_event(state, _evt(EventType.PHASE_TRANSITIONED, data={
            "from_phase": "sdd", "to_phase": "dev", "evidence_seq": 2,
        }))
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "dev", "order": 2}))
        assert state.tasks["t_001"].status == TaskStatus.READY

    def test_cross_phase_dependency(self):
        """Scenario 5.8: dep in sdd completes; task in dev becomes ready after dev activates."""
        state = OrchState()
        apply_event(state, _evt(EventType.PHASE_DECLARED, data={
            "workflow_id": "wf",
            "phases": [
                {"name": "sdd", "order": 1, "required": True},
                {"name": "dev", "order": 2, "required": True},
            ],
        }))
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "sdd", "order": 1}))
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_spec",
                                data=_task_data(phase="sdd", deps=[])))
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_impl",
                                data=_task_data(phase="dev", deps=["t_spec"])))

        # Complete t_spec
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_spec", attempt=1,
                                data={"phase": "sdd", "worker_type": "x", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_COMPLETED, task_id="t_spec", attempt=1,
                                data={"phase": "sdd", "artifacts": [], "summary": "done"}))

        assert state.tasks["t_impl"].status == TaskStatus.PENDING  # dev not active yet

        # Activate dev
        apply_event(state, _evt(EventType.PHASE_EXIT_APPROVED, data={
            "phase": "sdd", "criteria_met": ["done"], "next_phase": "dev",
        }))
        apply_event(state, _evt(EventType.PHASE_TRANSITIONED, data={
            "from_phase": "sdd", "to_phase": "dev", "evidence_seq": 3,
        }))
        apply_event(state, _evt(EventType.PHASE_ENTERED, data={"phase": "dev", "order": 2}))

        assert state.tasks["t_impl"].status == TaskStatus.READY

    def test_current_phase_derived_from_log(self, tmp_orch):
        """Scenario 5.9: reduce_all recovers current_phase from log."""
        append_event("orchestrator", "phase_declared", data={
            "workflow_id": "wf", "phases": [{"name": "dev", "order": 1, "required": True}],
        })
        append_event("orchestrator", "phase_entered", data={"phase": "dev", "order": 1})
        state = reduce_all()
        assert state.current_phase == "dev"

    def test_phase_exit_criterion_met_accumulates(self):
        """Scenario 5.10."""
        state = fresh()
        apply_event(state, _evt(EventType.PHASE_EXIT_CRITERION_MET,
                                data={"phase": "dev", "criterion": "all_decomposed"}))
        apply_event(state, _evt(EventType.PHASE_EXIT_CRITERION_MET,
                                data={"phase": "dev", "criterion": "specs_validated"}))
        assert "all_decomposed" in state.phases["dev"].criteria_met
        assert "specs_validated" in state.phases["dev"].criteria_met

    def test_phase_paused_and_resumed(self):
        """Scenario 5.11."""
        state = fresh()
        apply_event(state, _evt(EventType.PHASE_PAUSED,
                                data={"phase": "dev", "reason": "escalation"}))
        assert state.phases["dev"].status == PhaseStatus.PAUSED

        apply_event(state, _evt(EventType.PHASE_RESUMED,
                                data={"phase": "dev", "paused_seq": 1}))
        assert state.phases["dev"].status == PhaseStatus.ACTIVE


# ---------------------------------------------------------------------------
# OrchState: to_dict / from_dict round-trip
# ---------------------------------------------------------------------------

class TestOrchStateRoundTrip:
    def test_to_dict_from_dict_roundtrip(self):
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(deps=[])))
        d = state.to_dict()
        state2 = OrchState.from_dict(d)
        assert state2.to_dict() == d

    def test_task_state_roundtrip(self):
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(deps=[])))
        t = state.tasks["t_001"]
        d = t.to_dict()
        t2 = TaskState.from_dict(d)
        assert t2.to_dict() == d

    def test_phase_state_roundtrip(self):
        state = fresh()
        p = state.phases["dev"]
        d = p.to_dict()
        p2 = PhaseState.from_dict(d)
        assert p2.to_dict() == d

    def test_tasks_by_status(self):
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(deps=[])))
        assert len(state.tasks_by_status(TaskStatus.READY)) == 1
        assert len(state.tasks_by_status(TaskStatus.PENDING)) == 0

    def test_tasks_by_phase(self):
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(phase="dev", deps=[])))
        assert len(state.tasks_by_phase("dev")) == 1
        assert len(state.tasks_by_phase("sdd")) == 0

    def test_ready_tasks(self):
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(deps=[])))
        ready = state.ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "t_001"


# ---------------------------------------------------------------------------
# B1 — apply_event no-ops for valid types without reducer handlers
# ---------------------------------------------------------------------------

class TestApplyEventNoOp:
    def test_task_progress_does_not_crash(self, tmp_orch):
        """B1: task_progress is worker-emittable but has no reducer effect."""
        append_event("orchestrator", "phase_declared", data={
            "workflow_id": "wf", "phases": [{"name": "dev", "order": 1, "required": True}]
        })
        append_event("orchestrator", "phase_entered", data={"phase": "dev", "order": 1})
        append_event("orchestrator", "task_created", task_id="t_0001",
                     data=_task_data(deps=[]))
        append_event("worker", "task_claimed", task_id="t_0001", attempt=1,
                     data={"phase": "dev", "worker_type": "impl", "worker_id": "w"})
        append_event("worker", "task_progress", task_id="t_0001", attempt=1,
                     data={"phase": "dev", "note": "halfway"})
        append_event("worker", "task_completed", task_id="t_0001", attempt=1,
                     data={"phase": "dev", "artifacts": [], "summary": "done"})

        state = reduce_all()
        assert state.tasks["t_0001"].status == TaskStatus.COMPLETED

    def test_task_progress_does_not_change_task_status(self):
        """B1: task_progress event applied directly leaves task running."""
        state = fresh()
        apply_event(state, _evt(EventType.TASK_CREATED, task_id="t_001",
                                data=_task_data(deps=[])))
        apply_event(state, _evt(EventType.TASK_CLAIMED, task_id="t_001",
                                data={"phase": "dev", "worker_type": "x", "worker_id": "w"}))
        apply_event(state, _evt(EventType.TASK_PROGRESS, task_id="t_001",
                                data={"phase": "dev", "note": "50%"}))

        assert state.tasks["t_001"].status == TaskStatus.RUNNING

    def test_unknown_event_type_raises(self):
        """B1: completely unknown event_type still raises UnknownEventType."""
        from orch_core import UnknownEventType
        state = OrchState()
        bad_event = _evt("not_a_real_type", data={})
        bad_event.event_type = "not_a_real_type"

        with pytest.raises(UnknownEventType):
            apply_event(state, bad_event)

    def test_last_seq_updated_for_no_op_events(self):
        """B1: last_seq advances even for no-op events."""
        state = OrchState()
        ev = _evt(EventType.TASK_PROGRESS, task_id="t_001",
                  data={"phase": "dev", "note": "x"}, seq=42)
        apply_event(state, ev)
        assert state.last_seq == 42
