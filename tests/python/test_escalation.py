"""
Escalation detection tests — detect_dependency_cycle, detect_deadlock.
"""
import pytest


def _mk_task(task_id, status="pending", deps=None, tier="standard"):
    import orch_core
    return orch_core.TaskState(
        task_id=task_id,
        phase="sdd",
        status=orch_core.TaskStatus(status),
        deps=deps or [],
        tier=tier,
        task_type="spec",
        spec="x",
    )


def _state_with_tasks(tasks):
    import orch_core
    state = orch_core.OrchState()
    for t in tasks:
        state.tasks[t.task_id] = t
    return state


# ---------------------------------------------------------------------------
# detect_dependency_cycle
# ---------------------------------------------------------------------------

class TestDetectDependencyCycle:

    def test_no_cycle_returns_empty(self):
        import orch_core
        # t1 → t2 → t3 (linear, no cycle)
        state = _state_with_tasks([
            _mk_task("t1", deps=[]),
            _mk_task("t2", deps=["t1"]),
            _mk_task("t3", deps=["t2"]),
        ])
        assert orch_core.detect_dependency_cycle(state) == []

    def test_direct_cycle_detected(self):
        import orch_core
        # t1 depends on t2, t2 depends on t1
        state = _state_with_tasks([
            _mk_task("t1", deps=["t2"]),
            _mk_task("t2", deps=["t1"]),
        ])
        cycle = orch_core.detect_dependency_cycle(state)
        assert len(cycle) > 0

    def test_three_node_cycle(self):
        import orch_core
        state = _state_with_tasks([
            _mk_task("t1", deps=["t3"]),
            _mk_task("t2", deps=["t1"]),
            _mk_task("t3", deps=["t2"]),
        ])
        cycle = orch_core.detect_dependency_cycle(state)
        assert len(cycle) > 0

    def test_completed_tasks_excluded_from_cycle_detection(self):
        import orch_core
        # t1(completed) ← t2(pending) → t3(pending) ← t2 (no live cycle)
        state = _state_with_tasks([
            _mk_task("t1", status="completed", deps=[]),
            _mk_task("t2", status="pending", deps=["t1"]),
        ])
        assert orch_core.detect_dependency_cycle(state) == []

    def test_empty_state_returns_empty(self):
        import orch_core
        state = orch_core.OrchState()
        assert orch_core.detect_dependency_cycle(state) == []


# ---------------------------------------------------------------------------
# detect_deadlock
# ---------------------------------------------------------------------------

class TestDetectDeadlock:

    def test_no_tasks_is_not_deadlock(self):
        import orch_core
        state = orch_core.OrchState()
        assert orch_core.detect_deadlock(state) is False

    def test_running_task_is_not_deadlock(self):
        import orch_core
        state = _state_with_tasks([_mk_task("t1", status="running")])
        assert orch_core.detect_deadlock(state) is False

    def test_ready_task_is_not_deadlock(self):
        import orch_core
        state = _state_with_tasks([_mk_task("t1", status="ready")])
        assert orch_core.detect_deadlock(state) is False

    def test_all_completed_is_not_deadlock(self):
        import orch_core
        state = _state_with_tasks([
            _mk_task("t1", status="completed"),
            _mk_task("t2", status="completed"),
        ])
        assert orch_core.detect_deadlock(state) is False

    def test_pending_blocked_by_dlq_dep_is_deadlock(self):
        import orch_core
        state = _state_with_tasks([
            _mk_task("t1", status="dlq"),
            _mk_task("t2", status="pending", deps=["t1"]),
        ])
        assert orch_core.detect_deadlock(state) is True

    def test_cycle_among_pending_tasks_is_deadlock(self):
        import orch_core
        state = _state_with_tasks([
            _mk_task("t1", status="pending", deps=["t2"]),
            _mk_task("t2", status="pending", deps=["t1"]),
        ])
        assert orch_core.detect_deadlock(state) is True

    def test_pending_with_no_blocking_deps_is_not_deadlock(self):
        import orch_core
        state = _state_with_tasks([
            _mk_task("t1", status="completed"),
            _mk_task("t2", status="pending", deps=["t1"]),
        ])
        # t2 pending but t1 is completed — t2 can become ready
        assert orch_core.detect_deadlock(state) is False


# ---------------------------------------------------------------------------
# detect_critical_dlq
# ---------------------------------------------------------------------------

class TestDetectCriticalDLQ:

    def test_critical_dlq_detected(self):
        import orch_core
        state = _state_with_tasks([
            _mk_task("t1", status="dlq", tier="critical"),
            _mk_task("t2", status="dlq", tier="standard"),
        ])
        result = orch_core.detect_critical_dlq(state)
        assert "t1" in result
        assert "t2" not in result

    def test_empty_when_no_critical_dlq(self):
        import orch_core
        state = _state_with_tasks([
            _mk_task("t1", status="completed", tier="critical"),
            _mk_task("t2", status="dlq", tier="standard"),
        ])
        assert orch_core.detect_critical_dlq(state) == []
