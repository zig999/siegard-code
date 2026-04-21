"""Tests for DLQ cascade — Task 3.6."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / ".claude" / "lib"))

from orch_core import (
    OrchState, TaskState, TaskStatus, PhaseState, PhaseStatus,
    IllegalTransition, apply_event, reduce_all, append_event,
    EventType, Event, now_iso, new_event_id,
)
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state_with_tasks(tasks: dict[str, dict]) -> OrchState:
    """Build an OrchState directly from a dict of task specs."""
    state = OrchState()
    state.current_phase = "default"
    state.phases["default"] = PhaseState(
        name="default", order=1, required=True, status=PhaseStatus.ACTIVE,
    )
    for task_id, spec in tasks.items():
        t = TaskState(
            task_id=task_id,
            phase=spec.get("phase", "default"),
            status=spec["status"],
            deps=spec.get("deps", []),
            tier=spec.get("tier", "standard"),
            task_type=spec.get("type", "impl"),
            spec=spec.get("spec", ""),
            max_attempts=3,
            last_event_at=now_iso(),
        )
        state.tasks[task_id] = t
    return state


def _evt(event_type: str, task_id: str | None = None, data: dict | None = None) -> Event:
    return Event(
        seq=1,
        event_id=new_event_id(),
        ts=now_iso(),
        agent="orchestrator",
        event_type=event_type,
        task_id=task_id,
        attempt=1,
        data=data or {},
        prev_hash="GENESIS",
        hash="",
    )


# ---------------------------------------------------------------------------
# Reducer: PENDING → DLQ allowed for cascade
# ---------------------------------------------------------------------------

def test_task_dlq_accepts_pending_status():
    """task_dlq is allowed for PENDING tasks (cascade-from-dep path)."""
    state = _make_state_with_tasks({
        "t_001": {"status": TaskStatus.PENDING, "deps": ["t_999"]},
    })
    evt = _evt("task_dlq", "t_001", {
        "phase": "default", "reason": "cascade_from_dep", "last_error": "dep t_999 is in dlq"
    })
    apply_event(state, evt)
    assert state.tasks["t_001"].status == TaskStatus.DLQ


def test_task_dlq_still_rejects_completed():
    """task_dlq must not accept COMPLETED tasks."""
    state = _make_state_with_tasks({
        "t_001": {"status": TaskStatus.COMPLETED, "deps": []},
    })
    evt = _evt("task_dlq", "t_001", {
        "phase": "default", "reason": "cascade_from_dep", "last_error": "x"
    })
    with pytest.raises(IllegalTransition):
        apply_event(state, evt)


def test_task_dlq_still_rejects_ready():
    """task_dlq must not accept READY tasks."""
    state = _make_state_with_tasks({
        "t_001": {"status": TaskStatus.READY, "deps": []},
    })
    evt = _evt("task_dlq", "t_001", {
        "phase": "default", "reason": "cascade_from_dep", "last_error": "x"
    })
    with pytest.raises(IllegalTransition):
        apply_event(state, evt)


# ---------------------------------------------------------------------------
# Cascade logic (orchestrator-level, simulated)
# ---------------------------------------------------------------------------

def _find_cascade_targets(state: OrchState) -> list[tuple[str, str]]:
    """Returns (task_id, blocking_dep_id) for all pending tasks with a DLQ dep."""
    result = []
    for tid, task in state.tasks.items():
        if task.status != TaskStatus.PENDING:
            continue
        for dep_id in task.deps:
            dep = state.tasks.get(dep_id)
            if dep and dep.status == TaskStatus.DLQ:
                result.append((tid, dep_id))
                break
    return result


def test_cascade_direct_dep():
    """A pending task whose dep is in DLQ is identified for cascade."""
    state = _make_state_with_tasks({
        "t_001": {"status": TaskStatus.DLQ, "deps": []},
        "t_002": {"status": TaskStatus.PENDING, "deps": ["t_001"]},
    })
    targets = _find_cascade_targets(state)
    assert len(targets) == 1
    assert targets[0] == ("t_002", "t_001")


def test_cascade_chain_two_levels():
    """Cascade propagates through a chain: t_001→DLQ cascades t_002, then t_003."""
    state = _make_state_with_tasks({
        "t_001": {"status": TaskStatus.DLQ, "deps": []},
        "t_002": {"status": TaskStatus.PENDING, "deps": ["t_001"]},
        "t_003": {"status": TaskStatus.PENDING, "deps": ["t_002"]},
    })
    # Level 1: t_002 is a target
    targets = _find_cascade_targets(state)
    assert ("t_002", "t_001") in targets

    # Apply cascade for t_002
    for (tid, dep_id) in targets:
        evt = _evt("task_dlq", tid, {"phase": "default", "reason": "cascade_from_dep", "last_error": f"dep {dep_id} is in dlq"})
        apply_event(state, evt)

    assert state.tasks["t_002"].status == TaskStatus.DLQ

    # Level 2: t_003 is now a target
    targets2 = _find_cascade_targets(state)
    assert ("t_003", "t_002") in targets2

    for (tid, dep_id) in targets2:
        evt = _evt("task_dlq", tid, {"phase": "default", "reason": "cascade_from_dep", "last_error": f"dep {dep_id} is in dlq"})
        apply_event(state, evt)

    assert state.tasks["t_003"].status == TaskStatus.DLQ


def test_no_cascade_for_failed_dep():
    """A dep in FAILED (transient) does NOT trigger cascade. Only DLQ does."""
    state = _make_state_with_tasks({
        "t_001": {"status": TaskStatus.FAILED, "deps": []},
        "t_002": {"status": TaskStatus.PENDING, "deps": ["t_001"]},
    })
    targets = _find_cascade_targets(state)
    assert targets == []


def test_no_cascade_for_completed_dep():
    """A dep in COMPLETED does not trigger cascade (healthy case)."""
    state = _make_state_with_tasks({
        "t_001": {"status": TaskStatus.COMPLETED, "deps": []},
        "t_002": {"status": TaskStatus.PENDING, "deps": ["t_001"]},
    })
    targets = _find_cascade_targets(state)
    assert targets == []


def test_partial_deps_one_dlq_triggers_cascade():
    """Task with multiple deps: one DLQ + one completed → still cascades."""
    state = _make_state_with_tasks({
        "t_001": {"status": TaskStatus.COMPLETED, "deps": []},
        "t_002": {"status": TaskStatus.DLQ, "deps": []},
        "t_003": {"status": TaskStatus.PENDING, "deps": ["t_001", "t_002"]},
    })
    targets = _find_cascade_targets(state)
    assert len(targets) == 1
    assert targets[0][0] == "t_003"


def test_cascade_does_not_affect_ready_tasks():
    """A READY task (deps already met) is not a cascade target."""
    state = _make_state_with_tasks({
        "t_001": {"status": TaskStatus.DLQ, "deps": []},
        "t_002": {"status": TaskStatus.READY, "deps": ["t_001"]},
    })
    targets = _find_cascade_targets(state)
    assert targets == []


def test_empty_state_no_cascade():
    state = OrchState()
    assert _find_cascade_targets(state) == []


def test_three_level_chain_full_cascade():
    """t_001→t_002→t_003→t_004: full cascade after t_001 goes to DLQ."""
    state = _make_state_with_tasks({
        "t_001": {"status": TaskStatus.DLQ, "deps": []},
        "t_002": {"status": TaskStatus.PENDING, "deps": ["t_001"]},
        "t_003": {"status": TaskStatus.PENDING, "deps": ["t_002"]},
        "t_004": {"status": TaskStatus.PENDING, "deps": ["t_003"]},
    })
    # Iterate until no more cascade targets
    for _ in range(10):
        targets = _find_cascade_targets(state)
        if not targets:
            break
        for (tid, dep_id) in targets:
            evt = _evt("task_dlq", tid, {"phase": "default", "reason": "cascade_from_dep", "last_error": f"dep {dep_id} is in dlq"})
            apply_event(state, evt)

    assert state.tasks["t_002"].status == TaskStatus.DLQ
    assert state.tasks["t_003"].status == TaskStatus.DLQ
    assert state.tasks["t_004"].status == TaskStatus.DLQ
