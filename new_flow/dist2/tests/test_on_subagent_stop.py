"""Tests for .claude/hooks/on_subagent_stop.py (scenarios 7.1, 7.2, 7.3)."""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / ".claude" / "hooks" / "on_subagent_stop.py"
APPEND = Path(__file__).parent.parent / ".claude" / "skills" / "orch-log" / "scripts" / "append.py"
READ = Path(__file__).parent.parent / ".claude" / "skills" / "orch-log" / "scripts" / "read.py"


def _run_hook(cwd: Path, env_extra: dict | None = None, stdin: str = "") -> subprocess.CompletedProcess:
    env = os.environ.copy()
    for k in ("ORCH_TASK_ID", "ORCH_ATTEMPT", "ORCH_WORKER_ID"):
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


def _append(cwd: Path, event_type: str, task_id: str | None = None,
            data: dict | None = None, attempt: int = 1) -> dict:
    args = ["--agent", "orch", "--event-type", event_type]
    if task_id:
        args += ["--task-id", task_id]
    if data:
        args += ["--data", json.dumps(data)]
    if attempt != 1:
        args += ["--attempt", str(attempt)]
    r = subprocess.run([sys.executable, str(APPEND)] + args,
                       capture_output=True, text=True, cwd=str(cwd))
    assert r.returncode == 0, r.stderr + r.stdout
    return json.loads(r.stdout)


def _read_all(cwd: Path) -> list[dict]:
    r = subprocess.run([sys.executable, str(READ)],
                       capture_output=True, text=True, cwd=str(cwd))
    return [json.loads(l) for l in r.stdout.strip().splitlines() if l]


def _setup(tmp_path: Path) -> None:
    (tmp_path / ".orch").mkdir(exist_ok=True)
    _append(tmp_path, "phase_declared",
            data={"workflow_id": "wf_1",
                  "phases": [{"name": "dev", "order": 1, "required": True}]})
    _append(tmp_path, "phase_entered", data={"phase": "dev", "order": 1})
    _append(tmp_path, "task_created", task_id="t_001",
            data={"phase": "dev", "tier": "standard",
                  "type": "impl", "spec": "do X", "deps": []})
    _append(tmp_path, "task_claimed", task_id="t_001",
            data={"phase": "dev", "worker_type": "code-writer", "worker_id": "w_1"})


# ---------------------------------------------------------------------------
# [CRIT] 7.1 — Hook synthesizes task_failed when worker stops silently
# ---------------------------------------------------------------------------

def test_hook_synthesizes_failed_when_no_terminal(tmp_path):
    _setup(tmp_path)
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path, env_extra={
        "ORCH_TASK_ID": "t_001",
        "ORCH_ATTEMPT": "1",
        "ORCH_WORKER_ID": "w_1",
    })
    assert r.returncode == 0, r.stderr

    events = _read_all(tmp_path)
    assert len(events) == before + 1
    last = events[-1]
    assert last["event_type"] == "task_failed"
    assert last["task_id"] == "t_001"
    assert last["attempt"] == 1
    assert last["agent"] == "w_1"


def test_synthesized_failed_is_retryable(tmp_path):
    _setup(tmp_path)
    _run_hook(tmp_path, env_extra={
        "ORCH_TASK_ID": "t_001",
        "ORCH_ATTEMPT": "1",
        "ORCH_WORKER_ID": "w_1",
    })
    events = _read_all(tmp_path)
    last = events[-1]
    assert last["event_type"] == "task_failed"
    assert last["data"]["retryable"] is True
    assert last["data"]["reason"] == "worker_stopped_without_terminal_event"


def test_synthesized_failed_has_correct_phase(tmp_path):
    _setup(tmp_path)
    _run_hook(tmp_path, env_extra={
        "ORCH_TASK_ID": "t_001",
        "ORCH_ATTEMPT": "1",
        "ORCH_WORKER_ID": "w_1",
    })
    events = _read_all(tmp_path)
    last = events[-1]
    assert last["data"]["phase"] == "dev"


# ---------------------------------------------------------------------------
# [HAPPY] 7.2 — Hook is no-op when env vars are absent
# ---------------------------------------------------------------------------

def test_noop_when_no_env_vars(tmp_path):
    _setup(tmp_path)
    before = len(_read_all(tmp_path))
    r = _run_hook(tmp_path)  # no env_extra
    assert r.returncode == 0
    assert len(_read_all(tmp_path)) == before


def test_noop_when_partial_env_vars(tmp_path):
    _setup(tmp_path)
    before = len(_read_all(tmp_path))
    for partial in [
        {"ORCH_TASK_ID": "t_001"},
        {"ORCH_ATTEMPT": "1"},
        {"ORCH_WORKER_ID": "w_1"},
        {"ORCH_TASK_ID": "t_001", "ORCH_ATTEMPT": "1"},
    ]:
        _run_hook(tmp_path, env_extra=partial)
        assert len(_read_all(tmp_path)) == before, f"wrote event with partial env: {partial}"


# ---------------------------------------------------------------------------
# [HAPPY] 7.3 — Hook is no-op if worker already emitted terminal
# ---------------------------------------------------------------------------

def test_noop_when_completed_already_emitted(tmp_path):
    _setup(tmp_path)
    _append(tmp_path, "task_completed", task_id="t_001",
            data={"phase": "dev", "artifacts": [], "summary": "done"})
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path, env_extra={
        "ORCH_TASK_ID": "t_001",
        "ORCH_ATTEMPT": "1",
        "ORCH_WORKER_ID": "w_1",
    })
    assert r.returncode == 0
    assert len(_read_all(tmp_path)) == before


def test_noop_when_failed_already_emitted(tmp_path):
    _setup(tmp_path)
    _append(tmp_path, "task_failed", task_id="t_001",
            data={"phase": "dev", "reason": "impl_error", "retryable": True})
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path, env_extra={
        "ORCH_TASK_ID": "t_001",
        "ORCH_ATTEMPT": "1",
        "ORCH_WORKER_ID": "w_1",
    })
    assert r.returncode == 0
    assert len(_read_all(tmp_path)) == before


def test_noop_when_different_attempt_has_terminal(tmp_path):
    """Terminal for attempt=2 should not suppress synthesis for attempt=1."""
    _setup(tmp_path)
    # attempt=2 has a terminal, attempt=1 does not
    _append(tmp_path, "task_failed", task_id="t_001", attempt=2,
            data={"phase": "dev", "reason": "err", "retryable": True})
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path, env_extra={
        "ORCH_TASK_ID": "t_001",
        "ORCH_ATTEMPT": "1",
        "ORCH_WORKER_ID": "w_1",
    })
    assert r.returncode == 0
    events = _read_all(tmp_path)
    # a new task_failed for attempt=1 should have been synthesized
    assert len(events) == before + 1
    assert events[-1]["attempt"] == 1


# ---------------------------------------------------------------------------
# Edge: hook accepts and ignores stdin JSON (as Claude Code would send)
# ---------------------------------------------------------------------------

def test_hook_ignores_stdin(tmp_path):
    _setup(tmp_path)
    stdin_payload = json.dumps({"stop_hook_active": True, "session_id": "abc"})
    r = _run_hook(tmp_path, env_extra={
        "ORCH_TASK_ID": "t_001",
        "ORCH_ATTEMPT": "1",
        "ORCH_WORKER_ID": "w_1",
    }, stdin=stdin_payload)
    assert r.returncode == 0
    events = _read_all(tmp_path)
    assert events[-1]["event_type"] == "task_failed"
