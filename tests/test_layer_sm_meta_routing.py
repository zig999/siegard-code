"""Layer SM — meta-orchestrator routing (M5, M7).

Task 03 of the sm-refactor plan (extras/sm-refactor/tasks/03-meta-routing.md).
Red phase: tests must fail before META_TRANSITIONS contains M5/M7 entries.

Decisions covered:
    M5 — Escalation decision gate (info+options → ask_user; else → surface_error)
    M7 — Phase routing (current_phase → orchestrator-{sdd|dev|review|test})
"""
import sys
from pathlib import Path

import pytest

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
sys.path.insert(0, str(DIST_LIB))


class TestMetaEscalationGate:
    """M5 — Escalation decision gate."""

    def setup_method(self):
        from orch_core import META_TRANSITIONS, MetaStateMachine

        self.sm = MetaStateMachine(META_TRANSITIONS)

    def test_M5_info_with_options_asks_user(self):
        r = self.sm.evaluate(
            "escalation_active",
            {
                "escalation_severity": "info",
                "escalation_options": ["confirm_proceed", "abort"],
            },
        )
        assert r.name == "ask_user"
        assert r.params["options"] == ["confirm_proceed", "abort"]

    def test_M5_info_with_single_option_asks_user(self):
        r = self.sm.evaluate(
            "escalation_active",
            {"escalation_severity": "info", "escalation_options": ["retry"]},
        )
        assert r.name == "ask_user"

    def test_M5_info_without_options_surfaces_error(self):
        r = self.sm.evaluate(
            "escalation_active",
            {"escalation_severity": "info", "escalation_options": []},
        )
        assert r.name == "surface_error"

    def test_M5_critical_severity_surfaces_error(self):
        r = self.sm.evaluate(
            "escalation_active",
            {
                "escalation_severity": "critical",
                "escalation_options": ["abort"],
            },
        )
        assert r.name == "surface_error"

    def test_M5_warning_severity_surfaces_error(self):
        r = self.sm.evaluate(
            "escalation_active",
            {
                "escalation_severity": "warning",
                "escalation_options": ["retry"],
            },
        )
        assert r.name == "surface_error"


class TestMetaPhaseRouting:
    """M7 — Phase routing."""

    def setup_method(self):
        from orch_core import META_TRANSITIONS, MetaStateMachine

        self.sm = MetaStateMachine(META_TRANSITIONS)

    @pytest.mark.parametrize(
        "phase,subagent",
        [
            ("sdd", "orchestrator-sdd"),
            ("dev", "orchestrator-dev"),
            ("review", "orchestrator-review"),
            ("test", "orchestrator-test"),
        ],
    )
    def test_M7_phase_routes_to_subagent(self, phase, subagent):
        r = self.sm.evaluate("phase_entry", {"current_phase": phase})
        assert r.name == "spawn_phase_orchestrator"
        assert r.params["subagent_type"] == subagent

    def test_M7_done_routes_workflow_complete(self):
        """HF-03: 'done' is the terminal marker (to_phase of the final
        phase_transitioned) — re-entering phase routing with it must report
        completion, never error('unknown_phase')."""
        r = self.sm.evaluate("phase_entry", {"current_phase": "done"})
        assert r.name == "workflow_complete"

    def test_M7_unknown_phase_returns_error(self):
        r = self.sm.evaluate("phase_entry", {"current_phase": "qa"})
        assert r.name == "error"
        assert "unknown_phase" in r.params.get("reason", "")
        assert r.params.get("phase") == "qa"

    def test_M7_missing_phase_returns_error(self):
        r = self.sm.evaluate("phase_entry", {})
        assert r.name == "error"
