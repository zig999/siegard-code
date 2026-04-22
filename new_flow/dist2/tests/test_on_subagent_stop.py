"""Tests for .claude/hooks/on_subagent_stop.py — worker registry approach (C1/C7)."""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / ".claude" / "hooks" / "on_subagent_stop.py"
LIB = Path(__file__).parent.parent / ".claude" / "lib"
APPEND = Path(__file__).parent.parent / ".claude" / "skills" / "orch-log" / "scripts" / "append.py"
READ = Path(__file__).parent.parent / ".claude" / "skills" / "orch-log" / "scripts" / "read.py"

sys.path.insert(0, str(LIB))


def _run_hook(cwd: Path, stdin: str = "") -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["ORCH_PROJECT_DIR"] = str(cwd)
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
    return [json.loads(line) for line in r.stdout.strip().splitlines() if line]


def _register_worker(cwd: Path, worker_id: str, task_id: str, attempt: int) -> None:
    """Writes a worker registry entry the same way the orchestrator would."""
    workers_dir = cwd / ".orch" / "workers"
    workers_dir.mkdir(parents=True, exist_ok=True)
    entry = {"worker_id": worker_id, "task_id": task_id, "attempt": attempt}
    (workers_dir / f"{worker_id}.json").write_text(json.dumps(entry), encoding="utf-8")


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
# 7.1 — Hook synthesizes task_failed when worker stops silently
# ---------------------------------------------------------------------------

def test_hook_synthesizes_failed_when_no_terminal(tmp_path):
    """Hook with registry entry + no terminal → synthesizes task_failed."""
    _setup(tmp_path)
    _register_worker(tmp_path, "w_1", "t_001", 1)
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path)
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
    _register_worker(tmp_path, "w_1", "t_001", 1)
    _run_hook(tmp_path)
    events = _read_all(tmp_path)
    last = events[-1]
    assert last["event_type"] == "task_failed"
    assert last["data"]["retryable"] is True
    assert last["data"]["reason"] == "worker_stopped_without_terminal_event"


def test_synthesized_failed_has_correct_phase(tmp_path):
    _setup(tmp_path)
    _register_worker(tmp_path, "w_1", "t_001", 1)
    _run_hook(tmp_path)
    events = _read_all(tmp_path)
    last = events[-1]
    assert last["data"]["phase"] == "dev"


# ---------------------------------------------------------------------------
# 7.2 — Hook is no-op when registry is empty
# ---------------------------------------------------------------------------

def test_noop_when_no_registry_entries(tmp_path):
    """No registry entries → hook is a no-op."""
    _setup(tmp_path)
    before = len(_read_all(tmp_path))
    r = _run_hook(tmp_path)
    assert r.returncode == 0
    assert len(_read_all(tmp_path)) == before


def test_noop_when_no_log(tmp_path):
    """No log file → hook is a no-op (not an orchestrated context)."""
    (tmp_path / ".orch" / "workers").mkdir(parents=True, exist_ok=True)
    _register_worker(tmp_path, "w_1", "t_001", 1)
    r = _run_hook(tmp_path)
    assert r.returncode == 0


def test_noop_when_no_orch_dir(tmp_path):
    """No .orch dir at all → hook is a no-op."""
    r = _run_hook(tmp_path)
    assert r.returncode == 0


# ---------------------------------------------------------------------------
# 7.3 — Hook is no-op if worker already emitted terminal
# ---------------------------------------------------------------------------

def test_noop_when_completed_already_emitted(tmp_path):
    _setup(tmp_path)
    _append(tmp_path, "task_completed", task_id="t_001",
            data={"phase": "dev", "artifacts": [], "summary": "done"})
    _register_worker(tmp_path, "w_1", "t_001", 1)
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path)
    assert r.returncode == 0
    assert len(_read_all(tmp_path)) == before


def test_noop_when_failed_already_emitted(tmp_path):
    _setup(tmp_path)
    _append(tmp_path, "task_failed", task_id="t_001",
            data={"phase": "dev", "reason": "impl_error", "retryable": True})
    _register_worker(tmp_path, "w_1", "t_001", 1)
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path)
    assert r.returncode == 0
    assert len(_read_all(tmp_path)) == before


def test_noop_when_task_progressed_to_later_attempt(tmp_path):
    """Registry entry for attempt=1; task has already progressed to attempt=2 → no-op.

    If the task progressed past attempt=1, attempt=1 already had a terminal event
    (retry is only possible after task_failed). The registry entry is stale.
    """
    _setup(tmp_path)
    # Simulate retry cycle: attempt=1 failed → scheduled → retried → now at attempt=2
    _append(tmp_path, "task_failed", task_id="t_001", attempt=1,
            data={"phase": "dev", "reason": "first_fail", "retryable": True})
    _append(tmp_path, "task_scheduled_retry", task_id="t_001",
            data={"phase": "dev", "next_retry_at": "2026-04-21T00:00:00Z",
                  "backoff_seconds": 30, "previous_failure_seq": 5})
    _append(tmp_path, "task_retried", task_id="t_001", attempt=2,
            data={"phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": 6})
    _append(tmp_path, "task_claimed", task_id="t_001", attempt=2,
            data={"phase": "dev", "worker_type": "impl", "worker_id": "w_2"})
    # Registry still has stale entry for attempt=1
    _register_worker(tmp_path, "w_1", "t_001", 1)
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path)
    assert r.returncode == 0
    # No synthesis: attempt=1 already had task_failed; task progressed past it
    assert len(_read_all(tmp_path)) == before


# ---------------------------------------------------------------------------
# Parallel dispatch: hook handles multiple registry entries
# ---------------------------------------------------------------------------

def test_hook_handles_multiple_registry_entries(tmp_path):
    """Two workers registered, both without terminals → two task_failed synthesized."""
    (tmp_path / ".orch").mkdir(exist_ok=True)
    _append(tmp_path, "phase_declared",
            data={"workflow_id": "wf_parallel",
                  "phases": [{"name": "dev", "order": 1, "required": True}]})
    _append(tmp_path, "phase_entered", data={"phase": "dev", "order": 1})
    for tid in ("t_001", "t_002"):
        _append(tmp_path, "task_created", task_id=tid,
                data={"phase": "dev", "tier": "standard", "type": "impl",
                      "spec": f"task {tid}", "deps": []})
        _append(tmp_path, "task_claimed", task_id=tid,
                data={"phase": "dev", "worker_type": "impl",
                      "worker_id": f"w_{tid[-3:]}"})
        _register_worker(tmp_path, f"w_{tid[-3:]}", tid, 1)

    before = len(_read_all(tmp_path))
    r = _run_hook(tmp_path)
    assert r.returncode == 0

    events = _read_all(tmp_path)
    new_events = [e for e in events[before:] if e["event_type"] == "task_failed"]
    assert len(new_events) == 2
    synthesized_tasks = {e["task_id"] for e in new_events}
    assert synthesized_tasks == {"t_001", "t_002"}


# ---------------------------------------------------------------------------
# Edge: hook accepts and ignores stdin JSON (as Claude Code would send)
# ---------------------------------------------------------------------------

def test_hook_ignores_stdin(tmp_path):
    _setup(tmp_path)
    _register_worker(tmp_path, "w_1", "t_001", 1)
    stdin_payload = json.dumps({"stop_hook_active": True, "session_id": "abc"})
    r = _run_hook(tmp_path, stdin=stdin_payload)
    assert r.returncode == 0
    events = _read_all(tmp_path)
    assert events[-1]["event_type"] == "task_failed"
