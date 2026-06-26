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
