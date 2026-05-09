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
# canonical_json
# ---------------------------------------------------------------------------

class TestCanonicalJson:

    def test_sorted_keys(self):
        import orch_core
        obj = {"z": 1, "a": 2, "m": 3}
        result = orch_core.canonical_json(obj)
        assert result == '{"a":2,"m":3,"z":1}'

    def test_no_whitespace(self):
        import orch_core
        result = orch_core.canonical_json({"k": "v"})
        assert " " not in result

    def test_deterministic_across_calls(self):
        import orch_core
        obj = {"b": [1, 2, 3], "a": {"nested": True}}
        assert orch_core.canonical_json(obj) == orch_core.canonical_json(obj)

    def test_nested_sorted(self):
        import orch_core
        obj = {"b": {"z": 1, "a": 2}, "a": 0}
        result = orch_core.canonical_json(obj)
        parsed = json.loads(result)
        assert list(parsed.keys()) == ["a", "b"]
        assert list(parsed["b"].keys()) == ["a", "z"]


# ---------------------------------------------------------------------------
# stale_tasks
# ---------------------------------------------------------------------------

class TestStaleTasks:

    def test_returns_empty_when_no_running_tasks(self, orch_dir):
        import orch_core
        state = orch_core.reduce_all()
        result = orch_core.stale_tasks(state, _now())
        assert result == []

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

    def test_invalid_json_raises_config_error(self, orch_dir):
        import orch_core
        config_path = orch_dir / ".orch" / "config.json"
        config_path.write_text("not json {{{")
        with pytest.raises(orch_core.ConfigError):
            orch_core.load_config(config_path)

    def test_explicit_path_override(self, tmp_path):
        import orch_core
        custom_path = tmp_path / "custom_config.json"
        # File doesn't exist → return defaults
        cfg = orch_core.load_config(custom_path)
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

    def test_stack_defaults_to_be_on_invalid(self):
        import orch_core
        content = "stack: unknown_value\n"
        result = orch_core.parse_manifest_fields(content)
        assert result["stack"] == "be"

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
        assert result["stack"] == "be"
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

    def test_returns_empty_when_no_scheduled_tasks(self, orch_dir):
        import orch_core
        state = orch_core.reduce_all()
        result = orch_core.tasks_ready_for_retry(state, _now())
        assert result == []

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

    def test_returns_empty_when_no_workers(self, orch_dir):
        import orch_core
        result = orch_core.get_active_workers()
        assert result == []

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


# ---------------------------------------------------------------------------
# validate_orchestrator_report
# ---------------------------------------------------------------------------

def _valid_report(**overrides):
    base = {
        "status": "running",
        "workflow_id": "wf-001",
        "current_phase": "sdd",
        "last_seq": 10,
        "tasks": {"by_status": {"ready": 2, "running": 1}},
        "dispatched": [],
        "next_actions": [],
        "issues": [],
    }
    base.update(overrides)
    return base


class TestValidateOrchestratorReport:

    def test_valid_report_returns_empty_list(self):
        import orch_core
        errors = orch_core.validate_orchestrator_report(_valid_report())
        assert errors == []

    def test_missing_required_field(self):
        import orch_core
        report = _valid_report()
        del report["status"]
        errors = orch_core.validate_orchestrator_report(report)
        assert any("status" in e for e in errors)

    def test_invalid_status_value(self):
        import orch_core
        errors = orch_core.validate_orchestrator_report(_valid_report(status="unknown_state"))
        assert any("status" in e for e in errors)

    def test_all_valid_statuses_accepted(self):
        import orch_core
        for s in ("empty", "ready", "running", "blocked", "completed", "escalated", "error"):
            errors = orch_core.validate_orchestrator_report(_valid_report(status=s))
            # Status-related errors should not appear
            assert not any("not in" in e and "status" in e for e in errors), \
                f"Status {s!r} rejected unexpectedly"

    def test_tasks_missing_by_status(self):
        import orch_core
        report = _valid_report(tasks={"total": 5})  # no "by_status"
        errors = orch_core.validate_orchestrator_report(report)
        assert any("by_status" in e for e in errors)

    def test_issue_missing_fields(self):
        import orch_core
        report = _valid_report(issues=[{"code": "CB001"}])  # missing severity and detail
        errors = orch_core.validate_orchestrator_report(report)
        assert any("severity" in e for e in errors)
        assert any("detail" in e for e in errors)

    def test_issue_invalid_severity(self):
        import orch_core
        report = _valid_report(issues=[{
            "code": "CB001", "severity": "urgent", "detail": "some detail"
        }])
        errors = orch_core.validate_orchestrator_report(report)
        assert any("severity" in e for e in errors)

    def test_all_valid_severities_accepted(self):
        import orch_core
        for sev in ("critical", "warning", "info"):
            report = _valid_report(issues=[{
                "code": "X001", "severity": sev, "detail": "test"
            }])
            errors = orch_core.validate_orchestrator_report(report)
            assert not any("severity" in e for e in errors), \
                f"Severity {sev!r} rejected unexpectedly: {errors}"

    def test_missing_multiple_fields(self):
        import orch_core
        errors = orch_core.validate_orchestrator_report({})
        # All required fields should be flagged
        assert len(errors) >= len(["status", "last_seq", "tasks", "dispatched", "next_actions", "issues"])
