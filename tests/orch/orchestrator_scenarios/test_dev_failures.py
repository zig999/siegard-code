"""
Orchestrator scenario tests — dev phase failure modes (Level B).

Scenarios:
  A — Worker stops silently: synthesized task_failed drives task to FAILED
  B — Non-retryable failure → DLQ: should_retry returns False
  C — Planning task failure (E07): escalation emitted, run_status escalated
  D — Circuit breaker trips: evaluate_circuit_state triggers, state updated
"""
import pytest
from datetime import datetime, timezone, timedelta

import orch_core
from orch_core import (
    append_event,
    reduce_all,
    TaskStatus,
    default_config,
    evaluate_circuit_state,
    load_retry_policy,
    should_retry,
    detect_critical_dlq,
    now_iso,
)

from .conftest import (
    wf_env,  # noqa: F401
    declare_phases,
    enter_phase,
    create_task,
    claim_task,
    complete_task,
    fail_task,
    dlq_task,
    escalate,
    assert_task_status,
    assert_escalation_present,
    assert_run_status,
)


# ---------------------------------------------------------------------------
# Scenario A — Worker stops silently
# ---------------------------------------------------------------------------

class TestScenarioA_SilentWorkerStop:
    """
    A worker is claimed and then stops without emitting any terminal event.
    The on_subagent_stop hook synthesizes task_failed(retryable=True).
    The task must reflect FAILED status and be retry-eligible.
    """

    def test_synthesized_task_failed_sets_failed_status(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev")
        claim_task("dev_tc_001", "dev")

        # Simulate on_subagent_stop synthesizing task_failed
        append_event("orchestrator", "task_failed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "reason": "worker_exited_without_terminal", "retryable": True,
        })

        state = reduce_all()
        assert_task_status(state, "dev_tc_001", "failed")

    def test_failed_task_is_retry_eligible(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev", tier="standard")
        claim_task("dev_tc_001", "dev")
        append_event("orchestrator", "task_failed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "reason": "worker_exited_without_terminal", "retryable": True,
        })

        state = reduce_all()
        task = state.tasks["dev_tc_001"]
        policy = load_retry_policy(task.task_type, task.tier)
        assert should_retry(task, policy) is True

    def test_failed_task_increments_attempt_on_retry(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev", tier="standard")
        claim_task("dev_tc_001", "dev", attempt=1)
        # Attempt 1 fails — capture seq for previous_failure_seq
        fail_task("dev_tc_001", "dev", retryable=True, attempt=1)

        state = reduce_all()
        failure_seq = state.last_seq

        # Retry scheduled then retried
        append_event("orchestrator", "task_scheduled_retry", task_id="dev_tc_001",
                     attempt=1, data={
                         "phase": "dev",
                         "next_retry_at": now_iso(),
                         "backoff_seconds": 0,
                         "previous_failure_seq": failure_seq,
                     })
        scheduled_seq = reduce_all().last_seq
        append_event("orchestrator", "task_retried", task_id="dev_tc_001",
                     attempt=2, data={
                         "phase": "dev",
                         "previous_attempt": 1,
                         "scheduled_retry_seq": scheduled_seq,
                     })

        state = reduce_all()
        assert state.tasks["dev_tc_001"].attempts == 2

    def test_pending_sibling_promoted_to_ready_after_dep_completes(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev")
        create_task("dev_tc_002", "dev", deps=["dev_tc_001"])

        state = reduce_all()
        assert_task_status(state, "dev_tc_002", "pending")

        claim_task("dev_tc_001", "dev")
        complete_task("dev_tc_001", "dev")

        state = reduce_all()
        assert_task_status(state, "dev_tc_002", "ready")


# ---------------------------------------------------------------------------
# Scenario B — Non-retryable failure → DLQ
# ---------------------------------------------------------------------------

class TestScenarioB_NonRetryableDlq:
    """
    A task fails with retryable=False. The orchestrator sends it to DLQ.
    should_retry must return False. detect_critical_dlq must flag it.
    """

    def test_non_retryable_failure_accepted(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev")
        claim_task("dev_tc_001", "dev")
        fail_task("dev_tc_001", "dev", retryable=False)
        dlq_task("dev_tc_001", "dev")

        state = reduce_all()
        assert_task_status(state, "dev_tc_001", "dlq")

    def test_dlq_task_not_retry_eligible(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev", tier="standard")
        claim_task("dev_tc_001", "dev")
        fail_task("dev_tc_001", "dev", retryable=False)
        dlq_task("dev_tc_001", "dev")

        state = reduce_all()
        task = state.tasks["dev_tc_001"]
        policy = load_retry_policy(task.task_type, task.tier)
        assert should_retry(task, policy) is False

    def test_dlq_task_detected_as_critical(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev", tier="critical")
        claim_task("dev_tc_001", "dev")
        fail_task("dev_tc_001", "dev", retryable=False)
        dlq_task("dev_tc_001", "dev")

        state = reduce_all()
        critical_ids = detect_critical_dlq(state)
        assert "dev_tc_001" in critical_ids

    def test_dlq_cascades_to_dependent_pending_task(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev")
        create_task("dev_tc_002", "dev", deps=["dev_tc_001"])

        claim_task("dev_tc_001", "dev")
        fail_task("dev_tc_001", "dev", retryable=False)
        dlq_task("dev_tc_001", "dev")

        # Orchestrator cascades DLQ to dependent task
        append_event("orchestrator", "task_dlq", task_id="dev_tc_002", data={
            "phase": "dev", "reason": "cascade_from_dep", "last_error": "dependency dev_tc_001 in DLQ",
        })

        state = reduce_all()
        assert_task_status(state, "dev_tc_002", "dlq")

    def test_standard_tier_max_attempts_exhausted_goes_to_dlq(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev", tier="standard")

        # Exhaust attempts: 3 fail/retry cycles then DLQ
        scheduled_seq = None
        for attempt in range(1, 4):
            if attempt == 1:
                claim_task("dev_tc_001", "dev", attempt=attempt)
            else:
                append_event("orchestrator", "task_retried", task_id="dev_tc_001",
                             attempt=attempt, data={
                                 "phase": "dev",
                                 "previous_attempt": attempt - 1,
                                 "scheduled_retry_seq": scheduled_seq,
                             })
                # task_retried resets to READY; must claim before failing
                claim_task("dev_tc_001", "dev", attempt=attempt)
            fail_task("dev_tc_001", "dev", retryable=True, attempt=attempt)
            if attempt < 3:
                failure_seq = reduce_all().last_seq
                append_event("orchestrator", "task_scheduled_retry", task_id="dev_tc_001",
                             attempt=attempt, data={
                                 "phase": "dev",
                                 "next_retry_at": now_iso(),
                                 "backoff_seconds": 1,
                                 "previous_failure_seq": failure_seq,
                             })
                scheduled_seq = reduce_all().last_seq

        dlq_task("dev_tc_001", "dev", reason="max_attempts_exceeded")

        state = reduce_all()
        assert_task_status(state, "dev_tc_001", "dlq")


# ---------------------------------------------------------------------------
# Scenario C — Planning task failure (E07)
# ---------------------------------------------------------------------------

class TestScenarioC_PlanningTaskFailure:
    """
    A planning task fails → non-retryable → DLQ.
    The orchestrator emits escalation(code=E07_planning_failed).
    State run_status becomes 'escalated'.
    """

    def test_planning_task_dlq_triggers_e07_escalation(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_plan_001", "dev", task_type="planning")
        claim_task("dev_plan_001", "dev", worker_type="planning")
        fail_task("dev_plan_001", "dev", retryable=False)
        dlq_task("dev_plan_001", "dev")

        # Orchestrator detects planning DLQ and emits E07
        escalate("E07_planning_failed", "planning task in DLQ; manual intervention required",
                 agent="orchestrator-dev",
                 evidence=["dev_plan_001"])

        state = reduce_all()
        assert_task_status(state, "dev_plan_001", "dlq")
        assert_escalation_present(state, code="E07_planning_failed")
        assert_run_status(state, "escalated")

    def test_planning_dlq_blocks_impl_dispatch(self, wf_env):
        """While escalated, impl tasks remain in PENDING (cannot be dispatched)."""
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_plan_001", "dev", task_type="planning")
        # Impl tasks depend on planning
        create_task("dev_tc_001", "dev", deps=["dev_plan_001"])
        create_task("dev_tc_002", "dev", deps=["dev_plan_001"])

        claim_task("dev_plan_001", "dev", worker_type="planning")
        fail_task("dev_plan_001", "dev", retryable=False)
        dlq_task("dev_plan_001", "dev")
        escalate("E07_planning_failed", "planning DLQ")

        state = reduce_all()
        assert_run_status(state, "escalated")
        # Dependent tasks stay PENDING (deps not satisfied)
        assert_task_status(state, "dev_tc_001", "pending")
        assert_task_status(state, "dev_tc_002", "pending")

    def test_planning_dlq_without_escalation_has_active_run_status(self, wf_env):
        """Before the orchestrator emits escalation, run_status is still 'active'."""
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_plan_001", "dev", task_type="planning")
        claim_task("dev_plan_001", "dev")
        fail_task("dev_plan_001", "dev", retryable=False)
        dlq_task("dev_plan_001", "dev")

        state = reduce_all()
        assert_task_status(state, "dev_plan_001", "dlq")
        assert_run_status(state, "active")


# ---------------------------------------------------------------------------
# Scenario D — Circuit breaker trips
# ---------------------------------------------------------------------------

class TestScenarioD_CircuitBreaker:
    """
    Multiple failures within the circuit breaker window cause it to trip.
    After tripping, evaluate_circuit_state marks should_trip=True,
    and the circuit_breaker_tripped event updates state.
    """

    def _ts_ago(self, seconds: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()

    # test_five_failures_in_window_trips_breaker, test_circuit_breaker_tripped_event_updates_state,
    # test_fewer_than_threshold_does_not_trip removed — evaluate_circuit_state and the tripped-event
    # reducer are owned by test_circuit_breaker.py (incl. real-log integration test_50_failures_trip_circuit
    # and test_circuit_tripped_event_in_state). Only the dev reset+escalation cycle below is unique.

    def test_circuit_breaker_reset_via_human_response(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)

        for i in range(1, 6):
            create_task(f"dev_tc_{i:03d}", "dev")
            claim_task(f"dev_tc_{i:03d}", "dev")
            fail_task(f"dev_tc_{i:03d}", "dev", retryable=True)

        append_event("orchestrator", "circuit_breaker_tripped", data={
            "phase": "dev", "failure_count": 5, "threshold": 5,
            "window_start": now_iso(), "window_end": now_iso(),
        })
        escalate("E10_circuit_breaker_open", "circuit breaker tripped")

        state = reduce_all()
        assert state.circuit_breaker is not None
        seq = state.escalation["seq"]

        append_event("human", "human_response", data={
            "escalation_seq": seq,
            "action": "reset_circuit_breaker",
            "operator": "ops",
        })

        state = reduce_all()
        assert state.circuit_breaker is None
        assert state.escalation is None
        assert_run_status(state, "active")

    # test_already_tripped_flag_detected removed — duplicate of
    # test_circuit_breaker.py::test_already_tripped_flag (evaluate_circuit_state already_tripped path).
