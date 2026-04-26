"""
Tests for dev-phase exit criteria scripts (Level A).

Each test builds a log fixture in-process (via orch_core), then runs the
check script as a subprocess using the same ORCH_PROJECT_DIR.

Scripts under test:
  - check_all_impl_tasks_terminal.py
  - check_all_deliveries_qa_ready.py
  - check_no_open_prohibitions.py
"""
import pytest
import orch_core
from orch_core import append_event, TaskStatus

from .conftest import DEV_SCRIPTS, phase_env, run_check  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dev_phase(wf_id="wf_dev_test"):
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": wf_id,
        "phases": [{"name": "dev", "order": 1, "required": True}],
    })
    append_event("orchestrator", "phase_entered", data={"phase": "dev", "order": 1})


def _impl_task(task_id, deps=None):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "dev", "tier": "standard", "type": "impl",
        "spec": f"spec/{task_id}.md", "deps": deps or [],
    })


def _complete_with_delivery(task_id, project_dir, qa_ready=True, has_violations=False):
    """Complete a task and create a delivery.md artifact."""
    delivery_dir = project_dir / ".orch" / "sessions" / "wf_dev_test" / "delivery"
    delivery_dir.mkdir(parents=True, exist_ok=True)
    delivery_path = delivery_dir / f"{task_id}-delivery.md"

    content = f"# Delivery: {task_id}\n\n"
    content += f"qa_ready: {'true' if qa_ready else 'false'}\n"
    if has_violations:
        content += "prohibition_violations:\n  - something forbidden\n"
    else:
        content += "prohibition_violations: []\n"
    delivery_path.write_text(content)

    rel_path = str(delivery_path.relative_to(project_dir))
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "dev", "worker_type": "impl", "worker_id": f"w_{task_id}",
    })
    append_event("worker", "task_completed", task_id=task_id, attempt=1, data={
        "phase": "dev", "artifacts": [rel_path], "summary": "done",
    })
    return rel_path


def _fail_task(task_id, retryable=False):
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "dev", "worker_type": "impl", "worker_id": f"w_{task_id}",
    })
    append_event("worker", "task_failed", task_id=task_id, attempt=1, data={
        "phase": "dev", "reason": "runtime_error", "retryable": retryable,
    })
    if not retryable:
        append_event("orchestrator", "task_dlq", task_id=task_id, data={
            "phase": "dev", "reason": "non_retryable", "last_error": "exit 1",
        })


# ---------------------------------------------------------------------------
# check_all_impl_tasks_terminal.py
# ---------------------------------------------------------------------------

class TestAllImplTasksTerminal:
    def test_no_dev_tasks_is_not_met(self, phase_env):
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["criterion"] == "all_impl_tasks_terminal"
        assert result["met"] is False
        assert result["evidence"]["total"] == 0

    def test_running_task_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        append_event("orchestrator", "task_claimed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_001",
        })
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is False
        non_terminal = [t["task_id"] for t in result["evidence"]["non_terminal"]]
        assert "dev_tc_001" in non_terminal

    def test_pending_task_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is False

    def test_all_completed_is_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _impl_task("dev_tc_002")
        _complete_with_delivery("dev_tc_001", phase_env)
        _complete_with_delivery("dev_tc_002", phase_env)
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["total"] == 2
        assert result["evidence"]["terminal"] == 2

    def test_all_dlq_is_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _fail_task("dev_tc_001", retryable=False)
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is True

    def test_mixed_completed_and_dlq_is_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _impl_task("dev_tc_002")
        _complete_with_delivery("dev_tc_001", phase_env)
        _fail_task("dev_tc_002", retryable=False)
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is True

    def test_one_running_one_completed_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _impl_task("dev_tc_002")
        _complete_with_delivery("dev_tc_001", phase_env)
        append_event("orchestrator", "task_claimed", task_id="dev_tc_002", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_002",
        })
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is False
        non_terminal = [t["task_id"] for t in result["evidence"]["non_terminal"]]
        assert "dev_tc_002" in non_terminal


# ---------------------------------------------------------------------------
# check_all_deliveries_qa_ready.py
# ---------------------------------------------------------------------------

class TestAllDeliveriesQaReady:
    def test_no_completed_tasks_is_not_met(self, phase_env):
        _dev_phase()
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["criterion"] == "all_deliveries_qa_ready"
        assert result["met"] is False
        assert result["evidence"]["total"] == 0

    def test_delivery_file_not_found_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        # Complete but artifact path points nowhere
        append_event("worker", "task_claimed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev",
            "artifacts": ["does/not/exist/dev_tc_001-delivery.md"],
            "summary": "done",
        })
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["not_ready"][0]["reason"] == "file_not_found"

    def test_qa_ready_false_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _complete_with_delivery("dev_tc_001", phase_env, qa_ready=False)
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is False
        assert any(n["reason"] == "qa_ready_not_true" for n in result["evidence"]["not_ready"])

    def test_qa_ready_true_is_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _complete_with_delivery("dev_tc_001", phase_env, qa_ready=True)
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["ready"] == 1

    def test_all_tasks_qa_ready_is_met(self, phase_env):
        _dev_phase()
        for i in range(1, 4):
            _impl_task(f"dev_tc_{i:03d}")
            _complete_with_delivery(f"dev_tc_{i:03d}", phase_env, qa_ready=True)
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["ready"] == 3

    def test_mixed_ready_and_not_ready_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _impl_task("dev_tc_002")
        _complete_with_delivery("dev_tc_001", phase_env, qa_ready=True)
        _complete_with_delivery("dev_tc_002", phase_env, qa_ready=False)
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["ready"] == 1
        assert len(result["evidence"]["not_ready"]) == 1

    def test_only_delivery_artifacts_are_checked(self, phase_env):
        """Non-delivery artifacts in task_completed are ignored."""
        _dev_phase()
        _impl_task("dev_tc_001")
        append_event("worker", "task_claimed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev",
            "artifacts": ["some/other/artifact.md"],  # no "delivery" in name
            "summary": "done",
        })
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["total"] == 0


# ---------------------------------------------------------------------------
# check_no_open_prohibitions.py
# ---------------------------------------------------------------------------

class TestNoOpenProhibitions:
    def test_no_completed_tasks_is_met(self, phase_env):
        _dev_phase()
        result = run_check(DEV_SCRIPTS["check_prohibitions"], phase_env)
        assert result["criterion"] == "no_open_prohibitions"
        assert result["met"] is True
        assert result["evidence"]["total"] == 0

    def test_delivery_with_no_violations_is_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _complete_with_delivery("dev_tc_001", phase_env, has_violations=False)
        result = run_check(DEV_SCRIPTS["check_prohibitions"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["clean"] == 1

    def test_delivery_with_violations_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _complete_with_delivery("dev_tc_001", phase_env, has_violations=True)
        result = run_check(DEV_SCRIPTS["check_prohibitions"], phase_env)
        assert result["met"] is False
        assert any(
            v["reason"] == "prohibition_violations_present"
            for v in result["evidence"]["violations"]
        )

    def test_one_violation_one_clean_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _impl_task("dev_tc_002")
        _complete_with_delivery("dev_tc_001", phase_env, has_violations=False)
        _complete_with_delivery("dev_tc_002", phase_env, has_violations=True)
        result = run_check(DEV_SCRIPTS["check_prohibitions"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["clean"] == 1
        assert len(result["evidence"]["violations"]) == 1

    def test_file_not_found_counts_as_violation(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        append_event("worker", "task_claimed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev",
            "artifacts": ["missing/dev_tc_001-delivery.md"],
            "summary": "done",
        })
        result = run_check(DEV_SCRIPTS["check_prohibitions"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["violations"][0]["reason"] == "file_not_found"
