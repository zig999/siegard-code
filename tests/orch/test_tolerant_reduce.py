"""Tests for reduce_all_tolerant — diagnostic reduction that collects every
illegal transition instead of stopping at the first (monitor P2).

This module deliberately does NOT use the shared `orch_dir`/`make_event`
fixtures: those reload orch_core, which replaces its class objects and breaks
`isinstance`/`pytest.raises` identity for any later test in the session that
imported orch_core symbols by name. Instead it points orch_core's path globals
at a tmp dir directly (the same technique monitor._load_state uses), so no
reload happens and no other test is contaminated.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "dist" / ".claude" / "lib"))

import pytest
import orch_core


_PATH_GLOBALS = (
    "ORCH_DIR", "LOG_PATH", "LOCK_PATH", "STATE_DIR", "DLQ_DIR",
    "AUDIT_DIR", "METRICS_DIR", "BLOBS_DIR", "WORKERS_DIR", "CONFIG_PATH",
)


@pytest.fixture
def log_env(tmp_path):
    """Point orch_core at a fresh tmp .orch without reloading the module."""
    orch = tmp_path / ".orch"
    for sub in ("", "state", "dlq", "audit", "metrics", "blobs", "workers"):
        (orch / sub).mkdir(parents=True, exist_ok=True)
    saved = {name: getattr(orch_core, name) for name in _PATH_GLOBALS}
    orch_core.ORCH_DIR = orch
    orch_core.LOG_PATH = orch / "log.jsonl"
    orch_core.LOCK_PATH = orch / "log.jsonl.lock"
    orch_core.STATE_DIR = orch / "state"
    orch_core.DLQ_DIR = orch / "dlq"
    orch_core.AUDIT_DIR = orch / "audit"
    orch_core.METRICS_DIR = orch / "metrics"
    orch_core.BLOBS_DIR = orch / "blobs"
    orch_core.WORKERS_DIR = orch / "workers"
    orch_core.CONFIG_PATH = orch / "config.json"
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(orch_core, name, value)


def _event(event_type, *, task_id=None, data=None):
    return orch_core.append_event(
        event_type=event_type, agent="test-agent",
        task_id=task_id, attempt=1, data=data or {},
    )


def _claim_pending(task_id: str) -> None:
    """Create a task with NO active phase (stays pending) then claim it —
    an illegal task_claimed (pending, expected ready)."""
    _event("task_created", task_id=task_id, data={
        "phase": "dev", "tier": "standard", "type": "impl", "spec": "x", "deps": [],
    })
    _event("task_claimed", task_id=task_id, data={
        "phase": "dev", "worker_type": "impl", "worker_id": "w",
    })


def test_strict_reduce_still_raises(log_env):
    """The engine's strict reducer MUST keep rejecting a bad log."""
    _claim_pending("dev_tc_001")
    with pytest.raises(orch_core.IllegalTransition):
        orch_core.reduce_all()


def test_tolerant_reduce_collects_all_violations(log_env):
    """Two independent illegal claims → two violations, not one."""
    _claim_pending("dev_tc_001")
    _claim_pending("dev_tc_002")

    state, violations = orch_core.reduce_all_tolerant()

    assert len(violations) == 2
    assert {v.task_id for v in violations} == {"dev_tc_001", "dev_tc_002"}
    for v in violations:
        assert v.event_type == "task_claimed"
        assert v.seq is not None
        assert "expected ready" in v.message
    # State still reduced: both tasks exist (left PENDING, claim skipped).
    assert set(state.tasks) == {"dev_tc_001", "dev_tc_002"}
    assert all(t.status.value == "pending" for t in state.tasks.values())


def test_tolerant_reduce_clean_log_has_no_violations(log_env):
    """A well-formed log yields zero violations and full state."""
    _event("phase_declared", data={
        "workflow_id": "wf-test",
        "phases": [{"name": "dev", "order": 1, "required": True}],
    })
    _event("phase_entered", data={"phase": "dev", "order": 1, "workflow_id": "wf-test"})
    _event("task_created", task_id="t_ok", data={
        "phase": "dev", "tier": "standard", "type": "impl", "spec": "x", "deps": [],
    })
    state, violations = orch_core.reduce_all_tolerant()
    assert violations == []
    assert "t_ok" in state.tasks
