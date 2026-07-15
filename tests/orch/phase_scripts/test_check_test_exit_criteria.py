"""
Tests for test-phase exit criteria scripts (Level A).

Note: phase-test-rules scripts use reduce_all(log_path) with an explicit
path derived from ORCH_PROJECT_DIR, unlike dev/review scripts that use the
global LOG_PATH. Both patterns find the same file when ORCH_PROJECT_DIR
matches the tmp_orch root.

Scripts under test:
  - check_all_test_tasks_terminal.py
  - check_all_tests_passed.py
  - check_no_critical_failures.py
"""
import json

import pytest
import orch_core
from orch_core import append_event

from .conftest import TEST_SCRIPTS, phase_env, run_check  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _test_phase(wf_id="wf_test_test"):
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": wf_id,
        "phases": [{"name": "test", "order": 1, "required": True}],
    })
    append_event("orchestrator", "phase_entered", data={"phase": "test", "order": 1, "workflow_id": "wf-fix"})


def _test_task(task_id):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "test", "tier": "standard", "type": "test-run",
        "spec": f"delivery/{task_id}.md", "deps": [],
    })


def _complete_test(task_id, project_dir, result="passed", has_critical=False, fmt="json"):
    """Complete a test task and create a test-report artifact.

    Default fmt="json" mirrors the canonical producer contract
    (agents/dev/u-test-runner.md writes JSON). fmt="yaml" exercises the tolerant
    fallback path in the checkers.
    """
    report_dir = project_dir / ".orch" / "sessions" / "wf_test_test" / "test-reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        report_path = report_dir / f"{task_id}-report.json"
        report = {"task_id": task_id, "result": result}
        if has_critical:
            report["severity"] = "critical"
        report_path.write_text(json.dumps(report, indent=2))
    else:  # yaml-style fallback
        report_path = report_dir / f"{task_id}-report.md"
        content = f"# Test Report: {task_id}\n\nresult: {result}\n"
        if has_critical:
            content += "severity: critical\n"
        report_path.write_text(content)

    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "test", "worker_type": "test-run", "worker_id": f"w_{task_id}",
    })
    append_event("worker", "task_completed", task_id=task_id, attempt=1, data={
        "phase": "test",
        "artifacts": [str(report_path)],  # test scripts use absolute path
        "summary": f"tests {result}",
    })


def _fail_test_task(task_id):
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "test", "worker_type": "test-run", "worker_id": f"w_{task_id}",
    })
    append_event("worker", "task_failed", task_id=task_id, attempt=1, data={
        "phase": "test", "reason": "internal_error", "retryable": False,
    })
    append_event("orchestrator", "task_dlq", task_id=task_id, data={
        "phase": "test", "reason": "non_retryable", "last_error": "env broken",
    })


# ---------------------------------------------------------------------------
# check_all_test_tasks_terminal.py
# ---------------------------------------------------------------------------

class TestAllTestTasksTerminal:
    def test_no_test_tasks_is_not_met(self, phase_env):
        _test_phase()
        result = run_check(TEST_SCRIPTS["check_terminal"], phase_env)
        assert result["criterion"] == "all_test_tasks_terminal"
        assert result["met"] is False
        assert result["evidence"]["total"] == 0

    def test_running_task_is_not_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        append_event("orchestrator", "task_claimed", task_id="test_dev_tc_001", attempt=1, data={
            "phase": "test", "worker_type": "test-run", "worker_id": "w_001",
        })
        result = run_check(TEST_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is False
        non_terminal = [t["task_id"] for t in result["evidence"]["non_terminal"]]
        assert "test_dev_tc_001" in non_terminal

    def test_all_completed_is_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _test_task("test_dev_tc_002")
        _complete_test("test_dev_tc_001", phase_env)
        _complete_test("test_dev_tc_002", phase_env)
        result = run_check(TEST_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["total"] == 2

    def test_all_dlq_blocks(self, phase_env):
        # prod-hardening task 07 (A4-F4): DLQ now blocks the test->done transition
        # deterministically (was met=True under the old, prompt-trusted behavior).
        _test_phase()
        _test_task("test_dev_tc_001")
        _fail_test_task("test_dev_tc_001")
        result = run_check(TEST_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is False

    def test_pending_task_is_not_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        result = run_check(TEST_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is False


# ---------------------------------------------------------------------------
# check_all_tests_passed.py
# ---------------------------------------------------------------------------

class TestAllTestsPassed:
    def test_no_completed_tasks_is_not_met(self, phase_env):
        _test_phase()
        result = run_check(TEST_SCRIPTS["check_passed"], phase_env)
        assert result["criterion"] == "all_tests_passed"
        assert result["met"] is False
        assert result["evidence"]["total"] == 0

    def test_result_passed_is_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _complete_test("test_dev_tc_001", phase_env, result="passed")
        result = run_check(TEST_SCRIPTS["check_passed"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["passed"] == 1

    def test_result_failed_is_not_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _complete_test("test_dev_tc_001", phase_env, result="failed")
        result = run_check(TEST_SCRIPTS["check_passed"], phase_env)
        assert result["met"] is False
        assert len(result["evidence"]["failed"]) == 1

    def test_result_field_absent_is_not_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        # Write report without result field
        report_dir = phase_env / ".orch" / "sessions" / "wf_test_test" / "test-reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "test_dev_tc_001-report.md"
        report_path.write_text("# Test Report\n\nsummary: no result field\n")
        append_event("worker", "task_claimed", task_id="test_dev_tc_001", attempt=1, data={
            "phase": "test", "worker_type": "test-run", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="test_dev_tc_001", attempt=1, data={
            "phase": "test",
            "artifacts": [str(report_path)],
            "summary": "done",
        })
        result = run_check(TEST_SCRIPTS["check_passed"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["failed"][0]["result"] == "field_absent"

    def test_all_passed_multiple_tasks_is_met(self, phase_env):
        _test_phase()
        for i in range(1, 4):
            _test_task(f"test_dev_tc_{i:03d}")
            _complete_test(f"test_dev_tc_{i:03d}", phase_env, result="passed")
        result = run_check(TEST_SCRIPTS["check_passed"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["passed"] == 3

    def test_one_failed_among_passed_is_not_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _test_task("test_dev_tc_002")
        _complete_test("test_dev_tc_001", phase_env, result="passed")
        _complete_test("test_dev_tc_002", phase_env, result="failed")
        result = run_check(TEST_SCRIPTS["check_passed"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["passed"] == 1
        assert len(result["evidence"]["failed"]) == 1

    # DEF-1: the canonical producer (u-test-runner) writes JSON. The old
    # YAML-only regex never matched a quoted JSON key and blocked green suites.
    def test_json_report_passed_is_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _complete_test("test_dev_tc_001", phase_env, result="passed", fmt="json")
        result = run_check(TEST_SCRIPTS["check_passed"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["passed"] == 1

    def test_json_report_failed_is_not_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _complete_test("test_dev_tc_001", phase_env, result="failed", fmt="json")
        result = run_check(TEST_SCRIPTS["check_passed"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["failed"][0]["result"] == "failed"

    def test_yaml_report_passed_fallback_is_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _complete_test("test_dev_tc_001", phase_env, result="passed", fmt="yaml")
        result = run_check(TEST_SCRIPTS["check_passed"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["passed"] == 1


# ---------------------------------------------------------------------------
# check_no_critical_failures.py
# ---------------------------------------------------------------------------

class TestNoCriticalFailures:
    def test_no_completed_tasks_is_met(self, phase_env):
        _test_phase()
        result = run_check(TEST_SCRIPTS["check_critical"], phase_env)
        assert result["criterion"] == "no_critical_failures"
        assert result["met"] is True
        assert result["evidence"]["total"] == 0

    def test_no_critical_in_report_is_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _complete_test("test_dev_tc_001", phase_env, result="passed", has_critical=False)
        result = run_check(TEST_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["clean"] == 1

    def test_critical_in_report_is_not_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _complete_test("test_dev_tc_001", phase_env, result="failed", has_critical=True)
        result = run_check(TEST_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is False
        assert len(result["evidence"]["with_critical"]) == 1

    def test_one_critical_one_clean_is_not_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _test_task("test_dev_tc_002")
        _complete_test("test_dev_tc_001", phase_env, result="passed", has_critical=False)
        _complete_test("test_dev_tc_002", phase_env, result="failed", has_critical=True)
        result = run_check(TEST_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["clean"] == 1
        assert len(result["evidence"]["with_critical"]) == 1

    # DEF-1 sibling: a JSON "severity": "critical" was silently missed by the
    # YAML-only regex — a genuine critical failure passed the gate undetected.
    def test_json_critical_is_detected(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _complete_test("test_dev_tc_001", phase_env, result="failed", has_critical=True, fmt="json")
        result = run_check(TEST_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is False
        assert len(result["evidence"]["with_critical"]) == 1

    def test_json_no_critical_is_met(self, phase_env):
        _test_phase()
        _test_task("test_dev_tc_001")
        _complete_test("test_dev_tc_001", phase_env, result="passed", has_critical=False, fmt="json")
        result = run_check(TEST_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["clean"] == 1
