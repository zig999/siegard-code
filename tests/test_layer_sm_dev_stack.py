"""Layer SM — orchestrator-dev stack-conditional dispatch (D8, D9).

Task 05 of the sm-refactor plan (extras/sm-refactor/tasks/05-dev-stack-dispatch.md).
Red phase: tests must fail before D8/D9 transitions are added to DEV_TRANSITIONS.

Decisions covered:
    D8 — Stack-conditional planning dispatch (fullstack → parallel; be|fe → single; unknown → error)
    D9 — Stack propagation per task (task.stack > project.stack fallback)
"""
import sys
from pathlib import Path

import pytest

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
sys.path.insert(0, str(DIST_LIB))


class TestDevStackDispatch:
    """D8 — Stack-conditional planning dispatch."""

    def setup_method(self):
        from orch_core import DEV_TRANSITIONS, DevStateMachine

        self.sm = DevStateMachine(DEV_TRANSITIONS)

    def test_D8_fullstack_dispatches_parallel_planners(self):
        r = self.sm.evaluate("dispatch_planner_stack", {"stack": "fullstack"})
        assert r.name == "dispatch_parallel_planners"
        assert "u-be-planner" in r.params["workers"]
        assert "u-fe-planner" in r.params["workers"]
        assert "dev_planning_be" in r.params["tasks"]
        assert "dev_planning_fe" in r.params["tasks"]

    def test_D8_be_dispatches_single_be_planner(self):
        r = self.sm.evaluate("dispatch_planner_stack", {"stack": "be"})
        assert r.name == "dispatch_single_planner"
        assert r.params["stack"] == "be"
        assert r.params["worker"] == "u-be-planner"

    def test_D8_fe_dispatches_single_fe_planner(self):
        r = self.sm.evaluate("dispatch_planner_stack", {"stack": "fe"})
        assert r.name == "dispatch_single_planner"
        assert r.params["stack"] == "fe"
        assert r.params["worker"] == "u-fe-planner"

    def test_D8_unknown_stack_errors(self):
        r = self.sm.evaluate("dispatch_planner_stack", {"stack": "mobile"})
        assert r.name == "error"
        assert r.params.get("reason") == "unknown_stack"
        assert r.params.get("stack") == "mobile"

    def test_D8_missing_stack_errors(self):
        r = self.sm.evaluate("dispatch_planner_stack", {})
        assert r.name == "error"


class TestDevStackPropagation:
    """D9 — Stack propagation per task."""

    def setup_method(self):
        from orch_core import DEV_TRANSITIONS, DevStateMachine

        self.sm = DevStateMachine(DEV_TRANSITIONS)

    def test_D9_task_stack_wins_over_project_stack(self):
        r = self.sm.evaluate(
            "dispatch_impl_task",
            {"task_stack": "fe", "project_stack": "fullstack", "task_type": "impl"},
        )
        assert r.name == "select_worker"
        assert r.params["stack"] == "fe"
        assert r.params["task_type"] == "impl"

    def test_D9_task_stack_be_wins_over_project_stack(self):
        r = self.sm.evaluate(
            "dispatch_impl_task",
            {"task_stack": "be", "project_stack": "fullstack", "task_type": "impl"},
        )
        assert r.params["stack"] == "be"

    def test_D9_task_stack_null_falls_back_to_project_stack(self):
        r = self.sm.evaluate(
            "dispatch_impl_task",
            {"task_stack": None, "project_stack": "be", "task_type": "impl"},
        )
        assert r.name == "select_worker"
        assert r.params["stack"] == "be"

    def test_D9_task_stack_missing_falls_back_to_project_stack(self):
        r = self.sm.evaluate(
            "dispatch_impl_task",
            {"project_stack": "fe", "task_type": "impl"},
        )
        assert r.name == "select_worker"
        assert r.params["stack"] == "fe"

    def test_D9_no_resolvable_stack_errors(self):
        r = self.sm.evaluate(
            "dispatch_impl_task",
            {"task_stack": None, "project_stack": None, "task_type": "impl"},
        )
        assert r.name == "error"
        assert "no_resolvable_stack" in r.params.get("reason", "")

    def test_D9_task_stack_unknown_value_falls_back(self):
        # An invalid task_stack like "mobile" should fall back to project_stack
        r = self.sm.evaluate(
            "dispatch_impl_task",
            {"task_stack": "mobile", "project_stack": "be", "task_type": "impl"},
        )
        assert r.name == "select_worker"
        assert r.params["stack"] == "be"
