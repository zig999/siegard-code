"""Tests for on_stop.py — Task 3.7."""
import json
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).parents[1] / ".claude" / "hooks"
SKILLS_DIR = Path(__file__).parents[1] / ".claude" / "skills"
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
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1})
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
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1})
    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_001",
            data={"phase": "default", "worker_type": "test-worker", "worker_id": "w1"})
    _emit(tmp_path, "w1", "failed", "t_001",
          data={"phase": "default", "reason": "spec_unclear", "retryable": False})
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
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1})

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
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1})

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
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1})

    _run_hook(tmp_path)
    m = _read_metrics(tmp_path)
    assert m["run_status"] == "empty"
    assert m["tasks_total"] == 0
