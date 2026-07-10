"""CONF-01 (SIEGARD self-spec) — the circuit breaker must PERSIST its trip.

Before the fix, `evaluate_circuit_state`/`run_circuit_check.py` only computed
`should_trip` and blocked the cycle; nothing appended `circuit_breaker_tripped`, so
`state.circuit_breaker` was always None, the breaker relaxed silently on window age-out,
and the reset tool was unreachable. `trip_circuit_if_due` now appends the event when the
threshold is first crossed, making the breaker sticky (blocked until manual reset).
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import orch_core

RUN_CIRCUIT = (Path(__file__).resolve().parents[2] / "dist" / ".claude"
               / "skills" / "orch-infra" / "scripts" / "run_circuit_check.py")


def _now():
    return orch_core.now_iso()


def _future(seconds):
    dt = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _write_config(orch_dir, threshold=3, enabled=True):
    cfg = {"circuit_breaker": {"failure_threshold": threshold, "enabled": enabled}}
    (orch_dir / ".orch" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


def _phase():
    orch_core.append_event("orchestrator", "phase_declared", data={
        "workflow_id": "wf", "phases": [{"name": "dev", "order": 1, "required": True}]})
    orch_core.append_event("orchestrator", "phase_entered", data={
        "phase": "dev", "order": 1, "workflow_id": "wf"})


def _fail(i):
    tid = f"t{i}"
    orch_core.append_event("orchestrator", "task_created", task_id=tid, data={
        "phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": []})
    orch_core.append_event("w", "task_claimed", task_id=tid, data={
        "phase": "dev", "worker_type": "impl", "worker_id": f"w{i}"})
    orch_core.append_event("w", "task_failed", task_id=tid, data={
        "phase": "dev", "reason": "internal_error", "retryable": True})


def _cb_events():
    return orch_core.read_events_filtered(event_type="circuit_breaker_tripped")


class TestTripCircuitIfDue:

    def test_trip_persists_when_threshold_crossed(self, tmp_orch):
        _write_config(tmp_orch, threshold=3)
        _phase()
        for i in range(3):
            _fail(i)
        evt = orch_core.trip_circuit_if_due()
        assert evt is not None
        state = orch_core.reduce_all()
        assert state.circuit_breaker is not None
        assert state.circuit_breaker["status"] == "tripped"
        assert state.circuit_breaker["failure_count"] == 3
        assert len(_cb_events()) == 1

    def test_idempotent_once_tripped(self, tmp_orch):
        _write_config(tmp_orch, threshold=3)
        _phase()
        for i in range(3):
            _fail(i)
        assert orch_core.trip_circuit_if_due() is not None
        # Second call: already tripped -> no-op, no duplicate event.
        assert orch_core.trip_circuit_if_due() is None
        assert len(_cb_events()) == 1

    def test_no_trip_below_threshold(self, tmp_orch):
        _write_config(tmp_orch, threshold=3)
        _phase()
        for i in range(2):
            _fail(i)
        assert orch_core.trip_circuit_if_due() is None
        assert orch_core.reduce_all().circuit_breaker is None
        assert _cb_events() == []

    def test_no_trip_when_disabled(self, tmp_orch):
        _write_config(tmp_orch, threshold=3, enabled=False)
        _phase()
        for i in range(5):
            _fail(i)
        assert orch_core.trip_circuit_if_due() is None
        assert _cb_events() == []

    def test_sticky_survives_window_ageout(self, tmp_orch):
        """The point of the fix: once persisted, the breaker stays tripped even when
        the failures have aged out of the window (should_trip would be False)."""
        _write_config(tmp_orch, threshold=3)
        _phase()
        for i in range(3):
            _fail(i)
        orch_core.trip_circuit_if_due()
        state = orch_core.reduce_all()
        # Far future: all failures are outside the 10-min window.
        cb = orch_core.evaluate_circuit_state(state, _future(3600), orch_core.load_config())
        assert cb["failure_count"] == 0          # window empty
        assert cb["already_tripped"] is True     # ...but the breaker is still tripped
        assert cb["should_trip"] is False        # and won't re-trip
        assert state.circuit_breaker is not None  # persisted state survives

    def test_reset_clears_persisted_trip(self, tmp_orch):
        _write_config(tmp_orch, threshold=3)
        _phase()
        for i in range(3):
            _fail(i)
        trip = orch_core.trip_circuit_if_due()
        # Manual reset now reachable because a real trip event exists.
        orch_core.append_event("operator", "human_response", data={
            "escalation_seq": trip.seq, "action": "reset_circuit_breaker", "operator": "me"})
        state = orch_core.reduce_all()
        assert state.circuit_breaker is None
        assert state.failure_timestamps == []


class TestRunCircuitCheckWiring:

    def test_run_circuit_check_appends_and_blocks(self, tmp_orch):
        _write_config(tmp_orch, threshold=3)
        _phase()
        for i in range(3):
            _fail(i)
        env = {**os.environ, "ORCH_PROJECT_DIR": str(tmp_orch)}
        p = subprocess.run([sys.executable, str(RUN_CIRCUIT)],
                           capture_output=True, text=True, env=env)
        assert p.returncode == 1, p.stderr           # blocked
        out = json.loads(p.stdout)
        assert out["status"] == "blocked" and out["tripped"] is True
        # The trip was persisted.
        assert len(_cb_events()) == 1
        # Second run: still blocked (already_tripped), no duplicate event.
        p2 = subprocess.run([sys.executable, str(RUN_CIRCUIT)],
                            capture_output=True, text=True, env=env)
        assert p2.returncode == 1
        assert len(_cb_events()) == 1
