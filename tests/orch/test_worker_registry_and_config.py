"""
Tests for: worker registry (register/unregister/get_active_workers),
load_config ConfigError (CRIT 12.3), and validate_orchestrator_report.
"""
import json
import pytest
from pathlib import Path

import orch_core
from orch_core import (
    ConfigError,
    load_config,
    register_worker,
    unregister_worker,
    get_active_workers,
    validate_orchestrator_report,
    cleanup_stale_workers,
    append_event,
)


# ---------------------------------------------------------------------------
# Worker registry
# ---------------------------------------------------------------------------


class TestWorkerRegistry:
    def test_register_creates_file(self, tmp_orch):
        register_worker("w1", "task_001", 1)
        f = orch_core.WORKERS_DIR / "w1.json"
        assert f.exists()
        data = json.loads(f.read_text())
        assert data["worker_id"] == "w1"
        assert data["task_id"] == "task_001"
        assert data["attempt"] == 1
        assert "registered_at" in data

    def test_register_multiple_workers(self, tmp_orch):
        register_worker("w1", "t1", 1)
        register_worker("w2", "t2", 2)
        workers = get_active_workers()
        ids = {w["worker_id"] for w in workers}
        assert ids == {"w1", "w2"}

    def test_unregister_removes_file(self, tmp_orch):
        register_worker("w1", "task_001", 1)
        unregister_worker("w1")
        assert not (orch_core.WORKERS_DIR / "w1.json").exists()

    def test_unregister_nonexistent_is_noop(self, tmp_orch):
        unregister_worker("nonexistent_worker")  # must not raise

    def test_get_active_workers_empty_when_no_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(orch_core, "WORKERS_DIR", tmp_path / "no_workers")
        result = get_active_workers()
        assert result == []

    def test_get_active_workers_skips_corrupt_json(self, tmp_orch):
        register_worker("w_good", "t1", 1)
        (orch_core.WORKERS_DIR / "w_bad.json").write_text("NOT JSON")
        workers = get_active_workers()
        ids = [w["worker_id"] for w in workers]
        assert "w_good" in ids
        assert len(ids) == 1

    def test_register_overwrites_same_worker(self, tmp_orch):
        register_worker("w1", "t1", 1)
        register_worker("w1", "t2", 2)
        workers = get_active_workers()
        assert len(workers) == 1
        assert workers[0]["task_id"] == "t2"
        assert workers[0]["attempt"] == 2

    def test_entry_contains_expected_fields(self, tmp_orch):
        register_worker("w5", "task_02", 2, phase="dev", stack="be", task_type="impl")
        data = json.loads((orch_core.WORKERS_DIR / "w5.json").read_text())
        assert data["worker_id"] == "w5"
        assert data["task_id"] == "task_02"
        assert data["attempt"] == 2
        assert data["phase"] == "dev"
        assert data["stack"] == "be"
        assert data["task_type"] == "impl"

    def test_idempotent_same_task_and_attempt(self, tmp_orch):
        """Re-registering same worker_id + task_id + attempt must not update registered_at."""
        register_worker("w6", "task_03", 1)
        first = json.loads((orch_core.WORKERS_DIR / "w6.json").read_text())
        register_worker("w6", "task_03", 1)
        second = json.loads((orch_core.WORKERS_DIR / "w6.json").read_text())
        assert first["registered_at"] == second["registered_at"]

    def test_different_attempt_overwrites(self, tmp_orch):
        """New attempt on same worker_id must overwrite the entry."""
        register_worker("w7", "task_04", 1)
        register_worker("w7", "task_04", 2)
        data = json.loads((orch_core.WORKERS_DIR / "w7.json").read_text())
        assert data["attempt"] == 2

    def test_optional_fields_omitted_when_none(self, tmp_orch):
        """phase, stack, task_type must be absent when not provided."""
        register_worker("w8", "task_05", 1)
        data = json.loads((orch_core.WORKERS_DIR / "w8.json").read_text())
        assert "phase" not in data
        assert "stack" not in data
        assert "task_type" not in data


# ---------------------------------------------------------------------------
# cleanup_stale_workers
# ---------------------------------------------------------------------------


def _task_data(**kw):
    base = {"phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []}
    base.update(kw)
    return base


class TestCleanupStaleWorkers:
    def test_removes_worker_whose_task_is_completed(self, tmp_orch):
        append_event("orchestrator", "phase_declared",
                     data={"workflow_id": "wf", "phases": [{"name": "sdd", "order": 1, "required": True}]})
        append_event("orchestrator", "phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-fix"})
        append_event("orchestrator", "task_created", task_id="t_07", data=_task_data())
        append_event("orchestrator", "task_claimed", task_id="t_07",
                     data={"phase": "sdd", "worker_type": "w", "worker_id": "wkr_07"})
        append_event("orchestrator", "task_completed", task_id="t_07",
                     data={"phase": "sdd", "artifacts": []})
        register_worker("wkr_07", "t_07", 1)

        removed = cleanup_stale_workers(max_age_seconds=3600)
        assert "wkr_07" in removed
        assert not (orch_core.WORKERS_DIR / "wkr_07.json").exists()

    def test_does_not_remove_running_worker(self, tmp_orch):
        append_event("orchestrator", "phase_declared",
                     data={"workflow_id": "wf", "phases": [{"name": "sdd", "order": 1, "required": True}]})
        append_event("orchestrator", "phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": "wf-fix"})
        append_event("orchestrator", "task_created", task_id="t_08", data=_task_data())
        append_event("orchestrator", "task_claimed", task_id="t_08",
                     data={"phase": "sdd", "worker_type": "w", "worker_id": "wkr_08"})
        register_worker("wkr_08", "t_08", 1)

        removed = cleanup_stale_workers(max_age_seconds=3600)
        assert "wkr_08" not in removed
        assert (orch_core.WORKERS_DIR / "wkr_08.json").exists()


# ---------------------------------------------------------------------------
# load_config — CRIT 12.3
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_missing_file_returns_defaults(self, tmp_orch):
        cfg = load_config()
        assert "retry_policy" in cfg
        assert "circuit_breaker" in cfg

    def test_invalid_json_raises_config_error(self, tmp_orch):
        """[CRIT] 12.3 Config inválido levanta ConfigError."""
        orch_core.CONFIG_PATH.write_text("{ not valid json }", encoding="utf-8")
        with pytest.raises(ConfigError) as exc_info:
            load_config()
        assert str(orch_core.CONFIG_PATH) in str(exc_info.value)

    def test_partial_config_merged_with_defaults(self, tmp_orch):
        """[HAPPY] 12.2 Config parcial mesclado com defaults (top-level key merge)."""
        # Deep merge is top-level only: retry_policy dict gets merged at level 1,
        # so circuit_breaker defaults survive even when retry_policy is partially overridden.
        partial = {"retry_policy": {"defaults_by_tier": {"standard": {"max_attempts": 7}}}}
        orch_core.CONFIG_PATH.write_text(json.dumps(partial), encoding="utf-8")
        cfg = load_config()
        # The nested value from partial overrides the defaults_by_tier entirely
        assert cfg["retry_policy"]["defaults_by_tier"]["standard"]["max_attempts"] == 7
        # Other top-level keys like circuit_breaker survive
        assert "circuit_breaker" in cfg

    def test_explicit_path_override(self, tmp_path):
        custom = tmp_path / "custom_config.json"
        custom.write_text("{}", encoding="utf-8")
        cfg = load_config(config_path=custom)
        assert "retry_policy" in cfg

    def test_explicit_path_invalid_raises_config_error(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("oops", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(config_path=bad)


# ---------------------------------------------------------------------------
# validate_orchestrator_report
# ---------------------------------------------------------------------------


def _valid_report(**overrides) -> dict:
    base = {
        "status": "running",
        "workflow_id": "wf_001",
        "current_phase": "dev",
        "last_seq": 5,
        "tasks": {"by_status": {"pending": [], "running": [], "completed": []}},
        "dispatched": [],
        "next_actions": [],
        "issues": [],
    }
    base.update(overrides)
    return base


class TestValidateOrchestratorReport:
    def test_valid_report_returns_no_errors(self):
        assert validate_orchestrator_report(_valid_report()) == []

    def test_missing_required_field(self):
        report = _valid_report()
        del report["last_seq"]
        errors = validate_orchestrator_report(report)
        assert any("last_seq" in e for e in errors)

    def test_wrong_type_for_last_seq(self):
        report = _valid_report(last_seq="not_an_int")
        errors = validate_orchestrator_report(report)
        assert any("last_seq" in e for e in errors)

    def test_unknown_status_reported(self):
        report = _valid_report(status="unknown_status")
        errors = validate_orchestrator_report(report)
        assert any("unknown_status" in e for e in errors)

    def test_all_valid_statuses_accepted(self):
        for status in ("empty", "ready", "running", "blocked", "completed", "escalated", "error"):
            assert validate_orchestrator_report(_valid_report(status=status)) == []

    def test_tasks_dict_missing_by_status(self):
        report = _valid_report(tasks={"something_else": {}})
        errors = validate_orchestrator_report(report)
        assert any("by_status" in e for e in errors)

    def test_issue_missing_code_field(self):
        report = _valid_report(issues=[{"severity": "warning", "detail": "d"}])
        errors = validate_orchestrator_report(report)
        assert any("code" in e for e in errors)

    def test_issue_unknown_severity(self):
        report = _valid_report(
            issues=[{"code": "X", "severity": "blocker", "detail": "d"}]
        )
        errors = validate_orchestrator_report(report)
        assert any("severity" in e and "blocker" in e for e in errors)

    def test_issue_valid_severities_accepted(self):
        for sev in ("critical", "warning", "info"):
            report = _valid_report(
                issues=[{"code": "E99", "severity": sev, "detail": "d"}]
            )
            assert validate_orchestrator_report(report) == []

    def test_dispatched_entry_missing_worker_id(self):
        report = _valid_report(
            dispatched=[{"task_id": "t1", "result": "completed"}]
        )
        errors = validate_orchestrator_report(report)
        assert any("worker_id" in e for e in errors)

    def test_dispatched_entry_not_a_dict(self):
        report = _valid_report(dispatched=["not_a_dict"])
        errors = validate_orchestrator_report(report)
        assert any("dispatched[0]" in e for e in errors)

    def test_valid_dispatched_entry(self):
        report = _valid_report(
            dispatched=[{"task_id": "t1", "worker_id": "w1", "result": "completed"}]
        )
        assert validate_orchestrator_report(report) == []

    def test_null_workflow_id_and_phase_accepted(self):
        report = _valid_report(workflow_id=None, current_phase=None)
        assert validate_orchestrator_report(report) == []

    def test_issue_is_not_dict_reported(self):
        report = _valid_report(issues=["not_a_dict"])
        errors = validate_orchestrator_report(report)
        assert any("issues[0]" in e for e in errors)

    def test_multiple_missing_fields_all_reported(self):
        errors = validate_orchestrator_report({})
        required = {"status", "workflow_id", "current_phase", "last_seq", "tasks", "dispatched", "next_actions", "issues"}
        reported_fields = set()
        for e in errors:
            for f in required:
                if f in e:
                    reported_fields.add(f)
        assert required == reported_fields
