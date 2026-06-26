"""Tests for .claude/hooks/on_subagent_stop.py — worker registry approach (C1/C7)."""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent.parent / "dist" / ".claude" / "hooks" / "on_subagent_stop.py"
LIB = Path(__file__).parent.parent.parent / "dist" / ".claude" / "lib"
APPEND = Path(__file__).parent.parent.parent / "dist" / ".claude" / "skills" / "orch-log" / "scripts" / "append.py"
READ = Path(__file__).parent.parent.parent / "dist" / ".claude" / "skills" / "orch-log" / "scripts" / "read.py"

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


def _force_expired(cwd: Path) -> None:
    """Writes .orch/config.json so EVERY worker is past its liveness window (F-03).

    Sets all tier thresholds to -1 AND clears the task-type overrides, so any
    elapsed time (>= 0 > -1) counts as expired regardless of the task's type —
    this deterministically exercises the synthesis path without depending on
    wall-clock timing. The default (no config) keeps the real window, under which
    a freshly-claimed worker is deferred to the stale reaper.
    """
    (cwd / ".orch").mkdir(exist_ok=True)
    # Set both tier defaults AND the "impl" task-type override (the type these tests
    # seed) to -1. Since load_config deep-merges, leaving overrides_by_task_type out
    # would let the shipped impl=1200 default survive and defeat the forced expiry.
    cfg = {"stale_policy": {
        "defaults_by_tier": {"critical": -1, "standard": -1, "bulk": -1},
        "overrides_by_task_type": {"impl": -1},
    }}
    (cwd / ".orch" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


def _setup(tmp_path: Path) -> None:
    (tmp_path / ".orch").mkdir(exist_ok=True)
    _append(tmp_path, "phase_declared",
            data={"workflow_id": "wf_1",
                  "phases": [{"name": "dev", "order": 1, "required": True}]})
    _append(tmp_path, "phase_entered", data={"phase": "dev", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "task_created", task_id="t_001",
            data={"phase": "dev", "tier": "standard",
                  "type": "impl", "spec": "do X", "deps": []})
    _append(tmp_path, "task_claimed", task_id="t_001",
            data={"phase": "dev", "worker_type": "code-writer", "worker_id": "w_1"})


# ---------------------------------------------------------------------------
# 7.1 — Hook synthesizes task_failed when worker stops silently
# ---------------------------------------------------------------------------

def test_hook_synthesizes_failed_when_no_terminal(tmp_path):
    """Hook with registry entry + no terminal + past liveness window → synthesizes task_failed."""
    _setup(tmp_path)
    _force_expired(tmp_path)
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
    _force_expired(tmp_path)
    _register_worker(tmp_path, "w_1", "t_001", 1)
    _run_hook(tmp_path)
    events = _read_all(tmp_path)
    last = events[-1]
    assert last["event_type"] == "task_failed"
    assert last["data"]["retryable"] is True
    assert last["data"]["reason"] == "worker_exited_without_terminal"


def test_synthesized_failed_has_correct_phase(tmp_path):
    _setup(tmp_path)
    _force_expired(tmp_path)
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
            data={"phase": "dev", "reason": "internal_error", "retryable": True})
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
            data={"phase": "dev", "reason": "internal_error", "retryable": True})
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

def _setup_two_workers(tmp_path):
    (tmp_path / ".orch").mkdir(exist_ok=True)
    _append(tmp_path, "phase_declared",
            data={"workflow_id": "wf_parallel",
                  "phases": [{"name": "dev", "order": 1, "required": True}]})
    _append(tmp_path, "phase_entered", data={"phase": "dev", "order": 1, "workflow_id": "wf-fix"})
    for tid in ("t_001", "t_002"):
        _append(tmp_path, "task_created", task_id=tid,
                data={"phase": "dev", "tier": "standard", "type": "impl",
                      "spec": f"task {tid}", "deps": []})
        _append(tmp_path, "task_claimed", task_id=tid,
                data={"phase": "dev", "worker_type": "impl",
                      "worker_id": f"w_{tid[-3:]}"})
        _register_worker(tmp_path, f"w_{tid[-3:]}", tid, 1)


def test_hook_handles_multiple_registry_entries(tmp_path):
    """Two workers registered, both past their window → two task_failed synthesized."""
    _setup_two_workers(tmp_path)
    _force_expired(tmp_path)

    before = len(_read_all(tmp_path))
    r = _run_hook(tmp_path)
    assert r.returncode == 0

    events = _read_all(tmp_path)
    new_events = [e for e in events[before:] if e["event_type"] == "task_failed"]
    assert len(new_events) == 2
    synthesized_tasks = {e["task_id"] for e in new_events}
    assert synthesized_tasks == {"t_001", "t_002"}


# ---------------------------------------------------------------------------
# F-03 / SIEGARD BUG-1 regression — correlation gate: a stop must not kill a
# still-live worker, whether it is one of several OR the sole registered worker.
# Liveness (silence past the task-type window) is the only synthesis trigger.
# ---------------------------------------------------------------------------

def test_sole_stopping_worker_within_window_is_deferred(tmp_path):
    """SIEGARD BUG-1: a single non-terminal worker still within its liveness window
    is NOT synthesized on a stop.

    SubagentStop carries no key proving the stop belongs to this worker — it may be a
    sibling/auxiliary subagent's stop, or this worker may be mid-finalization (about to
    emit its terminal). With the default window (fresh claim) the hook defers to the
    stale reaper instead of reaping a possibly-live worker. The original bug failed a QA
    worker silent only ~107s under a 900s window, which then completed seconds later.
    """
    _setup(tmp_path)
    _register_worker(tmp_path, "w_1", "t_001", 1)
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path)
    assert r.returncode == 0
    events = _read_all(tmp_path)
    # Deferred — no synthesis while the worker is still within its window.
    assert len(events) == before


def test_sibling_stop_does_not_kill_live_workers(tmp_path):
    """Two live workers; a SubagentStop fires → neither is failed (F-03 core regression)."""
    _setup_two_workers(tmp_path)  # no config → default window; both just claimed
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path)
    assert r.returncode == 0

    events = _read_all(tmp_path)
    new_failed = [e for e in events[before:] if e["event_type"] == "task_failed"]
    assert new_failed == []


# ---------------------------------------------------------------------------
# Edge: hook accepts and ignores stdin JSON (as Claude Code would send)
# ---------------------------------------------------------------------------

def test_hook_ignores_stdin(tmp_path):
    _setup(tmp_path)
    _force_expired(tmp_path)
    _register_worker(tmp_path, "w_1", "t_001", 1)
    stdin_payload = json.dumps({"stop_hook_active": True, "session_id": "abc"})
    r = _run_hook(tmp_path, stdin=stdin_payload)
    assert r.returncode == 0
    events = _read_all(tmp_path)
    assert events[-1]["event_type"] == "task_failed"


# ---------------------------------------------------------------------------
# R1 regression — a malformed .orch/config.json must not crash the hook; the
# terminal-synthesis invariant must hold even when config is broken.
# ---------------------------------------------------------------------------

def test_malformed_config_does_not_crash_hook(tmp_path):
    """Corrupt config.json → hook falls back to enum defaults and does not crash.

    The ConfigError fallback sets config={} (not None): worker_liveness_expired then
    uses the Tier enum defaults instead of re-invoking load_config() and re-raising,
    which would crash the hook and silently disable ALL terminal synthesis exactly when
    config is broken. SIEGARD BUG-1 makes this path load-bearing: liveness now gates the
    single-worker case too, so the {} fallback is actually exercised here. A
    freshly-claimed worker is within its (enum-default) window → correctly deferred, no
    crash, no traceback.
    """
    _setup(tmp_path)  # single worker w_1 on t_001, just claimed
    (tmp_path / ".orch" / "config.json").write_text("{ this is not json", encoding="utf-8")
    _register_worker(tmp_path, "w_1", "t_001", 1)
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr
    events = _read_all(tmp_path)
    # Fresh worker within the enum-default window → deferred, not reaped.
    assert len(events) == before


def test_sole_worker_synthesized_once_expired(tmp_path):
    """SIEGARD BUG-1 companion: once the sole worker IS past its window, it is failed.

    Confirms the fix only DEFERS live workers — it does not disable synthesis. With the
    forced-expired config (all thresholds -1) the single registered worker is reaped.
    """
    _setup(tmp_path)
    _force_expired(tmp_path)
    _register_worker(tmp_path, "w_1", "t_001", 1)
    before = len(_read_all(tmp_path))

    r = _run_hook(tmp_path)
    assert r.returncode == 0
    events = _read_all(tmp_path)
    assert len(events) == before + 1
    assert events[-1]["event_type"] == "task_failed"
    assert events[-1]["task_id"] == "t_001"
