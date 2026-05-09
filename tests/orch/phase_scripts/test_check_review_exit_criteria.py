"""
Tests for review-phase exit criteria scripts (Level A).

Scripts under test:
  - check_all_qa_verdicts_approved.py
  - check_no_open_critical_findings.py
  - check_documentation_verified.py
"""
import pytest
import orch_core
from orch_core import append_event

from .conftest import REVIEW_SCRIPTS, phase_env, run_check  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _review_phase(wf_id="wf_review_test"):
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": wf_id,
        "phases": [{"name": "review", "order": 1, "required": True}],
    })
    append_event("orchestrator", "phase_entered", data={"phase": "review", "order": 1, "workflow_id": "wf-fix"})


def _review_task(task_id):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "review", "tier": "standard", "type": "qa",
        "spec": f"delivery/{task_id}.md", "deps": [],
    })


def _complete_review(task_id, project_dir, verdict="approved",
                     has_critical=False, doc_verified=True):
    """Complete a review task and create a qa-report artifact."""
    qa_dir = project_dir / "specs" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / f"{task_id}-qa.md"

    content = f"# QA Report: {task_id}\n\n"
    content += f"verdict: {verdict}\n"
    if has_critical:
        content += "severity: critical\n"
    content += f"documentation_verified: {'true' if doc_verified else 'false'}\n"
    qa_path.write_text(content)

    rel = str(qa_path.relative_to(project_dir))
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "review", "worker_type": "qa", "worker_id": f"w_{task_id}",
    })
    append_event("worker", "task_completed", task_id=task_id, attempt=1, data={
        "phase": "review", "artifacts": [rel], "summary": "qa done",
    })
    return rel


# ---------------------------------------------------------------------------
# check_all_qa_verdicts_approved.py
# ---------------------------------------------------------------------------

class TestAllQaVerdictsApproved:
    def test_no_review_tasks_is_not_met(self, phase_env):
        _review_phase()
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["criterion"] == "all_qa_verdicts_approved"
        assert result["met"] is False
        assert result["evidence"]["total"] == 0

    def test_verdict_rejected_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, verdict="rejected")
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is False
        assert any(
            n["verdict_found"] == "rejected"
            for n in result["evidence"]["not_approved"]
        )

    def test_verdict_approved_is_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, verdict="approved")
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["approved"] == 1

    def test_verdict_approved_with_reservations_is_not_met(self, phase_env):
        # approved_with_reservations is no longer a valid verdict — binary verdict only
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, verdict="approved_with_reservations")
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is False
        assert len(result["evidence"]["not_approved"]) == 1

    def test_mixed_approved_and_rejected_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _review_task("review_dev_tc_002")
        _complete_review("review_dev_tc_001", phase_env, verdict="approved")
        _complete_review("review_dev_tc_002", phase_env, verdict="rejected")
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["approved"] == 1
        assert len(result["evidence"]["not_approved"]) == 1

    def test_all_approved_is_met(self, phase_env):
        _review_phase()
        for i in range(1, 4):
            _review_task(f"review_dev_tc_{i:03d}")
            _complete_review(f"review_dev_tc_{i:03d}", phase_env, verdict="approved")
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["approved"] == 3

    def test_verdict_field_absent_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        # Write qa file without verdict field
        qa_dir = phase_env / "specs" / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        qa_path = qa_dir / "review_dev_tc_001-qa.md"
        qa_path.write_text("# QA Report\n\nsummary: reviewed\n")
        append_event("worker", "task_claimed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review", "worker_type": "qa", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review",
            "artifacts": [str(qa_path.relative_to(phase_env))],
            "summary": "done",
        })
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is False


# ---------------------------------------------------------------------------
# check_no_open_critical_findings.py
# ---------------------------------------------------------------------------

class TestNoOpenCriticalFindings:
    def test_no_review_tasks_is_met(self, phase_env):
        _review_phase()
        result = run_check(REVIEW_SCRIPTS["check_critical"], phase_env)
        assert result["criterion"] == "no_open_critical_findings"
        assert result["met"] is True
        assert result["evidence"]["total"] == 0

    def test_no_critical_severity_is_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, has_critical=False)
        result = run_check(REVIEW_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["clean"] == 1

    def test_critical_finding_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, has_critical=True)
        result = run_check(REVIEW_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is False
        assert any(
            v["reason"] == "critical_finding_present"
            for v in result["evidence"]["with_critical"]
        )

    def test_one_critical_one_clean_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _review_task("review_dev_tc_002")
        _complete_review("review_dev_tc_001", phase_env, has_critical=False)
        _complete_review("review_dev_tc_002", phase_env, has_critical=True)
        result = run_check(REVIEW_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["clean"] == 1
        assert len(result["evidence"]["with_critical"]) == 1


# ---------------------------------------------------------------------------
# check_documentation_verified.py
# ---------------------------------------------------------------------------

class TestDocumentationVerified:
    def test_no_review_tasks_is_not_met(self, phase_env):
        _review_phase()
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["criterion"] == "documentation_verified"
        assert result["met"] is False
        assert result["evidence"]["total"] == 0

    def test_field_absent_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        qa_dir = phase_env / "specs" / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        qa_path = qa_dir / "review_dev_tc_001-qa.md"
        qa_path.write_text("verdict: approved\n")
        append_event("worker", "task_claimed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review", "worker_type": "qa", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review",
            "artifacts": [str(qa_path.relative_to(phase_env))],
            "summary": "done",
        })
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["field_absent"] == 1

    def test_documentation_verified_false_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, doc_verified=False)
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["met"] is False
        assert len(result["evidence"]["verified_false"]) == 1

    def test_documentation_verified_true_is_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, doc_verified=True)
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["verified_true"] == 1

    def test_all_verified_is_met(self, phase_env):
        _review_phase()
        for i in range(1, 3):
            _review_task(f"review_dev_tc_{i:03d}")
            _complete_review(f"review_dev_tc_{i:03d}", phase_env, doc_verified=True)
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["verified_true"] == 2

    def test_one_true_one_false_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _review_task("review_dev_tc_002")
        _complete_review("review_dev_tc_001", phase_env, doc_verified=True)
        _complete_review("review_dev_tc_002", phase_env, doc_verified=False)
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["verified_true"] == 1
        assert len(result["evidence"]["verified_false"]) == 1
