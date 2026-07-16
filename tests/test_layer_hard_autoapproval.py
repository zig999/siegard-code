"""Layer Hard Auto-approval — bind auto-approval to the Python qualifies verdict (task 02).

check_micro_unanimous_clean.py must exit 0 ONLY when qualifies is true (exit 2 when
disqualified, 1 on bad input), so the review orchestrator can gate the synthesized
human approval on the script's exit code rather than on LLM-retyped booleans.

Findings: C2 / A4-F2, A1-F2.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "dist/.claude/skills/phase-review-rules/scripts/check_micro_unanimous_clean.py"
sys.path.insert(0, str(ROOT / "dist/.claude/lib"))


def _run(tasks, project_dir):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-dir", str(project_dir), "--tasks", json.dumps(tasks)],
        capture_output=True, text=True,
    )


def _verdict(tmp_path, verdict="approved", severity=None):
    d = tmp_path / "qa"
    d.mkdir(exist_ok=True)
    f = d / "v.yaml"
    body = f"verdict: {verdict}\n"
    if severity:
        body += f"findings:\n  - severity: {severity}\n"
    f.write_text(body)
    return "qa/v.yaml"


class TestAutoApprovalExitCode:
    def test_exit_zero_only_when_qualifies(self, tmp_path):
        vp = _verdict(tmp_path, "approved", None)
        p = _run([{"task_id": "t1", "qa_mode": "micro", "verdict_path": vp}], tmp_path)
        assert p.returncode == 0
        assert json.loads(p.stdout)["qualifies"] is True

    def test_exit_nonzero_on_severe_finding(self, tmp_path):
        vp = _verdict(tmp_path, "approved", "high")
        p = _run([{"task_id": "t1", "qa_mode": "micro", "verdict_path": vp}], tmp_path)
        assert p.returncode != 0
        assert json.loads(p.stdout)["qualifies"] is False

    def test_exit_nonzero_on_non_micro(self, tmp_path):
        vp = _verdict(tmp_path, "approved", None)
        p = _run([{"task_id": "t1", "qa_mode": "standard", "verdict_path": vp}], tmp_path)
        assert p.returncode != 0

    def test_exit_nonzero_on_rejected(self, tmp_path):
        vp = _verdict(tmp_path, "rejected", None)
        p = _run([{"task_id": "t1", "qa_mode": "micro", "verdict_path": vp}], tmp_path)
        assert p.returncode != 0

    def test_bad_input_exit_1(self, tmp_path):
        p = subprocess.run([sys.executable, str(SCRIPT), "--tasks", "not-json"],
                           capture_output=True, text=True)
        assert p.returncode == 1

    def test_empty_tasks_disqualifies_nonzero(self, tmp_path):
        p = _run([], tmp_path)
        assert p.returncode != 0
        assert json.loads(p.stdout)["qualifies"] is False


class TestReviewSMQualifies:
    def _sm(self):
        from orch_core import ReviewStateMachine, REVIEW_TRANSITIONS
        return ReviewStateMachine(REVIEW_TRANSITIONS)

    def test_qualifies_false_forces_manual_gate(self):
        # Passing the script's qualifies=False short-circuits to the manual gate,
        # even if the (LLM-supplied) evidence booleans look clean.
        r = self._sm().evaluate("approval_gate", {
            "qualifies": False, "completed_review_tasks_count": 1,
            "all_qa_mode_micro": True, "all_verdicts_approved": True, "any_severe_findings": False,
        })
        assert r.name == "manual_gate"
        assert r.params.get("disqualified_by") == "script_qualifies_false"

    def test_existing_boolean_path_still_auto_approves(self):
        # Backward compatible: no qualifies key -> R1-R4 defense-in-depth still applies.
        r = self._sm().evaluate("approval_gate", {
            "completed_review_tasks_count": 1, "all_qa_mode_micro": True,
            "all_verdicts_approved": True, "any_severe_findings": False,
        })
        assert r.name == "auto_approve"

    def test_qualifies_true_with_clean_booleans_auto_approves(self):
        r = self._sm().evaluate("approval_gate", {
            "qualifies": True, "completed_review_tasks_count": 1, "all_qa_mode_micro": True,
            "all_verdicts_approved": True, "any_severe_findings": False,
        })
        assert r.name == "auto_approve"


class TestE18SynthesizedResponseContract:
    """E18 auto-approval payload contract (2026-07-15 post-fix audit, 5.1).

    The synthesized human_response documented in orchestrator-review.md MUST carry
    escalation_seq — it is a REQUIRED field of human_response, so the payload the
    prompt previously prescribed was rejected by _validate_event_data at append
    time: the 'skip the human gate' feature deterministically degraded into a
    manual gate plus a mid-flow error. These tests pin (a) the documented payload
    template and (b) the functional round-trip: E18 -> synthesized response ->
    escalation resolved, run_status back to active.
    """

    REVIEW_MD = ROOT / "dist/.claude/agents/orchestrator-review.md"

    def _auto_approve_block(self):
        text = self.REVIEW_MD.read_text(encoding="utf-8")
        start = text.index('If `$ACTION == "auto_approve"`')
        end = text.index("Skip the E99 escalation", start)
        return text[start:end]

    def test_documented_payload_template_carries_escalation_seq(self):
        block = self._auto_approve_block()
        response_payloads = [
            line for line in block.splitlines()
            if "human_response" not in line and '"auto_approved":true' in line
        ]
        assert response_payloads, "synthesized human_response payload not found in auto-approve block"
        for payload in response_payloads:
            assert '"escalation_seq"' in payload, (
                "orchestrator-review.md auto-approve human_response payload lost the "
                "required escalation_seq field (append would fail validation and the "
                "auto-approval silently degrades into a manual gate)"
            )

    def test_synthesized_response_without_escalation_seq_is_rejected(self, orch_dir):
        """Enshrines WHY the field is load-bearing: the pre-fix payload fails append."""
        import orch_core
        import pytest
        with pytest.raises(orch_core.EventValidationError):
            orch_core.append_event(
                agent="orchestrator-review", event_type="human_response",
                data={"action": "approve", "auto_approved": True,
                      "reason": "micro_unanimous_clean",
                      "synthesized_by": "orchestrator-review", "phase": "review"})

    def test_e18_then_synthesized_response_resolves_escalation(self, orch_dir):
        """Functional round-trip of the documented sequence: the E18 escalation
        sets run_status=escalated; the synthesized response citing its seq
        resolves it in the same invocation — no human required."""
        import orch_core
        e18 = orch_core.append_event(
            agent="orchestrator-review", event_type="escalation",
            data={"code": "E18_auto_approval_granted", "severity": "info",
                  "reason": "strict gate met", "evidence": [],
                  "options": ["override_via_human_response: action=return_to_dev"],
                  "suggested_actions": []})
        assert orch_core.reduce_all().run_status == "escalated"
        orch_core.append_event(
            agent="orchestrator-review", event_type="human_response",
            data={"escalation_seq": e18.seq, "action": "approve",
                  "auto_approved": True, "reason": "micro_unanimous_clean",
                  "synthesized_by": "orchestrator-review", "phase": "review"})
        state = orch_core.reduce_all()
        assert state.run_status == "active"
        assert state.escalation is None
