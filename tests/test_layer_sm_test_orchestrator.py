"""Layer SM — orchestrator-test transitions (T1-T4).

Task 01 of the sm-refactor plan (extras/sm-refactor/tasks/01-test-orchestrator.md).
Red phase: these tests must fail before TEST_TRANSITIONS is added to orch_core.py.

Decisions covered:
    T1 — nesting depth guard (nesting_depth >= 3 → block)
    T2 — state reduction E12 (reduce_exit_code == 1 → escalate_e12)
    T3 — no delivery artifacts gate (dev_completed_tasks_with_delivery == 0 → block)
    T4 — stack worker routing (dispatch with task_type + stack → select_worker intent)
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
DIST_AGENTS = Path(__file__).parent.parent / "dist" / ".claude" / "agents"
sys.path.insert(0, str(DIST_LIB))


class TestTestOrchestratorTransitions:
    def setup_method(self):
        from orch_core import TEST_TRANSITIONS, TestPhaseStateMachine

        self.sm = TestPhaseStateMachine(TEST_TRANSITIONS)

    # T1 — Nesting depth guard
    def test_T1_nesting_depth_3_blocks(self):
        r = self.sm.evaluate("entry", {"nesting_depth": 3, "log_seq_at_spawn": 0})
        assert r.name == "block"
        assert "nesting_depth" in r.params.get("reason", "")

    def test_T1_nesting_depth_4_blocks(self):
        r = self.sm.evaluate("entry", {"nesting_depth": 4, "log_seq_at_spawn": 0})
        assert r.name == "block"

    def test_T1_nesting_depth_under_3_does_not_block(self):
        r = self.sm.evaluate("entry", {"nesting_depth": 2, "log_seq_at_spawn": 5})
        assert r.name != "block"

    # T2 — State reduction E12
    def test_T2_reduce_exit_1_escalates_e12(self):
        r = self.sm.evaluate("post_infra", {"reduce_exit_code": 1, "nesting_depth": 1})
        assert r.name == "escalate_e12"
        assert r.params.get("code") == "E12_state_reduction_failed"
        assert r.params.get("severity") == "critical"

    def test_T2_reduce_exit_0_does_not_escalate(self):
        r = self.sm.evaluate("post_infra", {"reduce_exit_code": 0, "nesting_depth": 1})
        assert r.name != "escalate_e12"

    # T3 — No delivery artifacts gate
    def test_T3_zero_delivery_artifacts_blocks(self):
        r = self.sm.evaluate(
            "post_state",
            {"dev_completed_tasks_with_delivery": 0, "nesting_depth": 1},
        )
        assert r.name == "block"
        assert "delivery" in r.params.get("reason", "")

    def test_T3_with_delivery_artifacts_proceeds(self):
        r = self.sm.evaluate(
            "post_state",
            {"dev_completed_tasks_with_delivery": 3, "nesting_depth": 1},
        )
        assert r.name != "block"

    # T4 — Stack worker routing (returns intent + populated params)
    @pytest.mark.parametrize("stack", ["be", "fe", "fullstack"])
    def test_T4_known_stack_routes_to_select_worker(self, stack):
        r = self.sm.evaluate(
            "dispatch",
            {"task_type": "test-run", "stack": stack, "nesting_depth": 1},
        )
        assert r.name == "select_worker"
        assert r.params["task_type"] == "test-run"
        assert r.params["stack"] == stack

    def test_T4_missing_stack_does_not_route(self):
        r = self.sm.evaluate("dispatch", {"task_type": "test-run", "nesting_depth": 1})
        assert r.name != "select_worker"

    def test_T4_missing_task_type_does_not_route(self):
        r = self.sm.evaluate("dispatch", {"stack": "be", "nesting_depth": 1})
        assert r.name != "select_worker"


class TestSmRunnerForTestMachine:
    # test_runner_lists_test_machine removed — machine registration is asserted for
    # all 5 machines at once by test_layer_sm_cleanup::test_all_5_machines_registered.

    def test_runner_evaluates_T1_block(self):
        inputs = json.dumps({"nesting_depth": 3, "log_seq_at_spawn": 0})
        result = subprocess.run(
            [
                "python3",
                str(DIST_LIB / "sm_runner.py"),
                "--machine",
                "test",
                "--state",
                "entry",
                "--inputs",
                inputs,
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["action"] == "block"

    def test_runner_evaluates_T4_select_worker(self):
        inputs = json.dumps({"task_type": "test-run", "stack": "fe", "nesting_depth": 1})
        result = subprocess.run(
            [
                "python3",
                str(DIST_LIB / "sm_runner.py"),
                "--machine",
                "test",
                "--state",
                "dispatch",
                "--inputs",
                inputs,
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["action"] == "select_worker"
        assert data["params"]["stack"] == "fe"


class TestOrchestratorMdReferencesSmRunner:
    """Green phase must update orchestrator-test.md to call sm_runner.py."""

    # test_orchestrator_test_md_calls_sm_runner removed — covered by the parametrized
    # test_layer_sm_cleanup::test_orchestrator_calls_sm_runner[orchestrator-test.md].

    def test_orchestrator_test_md_uses_test_machine(self):
        content = (DIST_AGENTS / "orchestrator-test.md").read_text()
        assert "--machine test" in content
