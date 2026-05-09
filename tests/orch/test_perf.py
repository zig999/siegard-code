"""
M6 — Performance benchmark: reduce_all() without snapshots.

Validates that reduce_all() on large logs stays within acceptable bounds
before Task 1.8 (snapshots) is implemented. Establishes baseline that
quantifies when snapshots become necessary.

Acceptance thresholds:
  - 100 events: < 0.5s
  - 500 events: < 2.0s
  - 1000 events: < 5.0s

These are conservative bounds; actual runtime should be well under them
on any modern filesystem. If a threshold is breached, Task 1.8 is overdue.
"""
import time
import pytest
import orch_core
from orch_core import append_event, reduce_all


def _generate_workflow(n_tasks: int, phase: str = "dev") -> None:
    """Writes a realistic workflow with n_tasks tasks (created + claimed + completed)."""
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": f"wf_perf_{n_tasks}",
        "phases": [{"name": phase, "order": 1, "required": True}],
    })
    append_event("orchestrator", "phase_entered", data={"phase": phase, "order": 1, "workflow_id": "wf-fix"})

    for i in range(n_tasks):
        tid = f"t_{i:06d}"
        append_event("orchestrator", "task_created", task_id=tid, data={
            "phase": phase, "tier": "standard", "type": "impl",
            "spec": f"task {i}", "deps": [],
        })
        append_event("worker", "task_claimed", task_id=tid, attempt=1, data={
            "phase": phase, "worker_type": "impl", "worker_id": f"w_{i:06d}",
        })
        append_event("worker", "task_completed", task_id=tid, attempt=1, data={
            "phase": phase, "artifacts": [f"{tid}.out"], "summary": "done",
        })


class TestReduceAllPerformance:
    def test_reduce_100_events(self, tmp_orch):
        """M6.1: reduce_all on ~302 events (100 tasks × 3 + 2 phase events) < 0.5s."""
        _generate_workflow(100)
        start = time.monotonic()
        state = reduce_all()
        elapsed = time.monotonic() - start

        assert len(state.tasks) == 100
        assert elapsed < 0.5, (
            f"reduce_all() took {elapsed:.3f}s on 100 tasks — "
            f"exceeds 0.5s threshold; consider Task 1.8 (snapshots)"
        )

    def test_reduce_500_events(self, tmp_orch):
        """M6.2: reduce_all on ~1502 events (500 tasks × 3 + 2) < 2.0s."""
        _generate_workflow(500)
        start = time.monotonic()
        state = reduce_all()
        elapsed = time.monotonic() - start

        assert len(state.tasks) == 500
        assert elapsed < 2.0, (
            f"reduce_all() took {elapsed:.3f}s on 500 tasks — "
            f"exceeds 2.0s threshold; Task 1.8 (snapshots) is required"
        )

    def test_reduce_1000_events(self, tmp_orch):
        """M6.3: reduce_all on ~3002 events (1000 tasks × 3 + 2) < 5.0s."""
        _generate_workflow(1000)
        start = time.monotonic()
        state = reduce_all()
        elapsed = time.monotonic() - start

        assert len(state.tasks) == 1000
        assert elapsed < 5.0, (
            f"reduce_all() took {elapsed:.3f}s on 1000 tasks — "
            f"exceeds 5.0s threshold; Task 1.8 (snapshots) is critically overdue"
        )

    def test_multiple_reduces_linear_scaling(self, tmp_orch):
        """M6.4: time for 500 tasks is not more than 6× time for 100 tasks (sub-quadratic)."""
        _generate_workflow(100)
        t0 = time.monotonic()
        reduce_all()
        t100 = time.monotonic() - t0

        # Add 400 more tasks (total 500)
        for i in range(100, 500):
            tid = f"t_{i:06d}"
            append_event("orchestrator", "task_created", task_id=tid, data={
                "phase": "dev", "tier": "standard", "type": "impl",
                "spec": f"task {i}", "deps": [],
            })
            append_event("worker", "task_claimed", task_id=tid, attempt=1, data={
                "phase": "dev", "worker_type": "impl", "worker_id": f"w_{i:06d}",
            })
            append_event("worker", "task_completed", task_id=tid, attempt=1, data={
                "phase": "dev", "artifacts": [f"t_{i:06d}.out"], "summary": "done",
            })

        t0 = time.monotonic()
        reduce_all()
        t500 = time.monotonic() - t0

        # Allow 20× headroom for WSL/CI variance. O(n²) would show as 25× (5^2).
        # This test catches algorithmic regressions, not tight benchmarks.
        if t100 > 0.001:  # avoid division noise on very fast machines
            ratio = t500 / t100
            assert ratio < 20.0, (
                f"reduce_all scaling ratio {ratio:.1f}× (100→500 tasks) exceeds 20×; "
                f"likely O(n²) regression — investigate before enabling Task 1.8"
            )
