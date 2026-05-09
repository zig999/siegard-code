"""Tests for on_stop.py — Task 3.7."""
import json
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).parents[2] / "dist" / ".claude" / "hooks"
SKILLS_DIR = Path(__file__).parents[2] / "dist" / ".claude" / "skills"
APPEND = str(SKILLS_DIR / "orch-log" / "scripts" / "append.py")
EMIT = str(SKILLS_DIR / "orch-report" / "scripts" / "emit.py")
HOOK = str(HOOKS_DIR / "on_stop.py")


def _append(cwd, agent, event_type, task_id=None, data=None, attempt=1, env=None):
    cmd = [
        sys.executable, APPEND,
        "--agent", agent,
        "--event-type", event_type,
        "--attempt", str(attempt),
        "--data", json.dumps(data or {}),
    ]
    if task_id:
        cmd += ["--task-id", task_id]
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _emit(cwd, worker_id, kind, task_id, attempt=1, data=None):
    env = {"ORCH_WORKER_ID": worker_id, "PATH": "/usr/bin:/bin"}
    r = subprocess.run(
        [sys.executable, EMIT, "--kind", kind, "--task-id", task_id,
         "--attempt", str(attempt), "--data", json.dumps(data or {})],
        cwd=str(cwd), capture_output=True, text=True, env=env
    )
    assert r.returncode == 0, r.stderr


def _run_hook(cwd):
    r = subprocess.run([sys.executable, HOOK], cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def _read_metrics(cwd):
    path = Path(cwd) / ".orch" / "metrics" / "current.json"
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------

def test_empty_log_no_output(tmp_path):
    """Hook is no-op when log doesn't exist yet."""
    _run_hook(tmp_path)
    assert not (tmp_path / ".orch" / "metrics" / "current.json").exists()


def test_metrics_written_after_workflow(tmp_path):
    """Metrics file is created with correct counts after a completed workflow."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_test", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_001",
            data={"phase": "default", "worker_type": "test-worker", "worker_id": "w1"})
    _emit(tmp_path, "w1", "completed", "t_001",
          data={"phase": "default", "artifacts": [], "summary": "done"})

    _run_hook(tmp_path)
    m = _read_metrics(tmp_path)

    assert m["workflow_id"] == "wf_test"
    assert m["tasks_total"] == 1
    assert m["tasks_completed"] == 1
    assert m["tasks_failed"] == 0
    assert m["tasks_dlq"] == 0
    assert m["run_status"] == "completed"
    assert m["last_seq"] > 0


def test_metrics_with_dlq(tmp_path):
    """Metrics reflect DLQ tasks correctly."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_dlq", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_001",
            data={"phase": "default", "worker_type": "test-worker", "worker_id": "w1"})
    _emit(tmp_path, "w1", "failed", "t_001",
          data={"phase": "default", "reason": "validation_failed", "retryable": False})
    _append(tmp_path, "orchestrator", "task_dlq", "t_001",
            data={"phase": "default", "reason": "non_retryable", "last_error": "spec_unclear"})

    _run_hook(tmp_path)
    m = _read_metrics(tmp_path)

    assert m["tasks_dlq"] == 1
    assert m["tasks_completed"] == 0
    assert m["run_status"] in ("completed_with_dlq",)


def test_metrics_keys_present(tmp_path):
    """All required metric keys are present in output."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_keys", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})

    _run_hook(tmp_path)
    m = _read_metrics(tmp_path)

    required_keys = [
        "generated_at", "workflow_id", "run_status", "current_phase",
        "last_seq", "tasks_total", "tasks_by_status",
        "tasks_completed", "tasks_failed", "tasks_dlq",
        "phases_completed", "phase_durations", "escalations",
        "circuit_breaker_tripped",
    ]
    for key in required_keys:
        assert key in m, f"Missing key: {key}"


def test_hook_survives_corrupt_env(tmp_path):
    """Hook never raises even with a broken ORCH_DIR (graceful no-op)."""
    # Run from a tmp_path with no log — should just exit 0
    r = subprocess.run(
        [sys.executable, HOOK], cwd=str(tmp_path), capture_output=True, text=True
    )
    assert r.returncode == 0


def test_metrics_overwritten_on_second_run(tmp_path):
    """Second run of hook overwrites first metrics file."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_overwrite", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})

    _run_hook(tmp_path)
    m1 = _read_metrics(tmp_path)

    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _run_hook(tmp_path)
    m2 = _read_metrics(tmp_path)

    assert m2["tasks_total"] == 1
    assert m2["tasks_total"] != m1["tasks_total"]


def test_empty_workflow_run_status(tmp_path):
    """Workflow with no tasks has run_status=empty."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_empty", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})

    _run_hook(tmp_path)
    m = _read_metrics(tmp_path)
    assert m["run_status"] == "empty"
    assert m["tasks_total"] == 0


# ---------------------------------------------------------------------------
# last_error.json (suggestion 3c)
# ---------------------------------------------------------------------------

def _read_last_error(cwd):
    path = Path(cwd) / ".orch" / "last_error.json"
    return json.loads(path.read_text())


def test_last_error_written_on_dlq(tmp_path):
    """last_error.json is created when run_status is completed_with_dlq."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_err_dlq", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_001",
            data={"phase": "default", "worker_type": "w", "worker_id": "w1"})
    _emit(tmp_path, "w1", "failed", "t_001",
          data={"phase": "default", "reason": "validation_failed", "retryable": False})
    _append(tmp_path, "orchestrator", "task_dlq", "t_001",
            data={"phase": "default", "reason": "non_retryable", "last_error": "spec_error"})

    _run_hook(tmp_path)

    assert (tmp_path / ".orch" / "last_error.json").exists()
    err = _read_last_error(tmp_path)
    assert err["run_status"] == "completed_with_dlq"
    assert err["workflow_id"] == "wf_err_dlq"
    assert "last_error_event" in err
    assert err["last_error_event"]["event_type"] in (
        "task_failed", "task_dlq", "escalation", "circuit_breaker_tripped", "preflight_failed"
    )


def test_last_error_written_on_escalation(tmp_path):
    """last_error.json is created when an escalation is active."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_esc", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    # A task is needed so run_status is derived from tasks (not short-circuited as "empty")
    _append(tmp_path, "orchestrator", "task_created", "t_esc",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_esc",
            data={"phase": "default", "worker_type": "w", "worker_id": "w_esc"})
    _emit(tmp_path, "w_esc", "failed", "t_esc",
          data={"phase": "default", "reason": "internal_error", "retryable": False})
    _append(tmp_path, "orchestrator", "task_dlq", "t_esc",
            data={"phase": "default", "reason": "non_retryable", "last_error": "critical_error"})
    _append(tmp_path, "orchestrator", "escalation",
            data={"code": "E04_critical_task_dlq", "severity": "critical",
                  "reason": "task failed", "evidence": [], "suggested_actions": []})

    _run_hook(tmp_path)

    assert (tmp_path / ".orch" / "last_error.json").exists()
    err = _read_last_error(tmp_path)
    assert err["run_status"] == "escalated"
    assert err["last_error_event"]["event_type"] == "escalation"


def test_last_error_not_written_on_clean_completion(tmp_path):
    """last_error.json is NOT created when the workflow completes cleanly."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_clean", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_001",
            data={"phase": "default", "worker_type": "w", "worker_id": "w1"})
    _emit(tmp_path, "w1", "completed", "t_001",
          data={"phase": "default", "artifacts": [], "summary": "ok"})

    _run_hook(tmp_path)

    assert not (tmp_path / ".orch" / "last_error.json").exists()


def test_last_error_contains_required_keys(tmp_path):
    """last_error.json has all required top-level keys."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_keys_err", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "orchestrator", "task_created", "t_002",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_002",
            data={"phase": "default", "worker_type": "w", "worker_id": "w2"})
    _emit(tmp_path, "w2", "failed", "t_002",
          data={"phase": "default", "reason": "stale_timeout", "retryable": False})
    _append(tmp_path, "orchestrator", "task_dlq", "t_002",
            data={"phase": "default", "reason": "non_retryable", "last_error": "timeout"})

    _run_hook(tmp_path)

    err = _read_last_error(tmp_path)
    for key in ("generated_at", "workflow_id", "run_status", "last_seq", "last_error_event"):
        assert key in err, f"Missing key in last_error.json: {key}"
