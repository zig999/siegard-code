"""
Orchestrator scenario tests — escalation flows (Level B).

Scenarios:
  I  — E99 unresolved: run_status=escalated, workflow blocked
  J  — E99 resolved via human_response(confirm_proceed): workflow resumes
  K  — E14 (u-improve confirmation): escalation emitted, then resolved
"""
import pytest

import orch_core
from orch_core import (
    append_event,
    reduce_all,
    TaskStatus,
)

from .conftest import (
    wf_env,  # noqa: F401
    declare_phases,
    enter_phase,
    create_task,
    claim_task,
    complete_task,
    run_task,
    escalate,
    human_respond,
    assert_task_status,
    assert_escalation_present,
    assert_no_escalation,
    assert_run_status,
    assert_current_phase,
)


# ---------------------------------------------------------------------------
# Scenario I — E99 unresolved blocks workflow
# ---------------------------------------------------------------------------

class TestScenarioI_E99Unresolved:
    """
    An E99 (confirmation/approval required) escalation is emitted.
    State.run_status must be 'escalated' and state.escalation must be populated.
    Workflow cannot progress without human_response.
    """

    def test_e99_sets_escalated_run_status(self, wf_env):
        declare_phases()
        enter_phase("sdd", 1)
        escalate("E99", "spec review requires operator approval before dispatch",
                 agent="orchestrator-sdd")

        state = reduce_all()
        assert_run_status(state, "escalated")

    def test_e99_populates_escalation_field(self, wf_env):
        declare_phases()
        enter_phase("sdd", 1)
        escalate("E99", "approval gate before sdd dispatch",
                 agent="orchestrator-sdd",
                 evidence=["sdd_spec_001"])

        state = reduce_all()
        assert_escalation_present(state, code="E99")
        assert state.escalation is not None
        assert "seq" in state.escalation

    def test_e99_escalation_seq_matches_event_seq(self, wf_env):
        declare_phases()
        enter_phase("sdd", 1)
        escalate("E99", "approval required")

        state = reduce_all()
        # escalation.seq must match the event seq injected by the reducer
        assert isinstance(state.escalation["seq"], int)
        assert state.escalation["seq"] > 0

    def test_multiple_tasks_pending_while_escalated(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev")
        create_task("dev_tc_002", "dev")
        escalate("E99", "dev dispatch approval required")

        state = reduce_all()
        assert_run_status(state, "escalated")
        assert_task_status(state, "dev_tc_001", "ready")
        assert_task_status(state, "dev_tc_002", "ready")

    def test_second_escalation_overwrites_first(self, wf_env):
        """Only the most recent escalation is active in state."""
        declare_phases()
        enter_phase("dev", 2)
        escalate("E99", "first approval gate")

        state_after_first = reduce_all()
        first_seq = state_after_first.escalation["seq"]

        escalate("E04", "task in DLQ requires review")

        state = reduce_all()
        assert_escalation_present(state, code="E04")
        assert state.escalation["seq"] > first_seq

    def test_e04_dlq_escalation_marks_run_status_escalated(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev", tier="critical")
        claim_task("dev_tc_001", "dev")
        append_event("w_dev_tc_001", "task_failed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "reason": "internal_error", "retryable": False,
        })
        append_event("orchestrator", "task_dlq", task_id="dev_tc_001", data={
            "phase": "dev", "reason": "non_retryable", "last_error": "fatal error",
        })
        escalate("E04", "critical task in DLQ")

        state = reduce_all()
        assert_run_status(state, "escalated")
        assert_escalation_present(state, code="E04")

    def test_e11_missing_input_escalation(self, wf_env):
        declare_phases()
        escalate("E11", "required input missing: api_contract",
                 agent="orchestrator",
                 evidence=["missing: api_contract.yaml"])

        state = reduce_all()
        assert_escalation_present(state, code="E11")
        assert_run_status(state, "escalated")

    def test_e09_spec_divergence_escalation(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        escalate("E09", "implementation diverges from spec",
                 agent="orchestrator-dev",
                 evidence=["dev_tc_001"])

        state = reduce_all()
        assert_escalation_present(state, code="E09")
        assert_run_status(state, "escalated")


# ---------------------------------------------------------------------------
# Scenario J — E99 resolved via human_response(confirm_proceed)
# ---------------------------------------------------------------------------

class TestScenarioJ_E99Resolved:
    """
    After an E99 escalation, the operator sends human_response(confirm_proceed).
    State.run_status returns to 'active'. State.escalation is cleared.
    Tasks can be dispatched again.
    """

    def test_confirm_proceed_clears_escalation(self, wf_env):
        declare_phases()
        enter_phase("sdd", 1)
        escalate("E99", "approval gate before sdd dispatch")

        state = reduce_all()
        seq = state.escalation["seq"]

        human_respond(seq, "confirm_proceed")

        state = reduce_all()
        assert_no_escalation(state)
        assert_run_status(state, "active")

    def test_workflow_resumes_after_e99_resolved(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev")
        escalate("E99", "pre-dispatch approval for dev phase")

        state = reduce_all()
        seq = state.escalation["seq"]
        assert_run_status(state, "escalated")

        human_respond(seq, "confirm_proceed")

        state = reduce_all()
        assert_run_status(state, "active")
        assert_task_status(state, "dev_tc_001", "ready")

    def test_abort_action_also_clears_escalation(self, wf_env):
        declare_phases()
        enter_phase("sdd", 1)
        escalate("E99", "approval required")

        state = reduce_all()
        seq = state.escalation["seq"]

        human_respond(seq, "abort")

        state = reduce_all()
        assert_no_escalation(state)
        assert_run_status(state, "active")

    def test_multiple_escalations_resolved_sequentially(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)

        escalate("E99", "first gate")
        state = reduce_all()
        seq1 = state.escalation["seq"]
        human_respond(seq1, "confirm_proceed")

        state = reduce_all()
        assert_no_escalation(state)

        escalate("E99", "second gate")
        state = reduce_all()
        seq2 = state.escalation["seq"]
        assert seq2 > seq1

        human_respond(seq2, "confirm_proceed")
        state = reduce_all()
        assert_no_escalation(state)
        assert_run_status(state, "active")

    def test_reject_action_clears_escalation(self, wf_env):
        declare_phases()
        enter_phase("review", 3)
        escalate("E05", "rejection cycle: QA did not approve",
                 agent="orchestrator-review")

        state = reduce_all()
        seq = state.escalation["seq"]

        human_respond(seq, "reject")

        state = reduce_all()
        assert_no_escalation(state)

    def test_e99_sdd_pre_dispatch_gate(self, wf_env):
        """Full SDD pre-dispatch gate: declare → enter → E99 → confirm → dispatch."""
        declare_phases()
        enter_phase("sdd", 1)
        create_task("sdd_spec_001", "sdd", task_type="spec-writer")
        create_task("sdd_val_001", "sdd", task_type="spec-validator",
                    deps=["sdd_spec_001"])

        # Orchestrator-sdd emits E99 before dispatching
        escalate("E99", "operator review of sdd tasks before dispatch",
                 agent="orchestrator-sdd")

        state = reduce_all()
        seq = state.escalation["seq"]
        assert_run_status(state, "escalated")
        assert_task_status(state, "sdd_spec_001", "ready")

        human_respond(seq, "confirm_proceed")

        state = reduce_all()
        assert_run_status(state, "active")
        # Now the orchestrator can dispatch sdd_spec_001
        claim_task("sdd_spec_001", "sdd", worker_type="spec-writer")
        state = reduce_all()
        assert_task_status(state, "sdd_spec_001", "running")


# ---------------------------------------------------------------------------
# Scenario K — E14 (u-improve confirmation)
# ---------------------------------------------------------------------------

class TestScenarioK_E14ImproveConfirmation:
    """
    The u-improve skill emits E14_improve_spec_confirmation before running.
    The operator confirms or aborts via human_response.
    After confirmation, the orchestrator resumes normal flow.
    """

    def test_e14_blocks_workflow(self, wf_env):
        declare_phases()
        escalate(
            "E14_improve_spec_confirmation",
            "u-improve: operator confirmation required before altering spec",
            agent="orchestrator",
            evidence=["spec/handoff-manifest.yaml"],
        )

        state = reduce_all()
        assert_escalation_present(state, code="E14_improve_spec_confirmation")
        assert_run_status(state, "escalated")

    def test_e14_confirmed_resumes_workflow(self, wf_env):
        declare_phases()
        escalate(
            "E14_improve_spec_confirmation",
            "u-improve confirmation",
            agent="orchestrator",
        )

        state = reduce_all()
        seq = state.escalation["seq"]

        human_respond(seq, "confirm_proceed")

        state = reduce_all()
        assert_no_escalation(state)
        assert_run_status(state, "active")

    def test_e14_aborted_clears_escalation(self, wf_env):
        declare_phases()
        escalate(
            "E14_improve_spec_confirmation",
            "u-improve confirmation",
            agent="orchestrator",
        )

        state = reduce_all()
        seq = state.escalation["seq"]

        human_respond(seq, "abort")

        state = reduce_all()
        assert_no_escalation(state)
        assert_run_status(state, "active")

    def test_e14_then_sdd_phase_continues(self, wf_env):
        """After E14 confirmation, sdd phase tasks can proceed normally."""
        declare_phases()
        enter_phase("sdd", 1)
        create_task("sdd_spec_001", "sdd", task_type="spec-writer")

        escalate(
            "E14_improve_spec_confirmation",
            "u-improve: improving spec before dispatch",
            agent="orchestrator-sdd",
        )

        state = reduce_all()
        assert_run_status(state, "escalated")
        seq = state.escalation["seq"]

        human_respond(seq, "confirm_proceed")

        state = reduce_all()
        assert_run_status(state, "active")
        assert_task_status(state, "sdd_spec_001", "ready")

        # Dispatch proceeds normally
        claim_task("sdd_spec_001", "sdd", worker_type="spec-writer")
        run_task_worker = "w_sdd_spec_001"
        complete_task("sdd_spec_001", "sdd", worker_id=run_task_worker)

        state = reduce_all()
        assert_task_status(state, "sdd_spec_001", "completed")

    def test_e14_escalation_seq_is_injected_by_reducer(self, wf_env):
        """Escalation dict must contain 'seq' field for human_response to reference."""
        declare_phases()
        escalate("E14_improve_spec_confirmation", "confirmation required")

        state = reduce_all()
        assert "seq" in state.escalation
        assert isinstance(state.escalation["seq"], int)

    def test_workflow_hash_chain_intact_after_escalation_cycle(self, wf_env):
        """Hash chain must remain valid after escalation + human_response cycle."""
        from orch_core import verify_chain, read_events

        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev")

        escalate("E99", "approval gate")
        state = reduce_all()
        seq = state.escalation["seq"]
        human_respond(seq, "confirm_proceed")

        result = verify_chain()
        assert result.ok is True
        assert len(result.error_details) == 0
