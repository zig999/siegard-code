"""E2E regression (5-a acceptance): two sequential workflows in ONE shared log,
with coinciding LOCAL TC numbers, produce disjoint task sets.

Eternal incident shape (log seqs 155-160 vs 750-756): workflow ingest-screen
completed dev_tc_001 + review_dev_tc_001; workflow error-taxonomy-unify reused
the same TC numbers — the review orchestrator's skip-if-exists found the OLD
completed review tasks and would have suppressed QA silently. With 5-a IDs are
workflow-namespaced, so the second workflow's tasks never collide with the
first's, the first workflow's derived state is never reset, and per-workflow
reduction separates them cleanly.
"""
import pytest
import orch_core
from orch_core import TaskStatus, append_event, reduce_all, reduce_workflow


def _run_workflow(wf: str, phases=("dev",)) -> None:
    """Simulate one workflow: declare, enter dev, run its namespaced TC + review."""
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": wf,
        "phases": [{"name": ph, "order": i + 1, "required": True}
                   for i, ph in enumerate(phases)],
    })
    append_event("orchestrator", "phase_entered",
                 data={"phase": "dev", "order": 1, "workflow_id": wf})
    dev_id = f"dev_{wf}_tc_001"
    append_event("orchestrator-dev", "task_created", task_id=dev_id, data={
        "phase": "dev", "workflow_id": wf, "tier": "standard", "type": "impl",
        "spec": f".orch/sessions/{wf}/backlog/tc-001.md", "deps": [],
    })
    append_event("orchestrator-dev", "task_claimed", task_id=dev_id, data={
        "phase": "dev", "worker_type": "impl", "worker_id": f"u-be-developer-{dev_id}",
    })
    append_event("worker", "task_completed", task_id=dev_id, data={
        "phase": "dev", "artifacts": [f".orch/sessions/{wf}/delivery/tc-001-delivery.md"],
    })
    review_id = f"review_{dev_id}"
    append_event("orchestrator-review", "task_created", task_id=review_id, data={
        "phase": "dev", "workflow_id": wf, "tier": "standard", "type": "qa",
        "spec": f".orch/sessions/{wf}/delivery/tc-001-delivery.md",
        "dev_task_id": dev_id, "deps": [],
    })
    append_event("orchestrator-review", "task_claimed", task_id=review_id, data={
        "phase": "dev", "worker_type": "qa", "worker_id": f"u-be-qa-{review_id}",
    })
    append_event("worker", "task_completed", task_id=review_id, data={
        "phase": "dev", "artifacts": [f".orch/sessions/{wf}/qa/tc-001-verdict.yaml"],
    })
    # close the workflow's phase so the next workflow can enter its own
    append_event("orchestrator", "phase_exit_approved", data={
        "phase": "dev", "criteria_met": ["all_impl_tasks_terminal"],
        "next_phase": "review", "workflow_id": wf,
    })
    append_event("orchestrator", "phase_transitioned", data={
        "from_phase": "dev", "to_phase": "review", "evidence_seq": 1, "workflow_id": wf,
    })


@pytest.fixture
def two_workflows(tmp_orch):
    _run_workflow("ingest-screen")
    _run_workflow("etax-unify")
    return tmp_orch


class TestTwoWorkflowsSharedLog:
    def test_task_sets_are_disjoint(self, two_workflows):
        """Same LOCAL TC number, zero shared task IDs (audit acceptance)."""
        state = reduce_all()
        assert "dev_ingest-screen_tc_001" in state.tasks
        assert "dev_etax-unify_tc_001" in state.tasks
        assert "review_dev_ingest-screen_tc_001" in state.tasks
        assert "review_dev_etax-unify_tc_001" in state.tasks

    def test_first_workflow_state_never_reset(self, two_workflows):
        """Legacy failure mode: wf2 re-creating dev_tc_001 reset wf1's completed
        task to pending. Namespaced IDs make that impossible."""
        state = reduce_all()
        assert state.tasks["dev_ingest-screen_tc_001"].status == TaskStatus.COMPLETED
        assert state.tasks["review_dev_ingest-screen_tc_001"].status == TaskStatus.COMPLETED

    def test_qa_not_suppressed_for_second_workflow(self, two_workflows):
        """The eternal E21 shape: wf2's review task exists AND is its own —
        linked to wf2's session — not a stale hit on wf1's completed review."""
        state = reduce_all()
        wf2_review = state.tasks["review_dev_etax-unify_tc_001"]
        assert wf2_review.status == TaskStatus.COMPLETED
        assert ".orch/sessions/etax-unify/" in wf2_review.spec

    def test_reduce_workflow_separates_cleanly(self, two_workflows):
        s1 = reduce_workflow("ingest-screen")
        s2 = reduce_workflow("etax-unify")
        assert set(s1.tasks) == {"dev_ingest-screen_tc_001", "review_dev_ingest-screen_tc_001"}
        assert set(s2.tasks) == {"dev_etax-unify_tc_001", "review_dev_etax-unify_tc_001"}

    def test_no_anomalies_and_no_illegal_transitions(self, two_workflows):
        """The whole two-workflow log replays strictly with zero absorbed
        duplicates — collisions are prevented, not just tolerated."""
        state = reduce_all()
        assert state.anomalies == []
