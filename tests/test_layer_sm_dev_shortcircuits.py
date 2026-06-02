"""Layer SM — orchestrator-dev short-circuits (D6, D7).

Task 04 of the sm-refactor plan (extras/sm-refactor/tasks/04-dev-shortcircuits.md).
Red phase: tests must fail before DEV_TRANSITIONS exists in orch_core.py.

Decisions covered:
    D6 — dev_impact: no_action short-circuit (handoff_type ∈ {fast_track, major_evolution} AND
         dev_impact == no_action → exit_vacuous)
    D7 — planner_required skip (workflow_type == improve AND planner_required == false →
         synthesize_backlog_from_triage; missing triage → escalate_e13)
"""
import sys
from pathlib import Path

import pytest

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
sys.path.insert(0, str(DIST_LIB))


class TestDevImpactNoActionShortCircuit:
    """D6 — dev_impact: no_action."""

    def setup_method(self):
        from orch_core import DEV_TRANSITIONS, StateMachine

        self.sm = StateMachine(DEV_TRANSITIONS)

    @pytest.mark.parametrize("handoff_type", ["fast_track", "major_evolution"])
    def test_D6_no_action_exits_vacuously(self, handoff_type):
        r = self.sm.evaluate(
            "post_manifest",
            {"handoff_type": handoff_type, "dev_impact": "no_action"},
        )
        assert r.name == "exit_vacuous"
        assert r.params["next_phase"] == "review"
        assert r.params.get("reason") == "dev_impact_no_action"

    def test_D6_new_domain_no_action_does_not_short_circuit(self):
        r = self.sm.evaluate(
            "post_manifest",
            {"handoff_type": "new_domain", "dev_impact": "no_action"},
        )
        assert r.name != "exit_vacuous"

    def test_D6_reverse_eng_no_action_does_not_short_circuit(self):
        r = self.sm.evaluate(
            "post_manifest",
            {"handoff_type": "reverse_eng", "dev_impact": "no_action"},
        )
        assert r.name != "exit_vacuous"

    def test_D6_fast_track_with_action_proceeds(self):
        r = self.sm.evaluate(
            "post_manifest",
            {"handoff_type": "fast_track", "dev_impact": "moderate"},
        )
        assert r.name != "exit_vacuous"

    def test_D6_major_evolution_with_reevaluate_proceeds(self):
        r = self.sm.evaluate(
            "post_manifest",
            {
                "handoff_type": "major_evolution",
                "dev_impact": "reevaluate_task_contracts",
            },
        )
        assert r.name != "exit_vacuous"


class TestPlannerSkipImproveFlow:
    """D7 — planner_required skip in improve flow."""

    def setup_method(self):
        from orch_core import DEV_TRANSITIONS, StateMachine

        self.sm = StateMachine(DEV_TRANSITIONS)

    def test_D7_improve_planner_not_required_synthesizes(self):
        r = self.sm.evaluate(
            "planning_dispatch",
            {
                "workflow_type": "improve",
                "planner_required": False,
                "triage_present": True,
            },
        )
        assert r.name == "synthesize_backlog_from_triage"
        assert r.params.get("skip_planner") is True

    def test_D7_improve_planner_required_dispatches(self):
        r = self.sm.evaluate(
            "planning_dispatch",
            {
                "workflow_type": "improve",
                "planner_required": True,
                "triage_present": True,
            },
        )
        assert r.name == "dispatch_planner"

    def test_D7_standard_workflow_always_dispatches(self):
        # planner_required is irrelevant for standard workflow
        r = self.sm.evaluate(
            "planning_dispatch",
            {
                "workflow_type": "standard",
                "planner_required": False,
                "triage_present": True,
            },
        )
        assert r.name == "dispatch_planner"

    def test_D7_improve_skip_with_missing_triage_escalates(self):
        r = self.sm.evaluate(
            "planning_dispatch",
            {
                "workflow_type": "improve",
                "planner_required": False,
                "triage_present": False,
            },
        )
        assert r.name == "escalate_e13"
        assert "triage_missing" in r.params.get("reason", "")
        assert r.params.get("code") == "E13_improve_scope_unusable"

    def test_D7_improve_planner_required_does_not_check_triage(self):
        # When dispatching planner, triage_present is irrelevant for the SM decision
        r = self.sm.evaluate(
            "planning_dispatch",
            {
                "workflow_type": "improve",
                "planner_required": True,
                "triage_present": False,
            },
        )
        assert r.name == "dispatch_planner"


class TestDevMachineRegistered:
    def test_dev_in_registered_machines(self):
        import json
        import subprocess

        result = subprocess.run(
            ["python3", str(DIST_LIB / "sm_runner.py"), "--list"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "dev" in data["registered_machines"]
