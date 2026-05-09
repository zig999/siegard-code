"""Tests for Task 4.3 — evaluate_circuit_state and circuit_breaker.py reset script.

Covers scenarios 4.7, 4.8, 4.9.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

LIB = Path(__file__).parents[2] / "dist" / ".claude" / "lib"
SKILLS_DIR = Path(__file__).parents[2] / "dist" / ".claude" / "skills"
SCRIPTS_DIR = Path(__file__).parents[2] / "dist" / ".claude" / "scripts"
APPEND = str(SKILLS_DIR / "orch-log" / "scripts" / "append.py")
EMIT = str(SKILLS_DIR / "orch-report" / "scripts" / "emit.py")
CB_SCRIPT = str(SCRIPTS_DIR / "circuit_breaker.py")

sys.path.insert(0, str(LIB))

from orch_core import (
    OrchState,
    TaskStatus,
    Tier,
    default_config,
    evaluate_circuit_state,
    now_iso,
    parse_iso,
    reduce_all,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(offset_minutes: float = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)).isoformat()


def _state_with_failures(timestamps: list[str]) -> OrchState:
    s = OrchState()
    s.failure_timestamps = list(timestamps)
    return s


def _append(cwd, agent, event_type, task_id=None, attempt=1, data=None):
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


def _bootstrap_and_fail(cwd, n_failures: int, task_offset: int = 0) -> None:
    """Create n_failures tasks and fail them all."""
    import os
    if task_offset == 0:
        _append(cwd, "orchestrator", "phase_declared",
                data={"workflow_id": "wf_cb_test",
                      "phases": [{"name": "default", "order": 1, "required": True}]})
        _append(cwd, "orchestrator", "phase_entered",
                data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    for i in range(n_failures):
        tid = f"t_{task_offset + i + 1:03d}"
        _append(cwd, "orchestrator", "task_created", tid,
                data={"phase": "default", "deps": [], "tier": "standard",
                      "type": "impl", "spec": "x"})
        _append(cwd, "orchestrator", "task_claimed", tid,
                data={"phase": "default", "worker_type": "test-worker",
                      "worker_id": f"w{task_offset + i + 1}"})
        _emit(cwd, f"w{task_offset + i + 1}", "failed", tid,
              data={"phase": "default", "reason": "internal_error", "retryable": True})


def _reduce(cwd) -> OrchState:
    import os
    old = os.getcwd()
    os.chdir(str(cwd))
    try:
        return reduce_all()
    finally:
        os.chdir(old)


# ---------------------------------------------------------------------------
# evaluate_circuit_state — unit tests
# ---------------------------------------------------------------------------

class TestEvaluateCircuitState:
    def test_no_failures_should_not_trip(self):
        s = _state_with_failures([])
        result = evaluate_circuit_state(s, _now())
        assert result["should_trip"] is False
        assert result["failure_count"] == 0

    def test_threshold_reached_should_trip(self):
        # 50 failures all within the last 5 minutes
        ts = _iso(-5)  # 5 min ago — within 10min window
        s = _state_with_failures([ts] * 50)
        result = evaluate_circuit_state(s, _now())
        assert result["should_trip"] is True
        assert result["failure_count"] == 50

    def test_threshold_not_reached(self):
        ts = _iso(-5)
        s = _state_with_failures([ts] * 49)
        result = evaluate_circuit_state(s, _now())
        assert result["should_trip"] is False
        assert result["failure_count"] == 49

    def test_failures_outside_window_not_counted(self):
        """Scenario 4.8: failures outside window do not trip the breaker."""
        old_ts = _iso(-15)   # 15 min ago — outside 10min window
        new_ts = _iso(-5)    # within window
        # 30 old + 30 new = 60 total, but only 30 in window → no trip (threshold=50)
        s = _state_with_failures([old_ts] * 30 + [new_ts] * 30)
        result = evaluate_circuit_state(s, _now())
        assert result["should_trip"] is False
        assert result["failure_count"] == 30

    def test_already_tripped_should_not_trip_again(self):
        ts = _iso(-5)
        s = _state_with_failures([ts] * 50)
        s.circuit_breaker = {"status": "tripped"}
        result = evaluate_circuit_state(s, _now())
        assert result["should_trip"] is False
        assert result["already_tripped"] is True

    def test_already_tripped_flag(self):
        s = OrchState()
        s.circuit_breaker = {"status": "tripped"}
        result = evaluate_circuit_state(s, _now())
        assert result["already_tripped"] is True

    def test_not_tripped_already_tripped_false(self):
        s = OrchState()
        result = evaluate_circuit_state(s, _now())
        assert result["already_tripped"] is False

    def test_disabled_circuit_breaker_never_trips(self):
        cfg = default_config()
        cfg["circuit_breaker"]["enabled"] = False
        ts = _iso(-1)
        s = _state_with_failures([ts] * 100)
        result = evaluate_circuit_state(s, _now(), config=cfg)
        assert result["should_trip"] is False
        assert result["failure_count"] == 0

    def test_custom_threshold_in_config(self):
        cfg = default_config()
        cfg["circuit_breaker"]["failure_threshold"] = 5
        ts = _iso(-1)
        s = _state_with_failures([ts] * 5)
        result = evaluate_circuit_state(s, _now(), config=cfg)
        assert result["should_trip"] is True
        assert result["threshold"] == 5

    def test_returns_window_metadata(self):
        s = OrchState()
        result = evaluate_circuit_state(s, _now())
        assert "window_start" in result
        assert "window_end" in result
        assert "window_minutes" in result
        assert result["window_minutes"] == 10.0


# ---------------------------------------------------------------------------
# evaluate_circuit_state — integration with real log
# ---------------------------------------------------------------------------

class TestCircuitBreakerIntegration:
    def test_50_failures_trip_circuit(self, tmp_path):
        """Scenario 4.7: 50 failures in 10min trips the circuit."""
        _bootstrap_and_fail(tmp_path, 50)
        s = _reduce(tmp_path)
        assert len(s.failure_timestamps) == 50
        result = evaluate_circuit_state(s, now_iso())
        assert result["should_trip"] is True
        assert result["failure_count"] == 50

    def test_49_failures_no_trip(self, tmp_path):
        _bootstrap_and_fail(tmp_path, 49)
        s = _reduce(tmp_path)
        result = evaluate_circuit_state(s, now_iso())
        assert result["should_trip"] is False

    def test_circuit_tripped_event_in_state(self, tmp_path):
        """After emitting circuit_breaker_tripped, state.circuit_breaker is set."""
        _bootstrap_and_fail(tmp_path, 3)
        s = _reduce(tmp_path)
        # Manually emit the trip event
        _append(tmp_path, "orchestrator", "circuit_breaker_tripped",
                data={
                    "window_start": _iso(-10),
                    "window_end": _iso(),
                    "failure_count": 3,
                    "threshold": 3,
                    "window_minutes": 10,
                    "scope": "workflow",
                })
        s2 = _reduce(tmp_path)
        assert s2.circuit_breaker is not None
        assert s2.circuit_breaker["status"] == "tripped"

    def test_human_response_reset_clears_circuit(self, tmp_path):
        """Scenario 4.9: human_response with reset_circuit_breaker clears state."""
        _bootstrap_and_fail(tmp_path, 3)
        # Emit circuit_breaker_tripped
        evt = _append(tmp_path, "orchestrator", "circuit_breaker_tripped",
                      data={
                          "window_start": _iso(-10),
                          "window_end": _iso(),
                          "failure_count": 3,
                          "threshold": 3,
                          "window_minutes": 10,
                          "scope": "workflow",
                      })
        s = _reduce(tmp_path)
        assert s.circuit_breaker is not None

        # Operator resets
        _append(tmp_path, "operator", "human_response",
                data={
                    "escalation_seq": evt["seq"],
                    "action": "reset_circuit_breaker",
                    "operator": "ops@example.com",
                })
        s2 = _reduce(tmp_path)
        assert s2.circuit_breaker is None
        assert s2.failure_timestamps == []


# ---------------------------------------------------------------------------
# circuit_breaker.py CLI script
# ---------------------------------------------------------------------------

class TestCircuitBreakerScript:
    def _run(self, cwd, *args):
        r = subprocess.run(
            [sys.executable, CB_SCRIPT] + list(args),
            cwd=str(cwd), capture_output=True, text=True
        )
        return r

    def test_status_no_log(self, tmp_path):
        """Script exits with code 4 when no log exists."""
        r = self._run(tmp_path, "--status")
        assert r.returncode == 4

    def test_status_not_tripped(self, tmp_path):
        _bootstrap_and_fail(tmp_path, 1)
        r = self._run(tmp_path, "--status")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["tripped"] is False

    def test_status_tripped(self, tmp_path):
        _bootstrap_and_fail(tmp_path, 1)
        _append(tmp_path, "orchestrator", "circuit_breaker_tripped",
                data={
                    "window_start": _iso(-10), "window_end": _iso(),
                    "failure_count": 1, "threshold": 1,
                    "window_minutes": 10, "scope": "workflow",
                })
        r = self._run(tmp_path, "--status")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["tripped"] is True

    def test_reset_requires_confirm(self, tmp_path):
        """--reset without --confirm must fail with exit 2."""
        _bootstrap_and_fail(tmp_path, 1)
        _append(tmp_path, "orchestrator", "circuit_breaker_tripped",
                data={
                    "window_start": _iso(-10), "window_end": _iso(),
                    "failure_count": 1, "threshold": 1,
                    "window_minutes": 10, "scope": "workflow",
                })
        r = self._run(tmp_path, "--reset", "--operator", "ops@example.com")
        assert r.returncode == 2

    def test_reset_requires_operator(self, tmp_path):
        """--reset --confirm without --operator must fail with exit 3."""
        _bootstrap_and_fail(tmp_path, 1)
        _append(tmp_path, "orchestrator", "circuit_breaker_tripped",
                data={
                    "window_start": _iso(-10), "window_end": _iso(),
                    "failure_count": 1, "threshold": 1,
                    "window_minutes": 10, "scope": "workflow",
                })
        r = self._run(tmp_path, "--reset", "--confirm")
        assert r.returncode == 3

    def test_reset_not_tripped_returns_1(self, tmp_path):
        """--reset on a circuit that is not tripped exits 1."""
        _bootstrap_and_fail(tmp_path, 1)
        r = self._run(tmp_path, "--reset", "--confirm", "--operator", "ops@example.com")
        assert r.returncode == 1

    def test_reset_succeeds(self, tmp_path):
        """Full reset: tripped → reset emits human_response → state clears."""
        _bootstrap_and_fail(tmp_path, 1)
        _append(tmp_path, "orchestrator", "circuit_breaker_tripped",
                data={
                    "window_start": _iso(-10), "window_end": _iso(),
                    "failure_count": 1, "threshold": 1,
                    "window_minutes": 10, "scope": "workflow",
                })

        r = self._run(tmp_path, "--reset", "--confirm",
                      "--operator", "ops@example.com",
                      "--notes", "investigated and safe to resume")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["status"] == "reset"
        assert out["operator"] == "ops@example.com"

        # Verify state cleared
        s = _reduce(tmp_path)
        assert s.circuit_breaker is None
