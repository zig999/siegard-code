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


def _worker_exited(task_id, chars=None):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": []})
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "dev", "worker_type": "impl", "worker_id": "w"})
    data = {"phase": "dev", "reason": "worker_exited_without_terminal", "retryable": True}
    if chars is not None:
        data["spawn_context_chars"] = chars
    append_event("worker", "task_failed", task_id=task_id, attempt=1, data=data)


def _stale_reaped_then_completed(task_id):
    """A worker reaped as stale (task_failed reason=stale_timeout) whose live straggler
    then completes the SAME attempt → FAILED→completed. Since F2 (SIEGARD) this is a
    RECONCILED false positive, not a violation: the reaper's terminal was synthesized,
    the worker was alive, so strict reduce_all accepts FAILED→COMPLETED and records an
    anomaly (no illegal transition)."""
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": []})
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "dev", "worker_type": "impl", "worker_id": "w"})
    append_event("stale-monitor", "task_failed", task_id=task_id, attempt=1, data={
        "phase": "dev", "reason": "stale_timeout", "retryable": True})
    append_event("worker", "task_completed", task_id=task_id, attempt=1, data={
        "phase": "dev", "artifacts": []})


def _completed_without_claim(task_id):
    """A task_completed emitted for a READY task that was never claimed → a genuine
    illegal transition (not a synthesized-failure false positive). Strict reduce_all
    raises IllegalTransition; tolerant reduction records it as a violation and keeps
    going. Replaces the stale-reaped case, which F2 now reconciles legally."""
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": []})
    append_event("worker", "task_completed", task_id=task_id, attempt=1, data={
        "phase": "dev", "artifacts": []})


class TestClassifyRunStatus:
    def test_no_escalation_is_no_pending(self, tmp_orch):
        _phase()
        result = _run(tmp_orch)
        assert result["status"] == "ok"
        assert result["run_status"] == "no_pending_escalation"
        assert result["dlq"]["total"] == 0

    def test_clean_log_has_no_reduce_violations(self, tmp_orch):
        _phase()
        result = _run(tmp_orch)
        assert result["reduce_violations"] == []

    def test_illegal_transition_does_not_crash_and_is_surfaced(self, tmp_orch):
        # Strict reduce_all would abort with internal_error here; tolerant reduction
        # keeps the report readable and lists the skipped transition.
        _phase()
        _completed_without_claim("dev_tc_001")
        result = _run(tmp_orch)
        assert result["status"] == "ok"
        assert len(result["reduce_violations"]) == 1
        v = result["reduce_violations"][0]
        assert v["task_id"] == "dev_tc_001"
        assert v["event_type"] == "task_completed"
        assert "skipped during tolerant reduction" in result["summary"]

    def test_stale_reaped_completion_reconciles_without_violation(self, tmp_orch):
        # F2 (SIEGARD): a stale-reaped worker that actually finished is reconciled
        # (FAILED->COMPLETED) by strict reduce_all — no illegal transition, so the
        # tolerant classifier reports zero violations and the task reads as completed.
        _phase()
        _stale_reaped_then_completed("dev_tc_001")
        result = _run(tmp_orch)
        assert result["status"] == "ok"
        assert result["reduce_violations"] == []

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

    def test_worker_exited_context_empty(self, tmp_orch):
        _phase()
        wec = _run(tmp_orch)["worker_exited_context"]
        assert wec["total"] == 0
        assert wec["with_context_chars"] == 0
        assert wec["median_chars"] is None

    def test_worker_exited_context_bands(self, tmp_orch):
        _phase()
        _worker_exited("t1", chars=30_000)    # <50k
        _worker_exited("t2", chars=80_000)    # 50-100k
        _worker_exited("t3", chars=120_000)   # 100-150k
        _worker_exited("t4", chars=200_000)   # >150k (context-implicated)
        _worker_exited("t5", chars=None)      # unrecorded
        wec = _run(tmp_orch)["worker_exited_context"]
        assert wec["total"] == 5
        assert wec["with_context_chars"] == 4
        assert wec["by_band"] == {"<50k": 1, "50-100k": 1, "100-150k": 1, ">150k": 1, "unrecorded": 1}
        assert wec["context_implicated"] == 1
        assert wec["median_chars"] in (80_000, 120_000)  # median of 4 recorded

    def test_worker_exited_unrecorded_is_dominant_on_legacy(self, tmp_orch):
        # Legacy/un-instrumented runs: chars never populated → all unrecorded.
        _phase()
        for i in range(3):
            _worker_exited(f"t{i}", chars=None)
        wec = _run(tmp_orch)["worker_exited_context"]
        assert wec["by_band"]["unrecorded"] == 3
        assert wec["with_context_chars"] == 0
        assert wec["context_implicated"] == 0

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


# ------------------------------------------------ --project-dir binding (M1)

class TestProjectDirBinding:
    """--project-dir was silently ignored (2026-07-15 post-fix audit, M1):
    ORCH_DIR/LOG_PATH bind when orch_core is imported, but the env var was set
    inside evaluate() — after the import. The CLI always read ./.orch of the
    CWD and reported a confident healthy verdict for the wrong (possibly
    missing) log. Now the flag is resolved BEFORE the import, and a missing
    log is an explicit log_missing error instead of an empty-log 'healthy'."""

    def _run_cli(self, project_dir, cwd):
        import subprocess, sys as _sys
        script = Path(__file__).resolve().parents[2] / "dist" / ".claude" / "scripts" / "classify_run_status.py"
        return subprocess.run(
            [_sys.executable, str(script), "--project-dir", str(project_dir)],
            capture_output=True, text=True, cwd=str(cwd),
            env={k: v for k, v in __import__("os").environ.items()
                 if k != "ORCH_PROJECT_DIR"},
        )

    def test_missing_log_reports_log_missing_not_healthy(self, tmp_path):
        empty_project = tmp_path / "no-orch-here"
        empty_project.mkdir()
        r = self._run_cli(empty_project, cwd=tmp_path)
        assert r.returncode == 1
        err = json.loads(r.stderr.strip())
        assert err["reason"] == "log_missing"

    def test_project_dir_flag_reads_the_target_log(self, tmp_path):
        # Build a minimal log in the TARGET project via a SUBPROCESS (append.py):
        # reloading orch_core in-process would swap the module object the whole
        # suite (conftest path-restore included) holds references to.
        import os, subprocess, sys as _sys
        target = tmp_path / "target-project"
        (target / ".orch").mkdir(parents=True)
        append_py = (Path(__file__).resolve().parents[2] / "dist" / ".claude"
                     / "skills" / "orch-log" / "scripts" / "append.py")
        env = {k: v for k, v in os.environ.items() if k != "ORCH_PROJECT_DIR"}
        env["ORCH_PROJECT_DIR"] = str(target)
        r0 = subprocess.run(
            [_sys.executable, str(append_py), "--agent", "x",
             "--event-type", "escalation",
             "--data", json.dumps({"code": "E99_human_approval_required",
                                    "severity": "critical", "reason": "r",
                                    "evidence": [], "suggested_actions": []})],
            capture_output=True, text=True, cwd=str(target), env=env)
        assert r0.returncode == 0, r0.stderr or r0.stdout
        # CLI run from an UNRELATED cwd must still see the escalation:
        r = self._run_cli(target, cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip())
        assert out["run_status"] == "awaiting_human"
