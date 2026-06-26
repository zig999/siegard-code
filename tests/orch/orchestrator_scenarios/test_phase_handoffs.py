"""
Orchestrator scenario tests — phase handoff flows (Level B).

Scenarios:
  E — Dev → review handoff: all criteria met → phase_transitioned emitted
  F — Review → return_to_dev: rejected tasks create revision tasks in dev
  G — SDD exit criteria → transition to dev
  H — Test failures → return_to_dev with test_feedback tasks
"""
import pytest

import orch_core
from orch_core import (
    append_event,
    reduce_all,
    TaskStatus,
    PhaseStatus,
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
    run_task,
    transition_phase,
    assert_task_status,
    assert_current_phase,
    assert_phase_status,
    assert_run_status,
)


# ---------------------------------------------------------------------------
# Scenario E — Dev → review handoff
# ---------------------------------------------------------------------------

class TestScenarioE_DevToReviewHandoff:
    """
    All dev tasks complete with qa_ready artifacts.
    All exit criteria are met. Phase transitions dev → review.
    State.current_phase becomes 'review'.
    """

    def test_dev_phase_transitions_to_review(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)

        for i in range(1, 3):
            create_task(f"dev_tc_{i:03d}", "dev")
            run_task(f"dev_tc_{i:03d}", "dev")

        transition_phase("dev", "review", [
            "all_impl_tasks_terminal",
            "all_deliveries_qa_ready",
            "no_open_prohibitions",
        ])
        enter_phase("review", 3)

        state = reduce_all()
        assert_current_phase(state, "review")

    def test_dev_phase_marked_completed_after_transition(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev")
        run_task("dev_tc_001", "dev")

        transition_phase("dev", "review", [
            "all_impl_tasks_terminal", "all_deliveries_qa_ready", "no_open_prohibitions",
        ])
        enter_phase("review", 3)

        state = reduce_all()
        assert_phase_status(state, "dev", "completed")

    def test_review_tasks_created_after_handoff(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev")
        run_task("dev_tc_001", "dev")

        transition_phase("dev", "review", [
            "all_impl_tasks_terminal", "all_deliveries_qa_ready", "no_open_prohibitions",
        ])
        enter_phase("review", 3)

        # Review phase creates QA tasks
        create_task("review_tc_001", "review", task_type="qa")
        state = reduce_all()

        assert "review_tc_001" in state.tasks
        assert state.tasks["review_tc_001"].phase == "review"

    def test_dev_tasks_not_visible_as_active_after_transition(self, wf_env):
        declare_phases()
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev")
        run_task("dev_tc_001", "dev")

        transition_phase("dev", "review", [
            "all_impl_tasks_terminal", "all_deliveries_qa_ready", "no_open_prohibitions",
        ])
        enter_phase("review", 3)

        state = reduce_all()
        dev_active = [t for t in state.tasks.values()
                      if t.phase == "dev" and t.status not in (
                          TaskStatus.COMPLETED, TaskStatus.DLQ)]
        assert dev_active == []

    def test_full_sdd_dev_handoff_chain(self, wf_env):
        declare_phases()
        enter_phase("sdd", 1)
        create_task("sdd_tc_001", "sdd", task_type="spec-writer")
        run_task("sdd_tc_001", "sdd", worker_type="spec-writer")

        transition_phase("sdd", "dev", [
            "handoff_manifest_approved", "all_domains_validated", "error_codes_synced",
        ])
        enter_phase("dev", 2)

        create_task("dev_tc_001", "dev")
        run_task("dev_tc_001", "dev")

        transition_phase("dev", "review", [
            "all_impl_tasks_terminal", "all_deliveries_qa_ready", "no_open_prohibitions",
        ])
        enter_phase("review", 3)

        state = reduce_all()
        assert_current_phase(state, "review")
        assert_phase_status(state, "sdd", "completed")
        assert_phase_status(state, "dev", "completed")


# ---------------------------------------------------------------------------
# Scenario F — Review → return_to_dev (partial rejection)
# ---------------------------------------------------------------------------

class TestScenarioF_ReviewReturnToDev:
    """
    QA rejects some deliveries. The orchestrator creates revision tasks
    in the dev phase (suffixed _r1). Phase transitions back to dev.
    """

    def _setup_review_phase(self):
        declare_phases()
        enter_phase("dev", 2)
        for i in range(1, 3):
            create_task(f"dev_tc_{i:03d}", "dev")
            run_task(f"dev_tc_{i:03d}", "dev")
        transition_phase("dev", "review", [
            "all_impl_tasks_terminal", "all_deliveries_qa_ready", "no_open_prohibitions",
        ])
        enter_phase("review", 3)

    def test_revision_task_created_in_dev_phase(self, wf_env):
        self._setup_review_phase()

        # QA rejects dev_tc_002
        create_task("review_tc_001", "review", task_type="qa")
        create_task("review_tc_002", "review", task_type="qa")
        run_task("review_tc_001", "review", worker_type="qa")
        run_task("review_tc_002", "review", worker_type="qa")

        # Phase transitions back to dev with revision tasks
        transition_phase("review", "dev", ["partial_rejection_rework"])
        enter_phase("dev", 2)

        # Orchestrator creates revision task for rejected delivery
        create_task("dev_tc_002_r1", "dev", task_type="impl",
                    spec="spec/dev_tc_002_r1.md")

        state = reduce_all()
        assert "dev_tc_002_r1" in state.tasks
        assert state.tasks["dev_tc_002_r1"].phase == "dev"

    def test_revision_task_is_ready_after_creation(self, wf_env):
        self._setup_review_phase()
        transition_phase("review", "dev", ["partial_rejection_rework"])
        enter_phase("dev", 2)

        create_task("dev_tc_001_r1", "dev", task_type="impl")

        state = reduce_all()
        assert_task_status(state, "dev_tc_001_r1", "ready")

    def test_current_phase_returns_to_dev_after_rejection(self, wf_env):
        self._setup_review_phase()
        transition_phase("review", "dev", ["partial_rejection_rework"])
        enter_phase("dev", 2)

        state = reduce_all()
        assert_current_phase(state, "dev")

    def test_review_phase_marked_completed_after_transition(self, wf_env):
        self._setup_review_phase()
        transition_phase("review", "dev", ["partial_rejection_rework"])
        enter_phase("dev", 2)

        state = reduce_all()
        assert_phase_status(state, "review", "completed")

    def test_multiple_revision_rounds_tracked(self, wf_env):
        """Two review rounds: _r1 and _r2 both visible in state."""
        self._setup_review_phase()

        # Round 1 revision
        transition_phase("review", "dev", ["partial_rejection_rework"])
        enter_phase("dev", 2)
        create_task("dev_tc_001_r1", "dev")
        run_task("dev_tc_001_r1", "dev")

        transition_phase("dev", "review", [
            "all_impl_tasks_terminal", "all_deliveries_qa_ready", "no_open_prohibitions",
        ])
        enter_phase("review", 3)

        # Round 2 revision
        transition_phase("review", "dev", ["partial_rejection_rework"])
        enter_phase("dev", 2)
        create_task("dev_tc_001_r2", "dev")

        state = reduce_all()
        assert "dev_tc_001_r1" in state.tasks
        assert "dev_tc_001_r2" in state.tasks


# ---------------------------------------------------------------------------
# Scenario G — SDD exit criteria → transition to dev
# ---------------------------------------------------------------------------

class TestScenarioG_SddToDevHandoff:
    """
    All SDD criteria are met: handoff_manifest_approved, all_domains_validated,
    error_codes_synced. Phase transitions sdd → dev.
    """

    def test_sdd_to_dev_transition(self, wf_env):
        declare_phases()
        enter_phase("sdd", 1)

        create_task("sdd_spec_001", "sdd", task_type="spec-writer")
        create_task("sdd_val_001", "sdd", task_type="spec-validator",
                    deps=["sdd_spec_001"])
        run_task("sdd_spec_001", "sdd", worker_type="spec-writer")
        run_task("sdd_val_001", "sdd", worker_type="spec-validator")

        transition_phase("sdd", "dev", [
            "handoff_manifest_approved",
            "all_domains_validated",
            "error_codes_synced",
        ])
        enter_phase("dev", 2)

        state = reduce_all()
        assert_current_phase(state, "dev")

    def test_sdd_phase_completed_after_transition(self, wf_env):
        declare_phases()
        enter_phase("sdd", 1)
        create_task("sdd_spec_001", "sdd", task_type="spec-writer")
        run_task("sdd_spec_001", "sdd")

        transition_phase("sdd", "dev", [
            "handoff_manifest_approved", "all_domains_validated", "error_codes_synced",
        ])
        enter_phase("dev", 2)

        state = reduce_all()
        assert_phase_status(state, "sdd", "completed")

    def test_dev_tasks_visible_after_sdd_handoff(self, wf_env):
        declare_phases()
        enter_phase("sdd", 1)
        create_task("sdd_spec_001", "sdd", task_type="spec-writer")
        run_task("sdd_spec_001", "sdd")

        transition_phase("sdd", "dev", [
            "handoff_manifest_approved", "all_domains_validated", "error_codes_synced",
        ])
        enter_phase("dev", 2)

        create_task("dev_tc_001", "dev")
        create_task("dev_tc_002", "dev")

        state = reduce_all()
        dev_tasks = state.tasks_by_phase("dev")
        assert len(dev_tasks) == 2

    def test_sdd_validator_deps_enforced(self, wf_env):
        """Validator task remains PENDING until spec-writer completes."""
        declare_phases()
        enter_phase("sdd", 1)
        create_task("sdd_spec_001", "sdd", task_type="spec-writer")
        create_task("sdd_val_001", "sdd", task_type="spec-validator",
                    deps=["sdd_spec_001"])

        state = reduce_all()
        assert_task_status(state, "sdd_val_001", "pending")

        run_task("sdd_spec_001", "sdd")

        state = reduce_all()
        assert_task_status(state, "sdd_val_001", "ready")


# ---------------------------------------------------------------------------
# Scenario H — Test failures → return_to_dev
# ---------------------------------------------------------------------------

class TestScenarioH_TestReturnToDev:
    """
    Tests fail. The orchestrator creates test_feedback tasks in dev.
    Phase transitions test → dev for remediation.
    """

    def _setup_to_test_phase(self):
        declare_phases()
        enter_phase("sdd", 1)
        create_task("sdd_spec_001", "sdd", task_type="spec-writer")
        run_task("sdd_spec_001", "sdd")
        transition_phase("sdd", "dev", [
            "handoff_manifest_approved", "all_domains_validated", "error_codes_synced",
        ])
        enter_phase("dev", 2)
        create_task("dev_tc_001", "dev")
        run_task("dev_tc_001", "dev")
        transition_phase("dev", "review", [
            "all_impl_tasks_terminal", "all_deliveries_qa_ready", "no_open_prohibitions",
        ])
        enter_phase("review", 3)
        create_task("review_tc_001", "review", task_type="qa")
        run_task("review_tc_001", "review", worker_type="qa")
        transition_phase("review", "test", [
            "all_qa_verdicts_approved", "no_open_critical_findings", "documentation_verified",
        ])
        enter_phase("test", 4)

    def test_test_failure_returns_to_dev(self, wf_env):
        self._setup_to_test_phase()

        create_task("test_run_001", "test", task_type="test-run")
        claim_task("test_run_001", "test", worker_type="test-run")
        fail_task("test_run_001", "test", retryable=False)
        dlq_task("test_run_001", "test")

        transition_phase("test", "dev", ["test_failures_require_rework"])
        enter_phase("dev", 2)

        create_task("dev_feedback_001", "dev", task_type="impl",
                    spec="spec/dev_feedback_001_test_feedback.md")

        state = reduce_all()
        assert_current_phase(state, "dev")
        assert "dev_feedback_001" in state.tasks

    def test_test_feedback_task_ready_for_dispatch(self, wf_env):
        self._setup_to_test_phase()

        create_task("test_run_001", "test", task_type="test-run")
        claim_task("test_run_001", "test", worker_type="test-run")
        fail_task("test_run_001", "test", retryable=False)
        dlq_task("test_run_001", "test")

        transition_phase("test", "dev", ["test_failures_require_rework"])
        enter_phase("dev", 2)

        create_task("dev_feedback_001", "dev", task_type="impl")

        state = reduce_all()
        assert_task_status(state, "dev_feedback_001", "ready")

    def test_test_phase_completed_after_transition_back(self, wf_env):
        self._setup_to_test_phase()

        create_task("test_run_001", "test", task_type="test-run")
        claim_task("test_run_001", "test", worker_type="test-run")
        fail_task("test_run_001", "test", retryable=False)
        dlq_task("test_run_001", "test")

        transition_phase("test", "dev", ["test_failures_require_rework"])
        enter_phase("dev", 2)

        state = reduce_all()
        assert_phase_status(state, "test", "completed")

    def test_all_tests_pass_completes_workflow(self, wf_env):
        self._setup_to_test_phase()

        create_task("test_run_001", "test", task_type="test-run")
        run_task("test_run_001", "test", worker_type="test-run")

        transition_phase("test", "done", [
            "all_test_tasks_terminal", "all_tests_passed", "no_critical_failures",
        ])

        state = reduce_all()
        assert_phase_status(state, "test", "completed")
