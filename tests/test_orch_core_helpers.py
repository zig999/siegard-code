"""
Tests for orch_core helper functions:
stale_tasks, load_config, parse_manifest_fields, tasks_ready_for_retry,
get_orphaned_dep_ids, get_active_workers, validate_orchestrator_report, canonical_json.
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _now() -> str:
    return _iso(datetime.now(timezone.utc))


def _past(seconds: int) -> str:
    return _iso(datetime.now(timezone.utc) - timedelta(seconds=seconds))


def _future(seconds: int) -> str:
    return _iso(datetime.now(timezone.utc) + timedelta(seconds=seconds))


def _setup_phase(make_event, phase: str = "sdd"):
    make_event("phase_declared", data={
        "workflow_id": "wf-helpers",
        "phases": [{"name": phase, "order": 1, "required": True}],
    })
    make_event("phase_entered", data={"phase": phase, "order": 1, "workflow_id": "wf-helpers"})


def _task_data(**kw):
    base = {"phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# stale_tasks
# ---------------------------------------------------------------------------

class TestStaleTasks:

    def test_running_task_within_threshold_not_stale(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_data())
        make_event("task_claimed", task_id="t1", data={
            "phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-01"
        })
        state = orch_core.reduce_all()
        # Standard tier stale threshold is 300s — check just 10s after claim
        result = orch_core.stale_tasks(state, _now())
        assert result == []

    def test_running_task_past_threshold_is_stale(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_data(tier="standard"))
        make_event("task_claimed", task_id="t1", data={
            "phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-02"
        })
        state = orch_core.reduce_all()
        # Simulate "now" being 400s past the standard tier threshold (300s)
        future_now = _future(700)
        result = orch_core.stale_tasks(state, future_now)
        assert any(t.task_id == "t1" for t in result)

    def test_bulk_tier_has_shorter_threshold(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_data(tier="bulk"))
        make_event("task_claimed", task_id="t1", data={
            "phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-03"
        })
        state = orch_core.reduce_all()
        # Bulk threshold is 120s — 200s from now should be stale
        result = orch_core.stale_tasks(state, _future(200))
        assert any(t.task_id == "t1" for t in result)

    def test_completed_task_not_included(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_data())
        make_event("task_claimed", task_id="t1", data={
            "phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-04"
        })
        make_event("task_completed", task_id="t1", data={"phase": "sdd", "artifacts": []})
        state = orch_core.reduce_all()
        result = orch_core.stale_tasks(state, _future(9999))
        assert result == []


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:

    def test_no_file_returns_defaults(self, orch_dir):
        import orch_core
        cfg = orch_core.load_config()
        assert "retry_policy" in cfg
        assert "circuit_breaker" in cfg
        assert cfg["version"] == "1.0"

    def test_partial_override_merges_deeply(self, orch_dir):
        import orch_core
        config_path = orch_dir / ".orch" / "config.json"
        override = {"circuit_breaker": {"window_minutes": 99}}
        config_path.write_text(json.dumps(override))
        cfg = orch_core.load_config(config_path)
        # Merged: override takes effect
        assert cfg["circuit_breaker"]["window_minutes"] == 99
        # Other circuit_breaker fields from defaults must still be present
        assert "failure_threshold" in cfg["circuit_breaker"]

    def test_top_level_override(self, orch_dir):
        import orch_core
        config_path = orch_dir / ".orch" / "config.json"
        config_path.write_text(json.dumps({"version": "2.0"}))
        cfg = orch_core.load_config(config_path)
        assert cfg["version"] == "2.0"
        # Other keys still present
        assert "retry_policy" in cfg


# ---------------------------------------------------------------------------
# parse_manifest_fields
# ---------------------------------------------------------------------------

class TestParseManifestFields:

    def test_parses_stack(self):
        import orch_core
        content = "stack: fe\n"
        result = orch_core.parse_manifest_fields(content)
        assert result["stack"] == "fe"

    def test_unknown_stack_no_packages_is_none(self):
        # prod-hardening task 05 (A3-F7): unknown stack + no package signal -> None
        # (fail-closed), not silently coerced to "be".
        import orch_core
        content = "stack: unknown_value\n"
        result = orch_core.parse_manifest_fields(content)
        assert result["stack"] is None

    def test_parses_type_from_handoff_block(self):
        import orch_core
        content = "handoff:\n  type: new_feature\n"
        result = orch_core.parse_manifest_fields(content)
        assert result["type"] == "new_feature"

    def test_type_defaults_to_new_domain(self):
        import orch_core
        content = "stack: be\n"
        result = orch_core.parse_manifest_fields(content)
        assert result["type"] == "new_domain"

    def test_parses_dev_impact(self):
        import orch_core
        content = "dev_impact: high\n"
        result = orch_core.parse_manifest_fields(content)
        assert result["dev_impact"] == "high"

    def test_parses_changed_files_list(self):
        import orch_core
        content = "changed_files:\n  - src/main.py\n  - src/utils.py\n"
        result = orch_core.parse_manifest_fields(content)
        assert result["changed_files"] == ["src/main.py", "src/utils.py"]

    def test_empty_content_returns_defaults(self):
        import orch_core
        result = orch_core.parse_manifest_fields("")
        assert result["stack"] is None        # task 05 (A3-F7): empty -> unresolved, fail-closed
        assert result["type"] == "new_domain"
        assert result["dev_impact"] == ""
        assert result["changed_files"] == []

    def test_fullstack_is_valid(self):
        import orch_core
        result = orch_core.parse_manifest_fields("stack: fullstack\n")
        assert result["stack"] == "fullstack"

    def test_quoted_values(self):
        import orch_core
        content = 'stack: "fe"\ndev_impact: "medium"\n'
        result = orch_core.parse_manifest_fields(content)
        assert result["stack"] == "fe"
        assert result["dev_impact"] == "medium"


# ---------------------------------------------------------------------------
# tasks_ready_for_retry
# ---------------------------------------------------------------------------

class TestTasksReadyForRetry:

    def test_scheduled_task_with_past_retry_at_is_ready(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_data())
        make_event("task_claimed", task_id="t1", data={
            "phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-01"
        })
        make_event("task_failed", task_id="t1", data={
            "phase": "sdd", "reason": "internal_error", "retryable": True
        })
        make_event("task_scheduled_retry", task_id="t1", data={
            "phase": "sdd",
            "backoff_seconds": 30.0,
            "previous_failure_seq": 4,
            "next_retry_at": _past(60),  # overdue
        })
        state = orch_core.reduce_all()
        result = orch_core.tasks_ready_for_retry(state, _now())
        assert any(t.task_id == "t1" for t in result)

    def test_scheduled_task_with_future_retry_at_not_ready(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_data())
        make_event("task_claimed", task_id="t1", data={
            "phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-02"
        })
        make_event("task_failed", task_id="t1", data={
            "phase": "sdd", "reason": "internal_error", "retryable": True
        })
        make_event("task_scheduled_retry", task_id="t1", data={
            "phase": "sdd",
            "backoff_seconds": 3600.0,
            "previous_failure_seq": 4,
            "next_retry_at": _future(3600),  # far in the future
        })
        state = orch_core.reduce_all()
        result = orch_core.tasks_ready_for_retry(state, _now())
        assert result == []

    def test_scheduled_task_with_no_retry_at_is_immediately_ready(self, orch_dir, make_event):
        """task_scheduled_retry with next_retry_at omitted → `reduce` won't set it;
        we can't emit task_scheduled_retry without next_retry_at (required field),
        so instead we validate that an overdue timestamp returns the task as ready."""
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_data())
        make_event("task_claimed", task_id="t1", data={
            "phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-03"
        })
        make_event("task_failed", task_id="t1", data={
            "phase": "sdd", "reason": "internal_error", "retryable": True
        })
        make_event("task_scheduled_retry", task_id="t1", data={
            "phase": "sdd",
            "backoff_seconds": 1.0,
            "previous_failure_seq": 4,
            "next_retry_at": _past(10),  # already overdue
        })
        state = orch_core.reduce_all()
        result = orch_core.tasks_ready_for_retry(state, _now())
        assert any(t.task_id == "t1" for t in result)


# ---------------------------------------------------------------------------
# get_orphaned_dep_ids
# ---------------------------------------------------------------------------

class TestGetOrphanedDepIds:

    def test_no_orphans_when_all_deps_present(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="dep1", data=_task_data())
        make_event("task_created", task_id="child", data=_task_data(deps=["dep1"]))
        state = orch_core.reduce_all()
        child_task = state.tasks["child"]
        result = orch_core.get_orphaned_dep_ids(child_task, state)
        assert result == []

    def test_orphan_detected_when_dep_absent(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        # Create child that references a dep that was never created
        make_event("task_created", task_id="child", data=_task_data(deps=["ghost-dep"]))
        state = orch_core.reduce_all()
        child_task = state.tasks["child"]
        result = orch_core.get_orphaned_dep_ids(child_task, state)
        assert "ghost-dep" in result

    def test_multiple_orphans(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="child", data=_task_data(deps=["a", "b", "c"]))
        state = orch_core.reduce_all()
        child_task = state.tasks["child"]
        orphans = orch_core.get_orphaned_dep_ids(child_task, state)
        assert set(orphans) == {"a", "b", "c"}

    def test_task_with_no_deps_has_no_orphans(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_data(deps=[]))
        state = orch_core.reduce_all()
        result = orch_core.get_orphaned_dep_ids(state.tasks["t1"], state)
        assert result == []


# ---------------------------------------------------------------------------
# get_active_workers
# ---------------------------------------------------------------------------

class TestGetActiveWorkers:

    def test_returns_registered_workers(self, orch_dir):
        import orch_core
        orch_core.register_worker("wkr-001", "task-01", 1, phase="sdd")
        orch_core.register_worker("wkr-002", "task-02", 1, phase="sdd")
        result = orch_core.get_active_workers()
        ids = {w["worker_id"] for w in result}
        assert ids == {"wkr-001", "wkr-002"}

    def test_unregistered_worker_not_in_list(self, orch_dir):
        import orch_core
        orch_core.register_worker("wkr-003", "task-03", 1)
        orch_core.unregister_worker("wkr-003")
        result = orch_core.get_active_workers()
        assert not any(w["worker_id"] == "wkr-003" for w in result)

    def test_returns_all_fields(self, orch_dir):
        import orch_core
        orch_core.register_worker("wkr-004", "task-04", 2, phase="dev", stack="fe", task_type="impl")
        workers = orch_core.get_active_workers()
        w = next(x for x in workers if x["worker_id"] == "wkr-004")
        assert w["task_id"] == "task-04"
        assert w["attempt"] == 2
        assert w["phase"] == "dev"


