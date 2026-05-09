"""Tests for stale_tasks() — Task 3.5."""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parents[2] / "dist" / ".claude" / "lib"))

from orch_core import (
    OrchState, TaskState, TaskStatus, Tier, stale_tasks,
)


def _make_task(
    task_id: str,
    status: TaskStatus,
    tier: str,
    last_event_at: str,
) -> TaskState:
    t = TaskState(
        task_id=task_id,
        phase="default",
        status=status,
        deps=[],
        tier=tier,
        task_type="impl",
        spec="",
        max_attempts=3,
        last_event_at=last_event_at,
    )
    return t


def _ts(offset_seconds: float = 0.0) -> str:
    """Returns ISO timestamp relative to now (negative = past)."""
    dt = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _now() -> str:
    return _ts(0)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_stale_running_beyond_threshold():
    """Task running longer than stale_seconds is detected."""
    state = OrchState()
    # standard tier threshold = 300s; last event 400s ago
    state.tasks["t_001"] = _make_task("t_001", TaskStatus.RUNNING, "standard", _ts(-400))
    result = stale_tasks(state, _now())
    assert len(result) == 1
    assert result[0].task_id == "t_001"


def test_recent_progress_not_stale():
    """Task with recent last_event_at (well within threshold) is not stale."""
    state = OrchState()
    # standard threshold = 300s; last event 60s ago
    state.tasks["t_001"] = _make_task("t_001", TaskStatus.RUNNING, "standard", _ts(-60))
    result = stale_tasks(state, _now())
    assert result == []


def test_exactly_at_threshold_not_stale():
    """Task at exactly the threshold boundary is NOT stale (strictly >)."""
    state = OrchState()
    state.tasks["t_001"] = _make_task("t_001", TaskStatus.RUNNING, "standard", _ts(-300))
    result = stale_tasks(state, _now())
    assert result == []


def test_just_over_threshold_is_stale():
    """Task 1 second over the threshold is stale."""
    state = OrchState()
    state.tasks["t_001"] = _make_task("t_001", TaskStatus.RUNNING, "standard", _ts(-301))
    result = stale_tasks(state, _now())
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Status filtering
# ---------------------------------------------------------------------------

def test_non_running_tasks_ignored():
    """Only tasks in RUNNING status are considered."""
    state = OrchState()
    for status, tid in [
        (TaskStatus.PENDING, "t_001"),
        (TaskStatus.READY, "t_002"),
        (TaskStatus.COMPLETED, "t_003"),
        (TaskStatus.FAILED, "t_004"),
        (TaskStatus.DLQ, "t_005"),
    ]:
        state.tasks[tid] = _make_task(tid, status, "standard", _ts(-9999))
    result = stale_tasks(state, _now())
    assert result == []


def test_mixed_statuses_only_running_stale():
    """With one running-stale and multiple non-running, only running is returned."""
    state = OrchState()
    state.tasks["t_001"] = _make_task("t_001", TaskStatus.COMPLETED, "standard", _ts(-9999))
    state.tasks["t_002"] = _make_task("t_002", TaskStatus.RUNNING, "standard", _ts(-500))
    state.tasks["t_003"] = _make_task("t_003", TaskStatus.PENDING, "standard", _ts(-9999))
    result = stale_tasks(state, _now())
    assert len(result) == 1
    assert result[0].task_id == "t_002"


# ---------------------------------------------------------------------------
# Tier thresholds
# ---------------------------------------------------------------------------

def test_critical_tier_threshold_600s():
    """Critical tier threshold is 600s."""
    state = OrchState()
    # 550s ago — within critical threshold
    state.tasks["t_ok"] = _make_task("t_ok", TaskStatus.RUNNING, "critical", _ts(-550))
    # 650s ago — beyond critical threshold
    state.tasks["t_stale"] = _make_task("t_stale", TaskStatus.RUNNING, "critical", _ts(-650))
    result = stale_tasks(state, _now())
    assert len(result) == 1
    assert result[0].task_id == "t_stale"


def test_bulk_tier_threshold_120s():
    """Bulk tier threshold is 120s."""
    state = OrchState()
    state.tasks["t_ok"] = _make_task("t_ok", TaskStatus.RUNNING, "bulk", _ts(-100))
    state.tasks["t_stale"] = _make_task("t_stale", TaskStatus.RUNNING, "bulk", _ts(-130))
    result = stale_tasks(state, _now())
    assert len(result) == 1
    assert result[0].task_id == "t_stale"


def test_unknown_tier_defaults_to_standard():
    """Unknown tier string falls back to standard (300s threshold)."""
    state = OrchState()
    state.tasks["t_001"] = _make_task("t_001", TaskStatus.RUNNING, "unknown_tier", _ts(-350))
    result = stale_tasks(state, _now())
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_state_returns_empty():
    """No tasks → empty result."""
    state = OrchState()
    assert stale_tasks(state, _now()) == []


def test_task_with_no_last_event_at_skipped():
    """Task with last_event_at=None is skipped (not treated as stale)."""
    state = OrchState()
    t = TaskState(
        task_id="t_001", phase="default", status=TaskStatus.RUNNING,
        deps=[], tier="standard", task_type="impl", spec="", max_attempts=3,
    )
    t.last_event_at = None
    state.tasks["t_001"] = t
    result = stale_tasks(state, _now())
    assert result == []


def test_multiple_stale_tasks_all_returned():
    """Multiple stale running tasks are all returned."""
    state = OrchState()
    for i in range(4):
        state.tasks[f"t_{i:03d}"] = _make_task(
            f"t_{i:03d}", TaskStatus.RUNNING, "standard", _ts(-400)
        )
    result = stale_tasks(state, _now())
    assert len(result) == 4
