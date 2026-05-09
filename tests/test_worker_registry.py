"""
Worker registry tests — register_worker, lookup, idempotency, unregister.
"""
import json
import pytest


class TestRegisterWorker:

    def test_creates_registry_entry(self, orch_dir):
        import orch_core
        orch_core.register_worker("wkr-001", "task-01", 1, phase="sdd")
        entry_path = orch_dir / ".orch" / "workers" / "wkr-001.json"
        assert entry_path.exists()

    def test_entry_contains_expected_fields(self, orch_dir):
        import orch_core
        orch_core.register_worker("wkr-002", "task-02", 2, phase="dev", stack="be", task_type="impl")
        entry = json.loads((orch_dir / ".orch" / "workers" / "wkr-002.json").read_text())
        assert entry["worker_id"] == "wkr-002"
        assert entry["task_id"] == "task-02"
        assert entry["attempt"] == 2
        assert entry["phase"] == "dev"
        assert entry["stack"] == "be"
        assert entry["task_type"] == "impl"

    def test_idempotent_same_task_and_attempt(self, orch_dir):
        """Re-registering same worker_id + task_id + attempt must be a no-op."""
        import orch_core
        orch_core.register_worker("wkr-003", "task-03", 1)
        first_entry = json.loads((orch_dir / ".orch" / "workers" / "wkr-003.json").read_text())
        orch_core.register_worker("wkr-003", "task-03", 1)
        second_entry = json.loads((orch_dir / ".orch" / "workers" / "wkr-003.json").read_text())
        # registered_at must not change
        assert first_entry["registered_at"] == second_entry["registered_at"]

    def test_different_attempt_overwrites(self, orch_dir):
        """New attempt number on same worker_id must overwrite the entry."""
        import orch_core
        orch_core.register_worker("wkr-004", "task-04", 1)
        orch_core.register_worker("wkr-004", "task-04", 2)
        entry = json.loads((orch_dir / ".orch" / "workers" / "wkr-004.json").read_text())
        assert entry["attempt"] == 2

    def test_optional_fields_omitted_when_none(self, orch_dir):
        import orch_core
        orch_core.register_worker("wkr-005", "task-05", 1)
        entry = json.loads((orch_dir / ".orch" / "workers" / "wkr-005.json").read_text())
        assert "phase" not in entry
        assert "stack" not in entry
        assert "task_type" not in entry


class TestUnregisterWorker:

    def test_removes_entry(self, orch_dir):
        import orch_core
        orch_core.register_worker("wkr-006", "task-06", 1)
        orch_core.unregister_worker("wkr-006")
        assert not (orch_dir / ".orch" / "workers" / "wkr-006.json").exists()

    def test_unregister_nonexistent_is_noop(self, orch_dir):
        import orch_core
        # Should not raise
        orch_core.unregister_worker("wkr-does-not-exist")


def _setup_phase(make_event, phase: str = "sdd"):
    make_event("phase_declared", data={
        "workflow_id": "wf-test",
        "phases": [{"name": phase, "order": 1, "required": True}],
    })
    make_event("phase_entered", data={"phase": phase, "order": 1, "workflow_id": "wf-test"})


class TestCleanupStaleWorkers:

    def test_removes_worker_whose_task_is_completed(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="task-07", data={
            "phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []
        })
        make_event("task_claimed", task_id="task-07", data={
            "phase": "sdd", "worker_type": "w", "worker_id": "wkr-007"
        })
        make_event("task_completed", task_id="task-07", data={"phase": "sdd", "artifacts": []})
        orch_core.register_worker("wkr-007", "task-07", 1)

        removed = orch_core.cleanup_stale_workers(max_age_seconds=3600)
        assert "wkr-007" in removed
        assert not (orch_dir / ".orch" / "workers" / "wkr-007.json").exists()

    def test_does_not_remove_running_worker(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="task-08", data={
            "phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []
        })
        make_event("task_claimed", task_id="task-08", data={
            "phase": "sdd", "worker_type": "w", "worker_id": "wkr-008"
        })
        orch_core.register_worker("wkr-008", "task-08", 1)

        removed = orch_core.cleanup_stale_workers(max_age_seconds=3600)
        assert "wkr-008" not in removed
        assert (orch_dir / ".orch" / "workers" / "wkr-008.json").exists()
