"""Layer SM — orchestrator-review qa_mode + concurrency (R4, R9).

Task 06 of the sm-refactor plan (extras/sm-refactor/tasks/06-review-qa-mode.md).
Red phase: tests must fail before REVIEW_TRANSITIONS exists in orch_core.py.

Decisions covered:
    R4 — qa_mode classification routing (output of classify_qa_mode.py drives create_qa_task)
    R9 — Dynamic concurrency by qa_mode window (min of CONCURRENCY[m] over candidates)
"""
import sys
from pathlib import Path

import pytest

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
sys.path.insert(0, str(DIST_LIB))


class TestReviewQaMode:
    """R4 — qa_mode classification routing."""

    def setup_method(self):
        from orch_core import REVIEW_TRANSITIONS, ReviewStateMachine

        self.sm = ReviewStateMachine(REVIEW_TRANSITIONS)

    @pytest.mark.parametrize(
        "qa_mode,expected_concurrency",
        [
            ("micro", 5),
            ("standard", 3),
            ("full", 2),
        ],
    )
    def test_R4_qa_mode_to_concurrency_hint(self, qa_mode, expected_concurrency):
        r = self.sm.evaluate(
            "classify_qa_mode_done",
            {"qa_mode": qa_mode, "rationale": "test_rationale"},
        )
        assert r.name == "create_qa_task"
        assert r.params["qa_mode"] == qa_mode
        assert r.params["concurrency_hint"] == expected_concurrency
        assert r.params.get("rationale") == "test_rationale"

    def test_R4_classifier_failed_defaults_to_standard(self):
        r = self.sm.evaluate(
            "classify_qa_mode_done",
            {"qa_mode": None, "classifier_failed": True},
        )
        assert r.name == "create_qa_task"
        assert r.params["qa_mode"] == "standard"
        assert r.params["concurrency_hint"] == 3
        assert r.params.get("warn_emitted") is True
        assert r.params.get("code") == "E19_qa_mode_classifier_failed"


class TestReviewDynamicConcurrency:
    """R9 — Dynamic concurrency by qa_mode window."""

    def setup_method(self):
        from orch_core import REVIEW_TRANSITIONS, ReviewStateMachine

        self.sm = ReviewStateMachine(REVIEW_TRANSITIONS)

    def test_R9_all_micro_uses_5(self):
        r = self.sm.evaluate(
            "select_batch", {"qa_modes_in_window": ["micro", "micro", "micro"]}
        )
        assert r.name == "set_max_concurrent"
        assert r.params["max_concurrent"] == 5

    def test_R9_mixed_uses_min(self):
        r = self.sm.evaluate(
            "select_batch", {"qa_modes_in_window": ["micro", "standard", "micro"]}
        )
        assert r.params["max_concurrent"] == 3  # min(5, 3, 5)

    def test_R9_full_anywhere_caps_to_2(self):
        r = self.sm.evaluate(
            "select_batch", {"qa_modes_in_window": ["micro", "full", "standard"]}
        )
        assert r.params["max_concurrent"] == 2

    def test_R9_empty_window_defaults_to_2(self):
        r = self.sm.evaluate("select_batch", {"qa_modes_in_window": []})
        assert r.params["max_concurrent"] == 2

    def test_R9_unknown_modes_treated_as_2(self):
        r = self.sm.evaluate(
            "select_batch", {"qa_modes_in_window": ["unknown", "micro"]}
        )
        assert r.params["max_concurrent"] == 2  # min(2, 5)

    def test_R9_all_standard_uses_3(self):
        r = self.sm.evaluate(
            "select_batch", {"qa_modes_in_window": ["standard", "standard"]}
        )
        assert r.params["max_concurrent"] == 3


class TestReviewMachineRegistered:
    def test_review_in_registered_machines(self):
        import json
        import subprocess

        result = subprocess.run(
            ["python3", str(DIST_LIB / "sm_runner.py"), "--list"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "review" in data["registered_machines"]
