"""Layer SM — orchestrator-review auto-approval gate (R10, R11).

Task 07 of the sm-refactor plan (extras/sm-refactor/tasks/07-review-auto-approval.md).
Red phase: tests must fail before R10/R11 entries are added to REVIEW_TRANSITIONS.

Decisions covered:
    R10 — Auto-approval gate (R1-R4 strict; auto_approve OR manual_gate with disqualified_by)
    R11 — human_response.action routing (approve | return_to_dev | return_partial | unknown)
"""
import sys
from pathlib import Path

import pytest

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
sys.path.insert(0, str(DIST_LIB))


class TestAutoApprovalGate:
    """R10 — Auto-approval gate (4 strict rules)."""

    def setup_method(self):
        from orch_core import REVIEW_TRANSITIONS, ReviewStateMachine

        self.sm = ReviewStateMachine(REVIEW_TRANSITIONS)

    def test_R10_all_rules_pass_auto_approves(self):
        r = self.sm.evaluate(
            "approval_gate",
            {
                "completed_review_tasks_count": 3,
                "all_qa_mode_micro": True,
                "all_verdicts_approved": True,
                "any_severe_findings": False,
            },
        )
        assert r.name == "auto_approve"
        assert r.params.get("synthesized_human_response") is True
        assert r.params.get("auto_approved") is True
        assert r.params.get("audit_code") == "E18_auto_approval_granted"

    def test_R10_R1_zero_tasks_falls_through(self):
        r = self.sm.evaluate(
            "approval_gate",
            {
                "completed_review_tasks_count": 0,
                "all_qa_mode_micro": True,
                "all_verdicts_approved": True,
                "any_severe_findings": False,
            },
        )
        assert r.name == "manual_gate"
        assert "R1" in r.params.get("disqualified_by", "")

    def test_R10_R2_non_micro_falls_through(self):
        r = self.sm.evaluate(
            "approval_gate",
            {
                "completed_review_tasks_count": 3,
                "all_qa_mode_micro": False,
                "all_verdicts_approved": True,
                "any_severe_findings": False,
            },
        )
        assert r.name == "manual_gate"
        assert "R2" in r.params.get("disqualified_by", "")

    def test_R10_R3_rejection_falls_through(self):
        r = self.sm.evaluate(
            "approval_gate",
            {
                "completed_review_tasks_count": 3,
                "all_qa_mode_micro": True,
                "all_verdicts_approved": False,
                "any_severe_findings": False,
            },
        )
        assert r.name == "manual_gate"
        assert "R3" in r.params.get("disqualified_by", "")

    def test_R10_R4_severe_finding_falls_through(self):
        r = self.sm.evaluate(
            "approval_gate",
            {
                "completed_review_tasks_count": 3,
                "all_qa_mode_micro": True,
                "all_verdicts_approved": True,
                "any_severe_findings": True,
            },
        )
        assert r.name == "manual_gate"
        assert "R4" in r.params.get("disqualified_by", "")


class TestHumanResponseRouting:
    """R11 — human_response.action routing."""

    def setup_method(self):
        from orch_core import REVIEW_TRANSITIONS, ReviewStateMachine

        self.sm = ReviewStateMachine(REVIEW_TRANSITIONS)

    def test_R11_approve_proceeds_to_exit(self):
        r = self.sm.evaluate("human_response_received", {"action": "approve"})
        assert r.name == "proceed_to_exit"

    def test_R11_return_to_dev_full(self):
        r = self.sm.evaluate("human_response_received", {"action": "return_to_dev"})
        assert r.name == "return_to_dev"
        assert r.params["scope"] == "full"

    def test_R11_return_partial_with_ids(self):
        r = self.sm.evaluate(
            "human_response_received",
            {
                "action": "return_partial",
                "rejected_task_ids": ["dev_tc_001", "dev_tc_003"],
            },
        )
        assert r.name == "return_to_dev"
        assert r.params["scope"] == "partial"
        assert r.params["rejected_task_ids"] == ["dev_tc_001", "dev_tc_003"]

    def test_R11_return_partial_without_ids_returns_empty_list(self):
        r = self.sm.evaluate(
            "human_response_received", {"action": "return_partial"}
        )
        assert r.name == "return_to_dev"
        assert r.params["scope"] == "partial"
        assert r.params["rejected_task_ids"] == []

    def test_R11_unknown_action_errors(self):
        r = self.sm.evaluate("human_response_received", {"action": "ignore"})
        assert r.name == "error"
        assert r.params.get("reason") == "unknown_action"
        assert r.params.get("received") == "ignore"

    def test_R11_missing_action_errors(self):
        r = self.sm.evaluate("human_response_received", {})
        assert r.name == "error"
