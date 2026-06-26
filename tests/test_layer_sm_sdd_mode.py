"""Layer SM — orchestrator-sdd mode derivation (S4-S8).

Task 08 of the sm-refactor plan (extras/sm-refactor/tasks/08-sdd-mode-derivation.md).
Red phase: tests must fail before SDD_TRANSITIONS exists in orch_core.py.

Decisions covered:
    S4 — type=implementation_only short-circuit
    S5 — effective_mode derivation (trigger × mode_hint)
    S6 — bypass_e99 derivation (trigger == u-improve)
    S7 — targeted/standard branch (effective_mode)
    S8 — greenfield routing (greenfield → use triage.domains | scan filesystem)
"""
import sys
from pathlib import Path

import pytest

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
sys.path.insert(0, str(DIST_LIB))


class TestSddModeDerivation:
    def setup_method(self):
        from orch_core import SDD_TRANSITIONS, SddStateMachine

        self.sm = SddStateMachine(SDD_TRANSITIONS)

    # S4 — type=implementation_only short-circuit
    def test_S4_implementation_only_exits(self):
        r = self.sm.evaluate(
            "triage_done",
            {
                "type": "implementation_only",
                "trigger": "u-improve",
                "mode_hint": "fast-track:patch",
            },
        )
        assert r.name == "exit_no_spec_change"
        assert r.params.get("next_phase") == "dev"
        assert r.params.get("reason") == "implementation_only_no_spec_change"

    def test_S4_implementation_only_with_u_spec_still_exits(self):
        r = self.sm.evaluate(
            "triage_done",
            {"type": "implementation_only", "trigger": "u-spec", "mode_hint": "full"},
        )
        assert r.name == "exit_no_spec_change"

    # S5 + S6 — effective_mode + bypass_e99 (combined)
    @pytest.mark.parametrize(
        "trigger,mode_hint,expected_mode,expected_bypass",
        [
            ("u-spec", "full", "standard", False),
            ("u-spec", "fast-track:patch", "standard", False),
            ("u-spec", "fast-track:minor", "standard", False),
            ("u-improve", "full", "standard", True),
            ("u-improve", "fast-track:minor", "targeted", True),
            ("u-improve", "fast-track:patch", "targeted", True),
        ],
    )
    def test_S5_S6_dispatch_pipeline(self, trigger, mode_hint, expected_mode, expected_bypass):
        r = self.sm.evaluate(
            "triage_done",
            {
                "type": "spec_change_required",
                "trigger": trigger,
                "mode_hint": mode_hint,
            },
        )
        assert r.name == "dispatch_pipeline"
        assert r.params["effective_mode"] == expected_mode
        assert r.params["bypass_e99"] == expected_bypass


class TestSddTargetedBranch:
    """S7 — Targeted vs Standard branch."""

    def setup_method(self):
        from orch_core import SDD_TRANSITIONS, SddStateMachine

        self.sm = SddStateMachine(SDD_TRANSITIONS)

    def test_S7_targeted_skips_to_step_4(self):
        r = self.sm.evaluate("post_mode_declared", {"effective_mode": "targeted"})
        assert r.name == "goto_step"
        assert r.params["step"] == "step_4_targeted"

    def test_S7_standard_proceeds_to_step_2(self):
        r = self.sm.evaluate("post_mode_declared", {"effective_mode": "standard"})
        assert r.name == "goto_step"
        assert r.params["step"] == "step_2_assess"


class TestSddGreenfieldRouting:
    """S8 — Greenfield routing."""

    def setup_method(self):
        from orch_core import SDD_TRANSITIONS, SddStateMachine

        self.sm = SddStateMachine(SDD_TRANSITIONS)

    def test_S8_greenfield_true_uses_triage_domains(self):
        r = self.sm.evaluate(
            "assess_pipeline",
            {"greenfield": True, "triage_domains": ["auth", "billing"]},
        )
        assert r.name == "use_triage_domains"
        assert r.params["domains"] == ["auth", "billing"]

    def test_S8_greenfield_true_with_empty_domains(self):
        r = self.sm.evaluate("assess_pipeline", {"greenfield": True, "triage_domains": []})
        assert r.name == "use_triage_domains"
        assert r.params["domains"] == []

    def test_S8_greenfield_false_scans_filesystem(self):
        r = self.sm.evaluate(
            "assess_pipeline", {"greenfield": False, "triage_domains": []}
        )
        assert r.name == "scan_filesystem"


class TestSddMachineRegistered:
    def test_sdd_in_registered_machines(self):
        import json
        import subprocess

        result = subprocess.run(
            ["python3", str(DIST_LIB / "sm_runner.py"), "--list"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "sdd" in data["registered_machines"]
