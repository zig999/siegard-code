"""Tests for orch-report/scripts/emit.py CLI (subprocess).

Covers:
  - All three valid kinds (progress, completed, failed)
  - Guard-rail: invalid kinds rejected before any event is written
  - Missing ORCH_WORKER_ID rejected
  - Invalid JSON data rejected
  - Agent is set from env var, not CLI arg
"""
import json
import subprocess
import sys
from pathlib import Path

EMIT_SCRIPT = (
    Path(__file__).parent.parent.parent / "dist" / ".claude" / "skills" / "orch-report" / "scripts" / "emit.py"
)
APPEND_SCRIPT = (
    Path(__file__).parent.parent.parent / "dist" / ".claude" / "skills" / "orch-log" / "scripts" / "append.py"
)
READ_SCRIPT = (
    Path(__file__).parent.parent.parent / "dist" / ".claude" / "skills" / "orch-log" / "scripts" / "read.py"
)


def _run(args: list[str], cwd: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os
    env = os.environ.copy()
    env.pop("ORCH_WORKER_ID", None)  # clean slate for each test
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(EMIT_SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


def _setup(tmp_path: Path) -> None:
    """Create log dir and emit phase_declared + phase_entered so tasks can be claimed."""
    (tmp_path / ".orch").mkdir(exist_ok=True)
    for script, extra_args in [
        (APPEND_SCRIPT, ["--agent", "orch", "--event-type", "phase_declared",
                          "--data", '{"workflow_id":"wf_1","phases":[{"name":"dev","order":1}]}']),
        (APPEND_SCRIPT, ["--agent", "orch", "--event-type", "phase_entered",
                          "--data", '{"phase":"dev","order":1,"workflow_id":"wf_1"}']),
        (APPEND_SCRIPT, ["--agent", "orch", "--event-type", "task_created",
                          "--task-id", "t_001",
                          "--data", '{"phase":"dev","tier":"standard","type":"impl","spec":"x","deps":[]}']),
    ]:
        r = subprocess.run([sys.executable, str(script)] + extra_args,
                           capture_output=True, text=True, cwd=str(tmp_path))
        assert r.returncode == 0, r.stderr


def _count_events(cwd: Path) -> int:
    r = subprocess.run([sys.executable, str(READ_SCRIPT)],
                       capture_output=True, text=True, cwd=str(cwd))
    return len([l for l in r.stdout.strip().splitlines() if l])


# ---------------------------------------------------------------------------
# Guard-rail: ORCH_WORKER_ID required
# ---------------------------------------------------------------------------

def test_missing_worker_id_exits_nonzero(tmp_path):
    _setup(tmp_path)
    r = _run(["--kind", "progress", "--task-id", "t_001",
              "--data", '{"phase":"dev","note":"working"}'], tmp_path)
    assert r.returncode != 0
    err = json.loads(r.stdout)
    assert err["status"] == "error"
    assert err["reason"] == "missing_env"


def test_missing_worker_id_writes_no_event(tmp_path):
    _setup(tmp_path)
    before = _count_events(tmp_path)
    _run(["--kind", "progress", "--task-id", "t_001",
          "--data", '{"phase":"dev","note":"working"}'], tmp_path)
    assert _count_events(tmp_path) == before


# ---------------------------------------------------------------------------
# Guard-rail: invalid kinds rejected
# ---------------------------------------------------------------------------

def test_invalid_kind_rejected(tmp_path):
    _setup(tmp_path)
    r = _run(["--kind", "task_claimed", "--task-id", "t_001"], tmp_path,
             env_extra={"ORCH_WORKER_ID": "w_1"})
    assert r.returncode != 0


def test_orchestrator_kind_rejected(tmp_path):
    _setup(tmp_path)
    for forbidden in ("escalation", "phase_declared", "snapshot", "claimed", "dlq"):
        r = _run(["--kind", forbidden, "--task-id", "t_001"], tmp_path,
                 env_extra={"ORCH_WORKER_ID": "w_1"})
        assert r.returncode != 0, f"kind={forbidden!r} should have been rejected"


def test_invalid_kind_writes_no_event(tmp_path):
    _setup(tmp_path)
    before = _count_events(tmp_path)
    _run(["--kind", "escalation", "--task-id", "t_001"], tmp_path,
         env_extra={"ORCH_WORKER_ID": "w_1"})
    assert _count_events(tmp_path) == before


# ---------------------------------------------------------------------------
# Valid kinds — happy path
# ---------------------------------------------------------------------------

def test_emit_progress(tmp_path):
    _setup(tmp_path)
    r = _run(
        ["--kind", "progress", "--task-id", "t_001",
         "--data", '{"phase":"dev","note":"running tests"}'],
        tmp_path,
        env_extra={"ORCH_WORKER_ID": "worker-42"},
    )
    assert r.returncode == 0, r.stderr + r.stdout
    event = json.loads(r.stdout)
    assert event["event_type"] == "task_progress"
    assert event["task_id"] == "t_001"
    assert event["agent"] == "worker-42"


def test_emit_completed(tmp_path):
    _setup(tmp_path)
    r = _run(
        ["--kind", "completed", "--task-id", "t_001",
         "--data", '{"phase":"dev","artifacts":["src/foo.py"],"summary":"done"}'],
        tmp_path,
        env_extra={"ORCH_WORKER_ID": "worker-42"},
    )
    assert r.returncode == 0, r.stderr + r.stdout
    event = json.loads(r.stdout)
    assert event["event_type"] == "task_completed"
    assert event["agent"] == "worker-42"


def test_emit_failed(tmp_path):
    _setup(tmp_path)
    r = _run(
        ["--kind", "failed", "--task-id", "t_001",
         "--data", '{"phase":"dev","reason":"validation_failed","retryable":true}'],
        tmp_path,
        env_extra={"ORCH_WORKER_ID": "worker-42"},
    )
    assert r.returncode == 0, r.stderr + r.stdout
    event = json.loads(r.stdout)
    assert event["event_type"] == "task_failed"
    assert event["agent"] == "worker-42"


def test_agent_set_from_env_not_arg(tmp_path):
    _setup(tmp_path)
    r = _run(
        ["--kind", "progress", "--task-id", "t_001",
         "--data", '{"phase":"dev","note":"test"}'],
        tmp_path,
        env_extra={"ORCH_WORKER_ID": "env-worker-id"},
    )
    assert r.returncode == 0
    event = json.loads(r.stdout)
    assert event["agent"] == "env-worker-id"


def test_emit_writes_event_to_log(tmp_path):
    _setup(tmp_path)
    before = _count_events(tmp_path)
    _run(
        ["--kind", "progress", "--task-id", "t_001",
         "--data", '{"phase":"dev","note":"check"}'],
        tmp_path,
        env_extra={"ORCH_WORKER_ID": "w_1"},
    )
    assert _count_events(tmp_path) == before + 1


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_invalid_json_data_rejected(tmp_path):
    _setup(tmp_path)
    r = _run(
        ["--kind", "progress", "--task-id", "t_001", "--data", "{bad}"],
        tmp_path,
        env_extra={"ORCH_WORKER_ID": "w_1"},
    )
    assert r.returncode != 0
    err = json.loads(r.stdout)
    assert err["status"] == "error"
    assert err["reason"] == "invalid_json"
