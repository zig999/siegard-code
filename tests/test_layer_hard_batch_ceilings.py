"""Layer Hard Batch Ceilings — per-phase concurrency cap in Python (task 09).

A6-F2: DEV/SDD/TEST batch ceilings were English prose ("select up to 2 tasks")
the orchestrator LLM was trusted to honor; only REVIEW returned its ceiling from
Python (_r9_compute_max_concurrent). Now all four phases expose a `select_batch`
SM state returning set_max_concurrent.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dist" / ".claude" / "lib"))


class TestBatchCeilings:
    def test_dev_caps_at_2(self):
        from orch_core import DEV_TRANSITIONS, DevStateMachine
        r = DevStateMachine(DEV_TRANSITIONS).evaluate("select_batch", {"ready_count": 5})
        assert r.name == "set_max_concurrent"
        assert r.params["max_concurrent"] == 2

    def test_test_caps_at_2(self):
        from orch_core import TEST_TRANSITIONS, TestPhaseStateMachine
        r = TestPhaseStateMachine(TEST_TRANSITIONS).evaluate("select_batch", {})
        assert r.name == "set_max_concurrent"
        assert r.params["max_concurrent"] == 2

    def test_sdd_standard_caps_at_2(self):
        from orch_core import SDD_TRANSITIONS, SddStateMachine
        r = SddStateMachine(SDD_TRANSITIONS).evaluate("select_batch", {"effective_mode": "standard"})
        assert r.name == "set_max_concurrent"
        assert r.params["max_concurrent"] == 2

    def test_sdd_targeted_caps_at_1(self):
        from orch_core import SDD_TRANSITIONS, SddStateMachine
        r = SddStateMachine(SDD_TRANSITIONS).evaluate("select_batch", {"effective_mode": "targeted"})
        assert r.name == "set_max_concurrent"
        assert r.params["max_concurrent"] == 1

    def test_review_unchanged(self):
        # REVIEW keeps its dynamic qa_mode ceiling (micro=5) — not regressed.
        from orch_core import REVIEW_TRANSITIONS, ReviewStateMachine
        r = ReviewStateMachine(REVIEW_TRANSITIONS).evaluate("select_batch", {"qa_modes_in_window": ["micro"]})
        assert r.name == "set_max_concurrent"
        assert r.params["max_concurrent"] == 5

    def test_all_four_phases_expose_select_batch(self):
        from orch_core import (DEV_TRANSITIONS, REVIEW_TRANSITIONS, SDD_TRANSITIONS,
                               TEST_TRANSITIONS)
        for table in (DEV_TRANSITIONS, SDD_TRANSITIONS, TEST_TRANSITIONS, REVIEW_TRANSITIONS):
            assert any(state == "select_batch" for (state, _pred) in table)

    def test_orchestrators_read_ceiling_from_sm(self):
        # A6-F2: all four orchestrators must read the cap via sm_runner select_batch,
        # not a prose literal.
        agents = Path(__file__).parent.parent / "dist" / ".claude" / "agents"
        for name in ("orchestrator-dev", "orchestrator-sdd", "orchestrator-test", "orchestrator-review"):
            src = (agents / f"{name}.md").read_text(encoding="utf-8")
            assert "--state select_batch" in src, f"{name} must read the SM batch ceiling"


class TestDevConfigurableCeiling:
    """SIEGARD-02 — the dev batch ceiling is config-driven (dispatch_policy.dev)."""

    def _eval(self, inputs):
        from orch_core import DEV_TRANSITIONS, DevStateMachine
        return DevStateMachine(DEV_TRANSITIONS).evaluate("select_batch", inputs)

    def test_config_raises_ceiling(self):
        r = self._eval({"dispatch_policy": {"dev": {"max_concurrent": 5}}})
        assert r.params["max_concurrent"] == 5

    def test_default_when_no_policy(self):
        # Regression: absent dispatch_policy keeps the historical default of 2.
        assert self._eval({}).params["max_concurrent"] == 2

    def test_invalid_value_falls_back_to_2(self):
        r = self._eval({"dispatch_policy": {"dev": {"max_concurrent": "lots"}}})
        assert r.params["max_concurrent"] == 2

    def test_clamps_below_one_to_2(self):
        r = self._eval({"dispatch_policy": {"dev": {"max_concurrent": 0}}})
        assert r.params["max_concurrent"] == 2

    def test_default_config_declares_dispatch_policy(self):
        from orch_core import default_config
        assert default_config()["dispatch_policy"]["dev"]["max_concurrent"] == 2

    def test_helper_unit(self):
        from orch_core import _dev_max_concurrent
        assert _dev_max_concurrent({"dev": {"max_concurrent": 4}}) == 4
        assert _dev_max_concurrent({}) == 2
        assert _dev_max_concurrent(None) == 2
        assert _dev_max_concurrent({"dev": {"max_concurrent": -1}}) == 2
