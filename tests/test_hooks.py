"""
Hook tests — on_subagent_stop.py behavior.

Tests are structured as unit tests of the hook's logic (main() function)
by patching stdin and running the function directly after setting up the
orch_dir environment.
"""
import io
import json
import sys
from pathlib import Path
import pytest


_HOOKS_DIR = Path(__file__).resolve().parents[1] / "dist" / ".claude" / "hooks"
_LIB_DIR = Path(__file__).resolve().parents[1] / "dist" / ".claude" / "lib"


def _import_hook():
    """Import on_subagent_stop without executing main()."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "on_subagent_stop", _HOOKS_DIR / "on_subagent_stop.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _task_created_data(**kw):
    base = {"phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []}
    base.update(kw)
    return base


def _setup_phase(make_event, phase: str = "sdd"):
    make_event("phase_declared", data={
        "workflow_id": "wf-hook",
        "phases": [{"name": phase, "order": 1, "required": True}],
    })
    make_event("phase_entered", data={"phase": phase, "order": 1, "workflow_id": "wf-hook"})


class TestOnSubagentStop:

    def test_noop_when_no_log_file(self, orch_dir, monkeypatch):
        """If log.jsonl does not exist, hook must return 0 without writing anything."""
        import orch_core
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        mod = _import_hook()
        result = mod.main()
        assert result == 0

    def test_noop_when_no_registered_workers(self, orch_dir, make_event, monkeypatch):
        """If workers/ directory is empty, hook is a no-op."""
        import orch_core
        make_event("task_created", task_id="t1", data=_task_created_data())
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        mod = _import_hook()
        result = mod.main()
        assert result == 0

    def test_appends_task_failed_when_worker_has_no_terminal(self, orch_dir, make_event, monkeypatch):
        """Worker registered and running but no terminal event → hook appends task_failed."""
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1",
                   data={"phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-hook-01"})
        # Register the worker (orchestrator step before spawn)
        orch_core.register_worker("wkr-hook-01", "t1", 1, phase="sdd")

        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        mod = _import_hook()
        mod.main()

        # A task_failed event must now be in the log
        events = list(orch_core.read_events())
        failed_events = [e for e in events if e.event_type == "task_failed" and e.task_id == "t1"]
        assert len(failed_events) == 1
        assert failed_events[0].data["reason"] == "worker_exited_without_terminal"

    def test_does_not_append_task_failed_when_terminal_already_present(
        self, orch_dir, make_event, monkeypatch
    ):
        """Worker already completed → hook must not append another task_failed."""
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1",
                   data={"phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-hook-02"})
        make_event("task_completed", task_id="t1", data={"phase": "sdd", "artifacts": []})
        # Register worker (simulate orchestrator before cleanup)
        orch_core.register_worker("wkr-hook-02", "t1", 1, phase="sdd")

        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        mod = _import_hook()
        mod.main()

        events = list(orch_core.read_events())
        failed_events = [e for e in events if e.event_type == "task_failed"]
        assert len(failed_events) == 0

    def test_does_not_append_when_task_already_failed(
        self, orch_dir, make_event, monkeypatch
    ):
        """Task already has task_failed → hook must not double-fail."""
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1",
                   data={"phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-hook-03"})
        make_event("task_failed", task_id="t1",
                   data={"phase": "sdd", "reason": "internal_error", "retryable": True})
        orch_core.register_worker("wkr-hook-03", "t1", 1, phase="sdd")

        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        mod = _import_hook()
        mod.main()

        events = list(orch_core.read_events())
        failed_events = [e for e in events if e.event_type == "task_failed"]
        # Only the original task_failed, not a synthesized second one
        assert len(failed_events) == 1


def _import_on_stop():
    """Import on_stop without executing main()."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "on_stop", _HOOKS_DIR / "on_stop.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestOnStop:

    def test_compute_metrics_empty_log(self, orch_dir):
        """Empty log → run_status 'empty', zero counts."""
        import orch_core
        mod = _import_on_stop()
        state = orch_core.reduce_all()
        metrics = mod._compute_metrics(state)

        assert metrics["run_status"] == "empty"
        assert metrics["tasks_total"] == 0
        assert metrics["tasks_completed"] == 0
        assert metrics["tasks_failed"] == 0
        assert metrics["tasks_dlq"] == 0
        assert metrics["phases_completed"] == 0
        assert "generated_at" in metrics
        assert "last_seq" in metrics

    def test_compute_metrics_all_completed(self, orch_dir, make_event):
        """All tasks completed → run_status 'completed'."""
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1",
                   data={"phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-01"})
        make_event("task_completed", task_id="t1", data={"phase": "sdd", "artifacts": []})
        mod = _import_on_stop()
        state = orch_core.reduce_all()
        metrics = mod._compute_metrics(state)

        assert metrics["run_status"] == "completed"
        assert metrics["tasks_total"] == 1
        assert metrics["tasks_completed"] == 1

    def test_compute_metrics_partial(self, orch_dir, make_event):
        """Some tasks still running → run_status 'partial'."""
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1",
                   data={"phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-02"})
        make_event("task_completed", task_id="t1", data={"phase": "sdd", "artifacts": []})
        make_event("task_created", task_id="t2", data=_task_created_data())
        # t2 is not completed
        mod = _import_on_stop()
        state = orch_core.reduce_all()
        metrics = mod._compute_metrics(state)

        assert metrics["run_status"] == "partial"

    def test_compute_metrics_with_dlq(self, orch_dir, make_event):
        """Tasks in DLQ → run_status 'completed_with_dlq' when no active tasks remain."""
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_claimed", task_id="t1",
                   data={"phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-03"})
        make_event("task_failed", task_id="t1",
                   data={"phase": "sdd", "reason": "max_attempts_exceeded", "retryable": False})
        make_event("task_dlq", task_id="t1", data={"phase": "sdd", "reason": "max_attempts_exceeded", "last_error": "exhausted retries"})
        mod = _import_on_stop()
        state = orch_core.reduce_all()
        metrics = mod._compute_metrics(state)

        assert metrics["run_status"] == "completed_with_dlq"
        assert metrics["tasks_dlq"] == 1

    def test_compute_metrics_returns_required_keys(self, orch_dir):
        """Verify all documented keys are present in the output dict."""
        import orch_core
        mod = _import_on_stop()
        state = orch_core.reduce_all()
        metrics = mod._compute_metrics(state)

        required_keys = {
            "generated_at", "workflow_id", "run_status", "current_phase",
            "last_seq", "tasks_total", "tasks_by_status", "tasks_completed",
            "tasks_failed", "tasks_dlq", "phases_completed", "phase_durations",
            "escalations", "circuit_breaker_tripped",
        }
        assert required_keys.issubset(metrics.keys())
