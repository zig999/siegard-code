"""Layer Hard Transition — phase_transitioned hard-block precondition (task 01).

Enforces in Python (not prompt): a forward phase transition requires a
phase_exit_approved for from_phase; leaving review forward (review->test)
additionally requires a human_response action=approve (or an E18 auto-approval).
Return-to-dev loop-backs (review->dev, test->dev) are exempt (rejection paths).

Findings: C1 / A4-F1 (transition not hard-blocked), A1-F1 (human gate prompt-only),
A3-F8 (evidence_seq unchecked).
"""
import sys
from pathlib import Path

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
sys.path.insert(0, str(DIST_LIB))

WF = "wf-hard-01"


def _declare(mk, phases):
    mk("phase_declared", data={"workflow_id": WF, "phases": phases})


class TestTransitionGate:
    def test_forward_transition_blocked_without_exit_approved(self, orch_dir, make_event):
        import orch_core
        _declare(make_event, [
            {"name": "dev", "order": 2, "required": True},
            {"name": "review", "order": 3, "required": True},
        ])
        make_event("phase_entered", data={"phase": "dev", "order": 2, "workflow_id": WF})
        try:
            make_event("phase_transitioned", data={
                "from_phase": "dev", "to_phase": "review", "evidence_seq": 1, "workflow_id": WF})
            assert False, "expected PreconditionViolation (no phase_exit_approved)"
        except orch_core.PreconditionViolation as exc:
            assert "phase_exit_approved" in str(exc)

    def test_forward_transition_allowed_with_exit_approved(self, orch_dir, make_event):
        import orch_core
        _declare(make_event, [
            {"name": "dev", "order": 2, "required": True},
            {"name": "review", "order": 3, "required": True},
        ])
        make_event("phase_entered", data={"phase": "dev", "order": 2, "workflow_id": WF})
        appr = make_event("phase_exit_approved", data={
            "phase": "dev", "criteria_met": ["c1"], "next_phase": "review", "workflow_id": WF})
        ev = make_event("phase_transitioned", data={
            "from_phase": "dev", "to_phase": "review", "evidence_seq": appr.seq, "workflow_id": WF})
        assert ev.event_type == "phase_transitioned"

    def test_review_to_test_blocked_without_human_approval(self, orch_dir, make_event):
        import orch_core
        _declare(make_event, [
            {"name": "review", "order": 3, "required": True},
            {"name": "test", "order": 4, "required": True},
        ])
        make_event("phase_entered", data={"phase": "review", "order": 3, "workflow_id": WF})
        make_event("phase_exit_approved", data={
            "phase": "review", "criteria_met": ["all_qa_verdicts_approved"],
            "next_phase": "test", "workflow_id": WF})
        try:
            make_event("phase_transitioned", data={
                "from_phase": "review", "to_phase": "test", "evidence_seq": 1, "workflow_id": WF})
            assert False, "expected PreconditionViolation (no human approval)"
        except orch_core.PreconditionViolation as exc:
            assert "human" in str(exc).lower()

    def test_review_to_test_allowed_with_human_response(self, orch_dir, make_event):
        import orch_core
        _declare(make_event, [
            {"name": "review", "order": 3, "required": True},
            {"name": "test", "order": 4, "required": True},
        ])
        make_event("phase_entered", data={"phase": "review", "order": 3, "workflow_id": WF})
        esc = make_event("escalation", data={
            "code": "E99_human_approval_required", "severity": "info",
            "reason": "approve?", "evidence": [2]})
        make_event("human_response", agent="operator", data={
            "escalation_seq": esc.seq, "action": "approve", "operator": "alice"})
        make_event("phase_exit_approved", data={
            "phase": "review", "criteria_met": ["all_qa_verdicts_approved"],
            "next_phase": "test", "workflow_id": WF})
        ev = make_event("phase_transitioned", data={
            "from_phase": "review", "to_phase": "test", "evidence_seq": esc.seq, "workflow_id": WF})
        assert ev.event_type == "phase_transitioned"

    def test_review_to_test_allowed_with_e18_autoapproval(self, orch_dir, make_event):
        import orch_core
        _declare(make_event, [
            {"name": "review", "order": 3, "required": True},
            {"name": "test", "order": 4, "required": True},
        ])
        make_event("phase_entered", data={"phase": "review", "order": 3, "workflow_id": WF})
        make_event("escalation", data={
            "code": "E18_auto_approval_granted", "severity": "info",
            "reason": "micro_unanimous_clean", "evidence": [2]})
        make_event("phase_exit_approved", data={
            "phase": "review", "criteria_met": ["x"], "next_phase": "test", "workflow_id": WF})
        ev = make_event("phase_transitioned", data={
            "from_phase": "review", "to_phase": "test", "evidence_seq": 2, "workflow_id": WF})
        assert ev.event_type == "phase_transitioned"

    def test_return_to_dev_exempt(self, orch_dir, make_event):
        # review -> dev (rejection loop-back) needs no exit_approved and no human gate
        import orch_core
        _declare(make_event, [
            {"name": "dev", "order": 2, "required": True},
            {"name": "review", "order": 3, "required": True},
        ])
        make_event("phase_entered", data={"phase": "review", "order": 3, "workflow_id": WF})
        ev = make_event("phase_transitioned", data={
            "from_phase": "review", "to_phase": "dev", "evidence_seq": 1, "workflow_id": WF})
        assert ev.event_type == "phase_transitioned"

    def test_evidence_seq_must_reference_prior_event(self, orch_dir, make_event):
        import orch_core
        _declare(make_event, [
            {"name": "dev", "order": 2, "required": True},
            {"name": "review", "order": 3, "required": True},
        ])
        make_event("phase_entered", data={"phase": "dev", "order": 2, "workflow_id": WF})
        make_event("phase_exit_approved", data={
            "phase": "dev", "criteria_met": ["c1"], "next_phase": "review", "workflow_id": WF})
        try:
            make_event("phase_transitioned", data={
                "from_phase": "dev", "to_phase": "review", "evidence_seq": 9999, "workflow_id": WF})
            assert False, "expected PreconditionViolation (evidence_seq invalid)"
        except orch_core.PreconditionViolation as exc:
            assert "evidence_seq" in str(exc)

    def test_precondition_installed_at_import(self, orch_dir):
        import orch_core
        assert "phase_transitioned" in orch_core._APPEND_PRECONDITIONS
