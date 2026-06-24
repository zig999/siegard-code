"""
Tests for scripts/classify_run_status.py (Rec B).

Builds a log fixture in-process (tmp_orch monkeypatches orch_core paths) and runs
the classifier as a subprocess against the same ORCH_PROJECT_DIR.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from orch_core import append_event

SCRIPT = Path(__file__).resolve().parents[2] / "dist" / ".claude" / "scripts" / "classify_run_status.py"


def _run(project_dir) -> dict:
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir)}
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--project-dir", str(project_dir)],
        capture_output=True, text=True, env=env, cwd=str(project_dir),
    )
    assert r.stdout, f"no stdout (stderr={r.stderr[:300]})"
    return json.loads(r.stdout)


def _phase(name="dev"):
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": "wf", "phases": [{"name": name, "order": 1, "required": True}]})
    append_event("orchestrator", "phase_entered", data={
        "phase": name, "order": 1, "workflow_id": "wf"})


def _escalation(code, severity, reason="x"):
    return append_event("orchestrator", "escalation", data={
        "code": code, "severity": severity, "reason": reason, "evidence": [],
        "suggested_actions": ["do thing"]})


def _root_dlq(task_id):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": []})
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "dev", "worker_type": "impl", "worker_id": "w"})
    append_event("worker", "task_failed", task_id=task_id, attempt=1, data={
        "phase": "dev", "reason": "internal_error", "retryable": False})
    append_event("orchestrator", "task_dlq", task_id=task_id, data={
        "phase": "dev", "reason": "non_retryable", "last_error": "exit 1"})


def _cascade_dlq(task_id, dep):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": [dep]})
    append_event("orchestrator", "task_dlq", task_id=task_id, data={
        "phase": "dev", "reason": "cascade_from_dep", "last_error": f"dep {dep} in dlq"})


class TestClassifyRunStatus:
    def test_no_escalation_is_no_pending(self, tmp_orch):
        _phase()
        result = _run(tmp_orch)
        assert result["status"] == "ok"
        assert result["run_status"] == "no_pending_escalation"
        assert result["dlq"]["total"] == 0

    def test_e99_gate_is_awaiting_human(self, tmp_orch):
        _phase()
        _escalation("E99_human_approval_required", "info")
        result = _run(tmp_orch)
        assert result["run_status"] == "awaiting_human"
        assert result["active_escalation"]["code"] == "E99_human_approval_required"

    def test_e99_test_intervention_warning_is_still_awaiting_human(self, tmp_orch):
        # E99 wins over severity — a human gate is not a failure even at warning severity.
        _phase()
        _escalation("E99_human_test_intervention_required", "warning")
        result = _run(tmp_orch)
        assert result["run_status"] == "awaiting_human"

    def test_resolved_e99_is_no_longer_active(self, tmp_orch):
        _phase()
        esc = _escalation("E99_human_approval_required", "info")
        append_event("operator", "human_response", data={
            "escalation_seq": esc.seq, "action": "approve", "operator": "me"})
        result = _run(tmp_orch)
        assert result["run_status"] == "no_pending_escalation"
        assert result["active_escalation"] is None

    def test_critical_escalation_is_failed(self, tmp_orch):
        _phase()
        _escalation("E04_critical_task_dlq", "critical", reason="impl task failed non-retryably")
        result = _run(tmp_orch)
        assert result["run_status"] == "failed"
        assert "E04" in result["summary"]

    def test_warning_escalation_is_needs_review(self, tmp_orch):
        _phase()
        _escalation("E08_exit_criteria_not_met", "warning")
        result = _run(tmp_orch)
        assert result["run_status"] == "needs_review"

    def test_dlq_roots_vs_cascade_split(self, tmp_orch):
        _phase()
        _root_dlq("dev_tc_001")
        _cascade_dlq("dev_tc_002", "dev_tc_001")
        _cascade_dlq("dev_tc_003", "dev_tc_001")
        result = _run(tmp_orch)
        dlq = result["dlq"]
        assert dlq["total"] == 3
        assert [r["task_id"] for r in dlq["roots"]] == ["dev_tc_001"]
        assert {c["task_id"] for c in dlq["cascaded"]} == {"dev_tc_002", "dev_tc_003"}
        assert dlq["by_reason"]["cascade_from_dep"] == 2
        assert dlq["by_reason"]["non_retryable"] == 1

    def test_last_unresolved_escalation_wins(self, tmp_orch):
        # An earlier resolved E99 then a later critical failure → failed.
        _phase()
        esc = _escalation("E99_human_approval_required", "info")
        append_event("operator", "human_response", data={
            "escalation_seq": esc.seq, "action": "approve", "operator": "me"})
        _escalation("E07_planning_failed", "critical")
        result = _run(tmp_orch)
        assert result["run_status"] == "failed"
        assert result["active_escalation"]["code"] == "E07_planning_failed"
