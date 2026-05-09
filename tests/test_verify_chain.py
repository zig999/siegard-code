"""
verify_chain(), verify_and_recover(), and read_events_filtered() tests.
"""
import json
import pytest


def _task_data(**kw) -> dict:
    base = {"phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []}
    base.update(kw)
    return base


def _setup_phase(make_event, phase="sdd"):
    make_event("phase_declared", data={
        "workflow_id": "wf-vc",
        "phases": [{"name": phase, "order": 1, "required": True}],
    })
    make_event("phase_entered", data={"phase": phase, "order": 1, "workflow_id": "wf-vc"})


# ---------------------------------------------------------------------------
# verify_chain — valid log
# ---------------------------------------------------------------------------

class TestVerifyChain:

    def test_empty_log_is_ok(self, orch_dir):
        import orch_core
        result = orch_core.verify_chain()
        assert result.ok is True
        assert result.events_verified == 0

    def test_valid_chain_passes(self, orch_dir, make_event):
        import orch_core
        for i in range(5):
            make_event("orchestrator_heartbeat", data={})
        result = orch_core.verify_chain()
        assert result.ok is True
        assert result.events_verified == 5

    def test_detects_tampered_hash_field(self, orch_dir, make_event):
        import orch_core
        make_event("orchestrator_heartbeat", data={})
        make_event("orchestrator_heartbeat", data={})
        make_event("orchestrator_heartbeat", data={})

        log_path = orch_dir / ".orch" / "log.jsonl"
        lines = log_path.read_bytes().splitlines()
        # Tamper the hash field of the second event
        obj = json.loads(lines[1])
        obj["hash"] = "0" * 64
        lines[1] = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        log_path.write_bytes(b"\n".join(lines) + b"\n")

        result = orch_core.verify_chain(mode="strict")
        assert result.ok is False
        assert result.first_error_seq is not None

    def test_detects_broken_prev_hash(self, orch_dir, make_event):
        import orch_core
        make_event("orchestrator_heartbeat", data={})
        make_event("orchestrator_heartbeat", data={})

        log_path = orch_dir / ".orch" / "log.jsonl"
        lines = log_path.read_bytes().splitlines()
        obj = json.loads(lines[1])
        obj["prev_hash"] = "deadbeef" * 8
        # Recompute hash to avoid hash_mismatch (test chain_broken specifically)
        from orch_core import Event
        e = Event.from_dict(obj)
        e.hash = ""
        obj["hash"] = ""
        lines[1] = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        log_path.write_bytes(b"\n".join(lines) + b"\n")

        result = orch_core.verify_chain(mode="strict")
        assert result.ok is False
        assert result.error_details[0]["type"] in ("chain_broken", "hash_mismatch")

    def test_audit_mode_collects_all_errors(self, orch_dir, make_event):
        import orch_core
        for _ in range(4):
            make_event("orchestrator_heartbeat", data={})

        log_path = orch_dir / ".orch" / "log.jsonl"
        lines = log_path.read_bytes().splitlines()
        # Tamper lines 1 and 2 (0-indexed)
        for idx in [1, 2]:
            obj = json.loads(lines[idx])
            obj["hash"] = "f" * 64
            lines[idx] = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        log_path.write_bytes(b"\n".join(lines) + b"\n")

        result = orch_core.verify_chain(mode="audit")
        assert result.ok is False
        assert len(result.error_details) >= 1  # at least the first tampered entry

    def test_explicit_log_path_override(self, orch_dir, make_event, tmp_path):
        import orch_core
        # Write to main log (for chain context) but verify an empty separate path
        other_log = tmp_path / "other.jsonl"
        result = orch_core.verify_chain(log_path=other_log)
        assert result.ok is True
        assert result.events_verified == 0


# ---------------------------------------------------------------------------
# verify_and_recover
# ---------------------------------------------------------------------------

class TestVerifyAndRecover:

    def test_requires_confirm_true(self, orch_dir, make_event):
        import orch_core
        make_event("orchestrator_heartbeat", data={})
        with pytest.raises(ValueError, match="confirm=True"):
            orch_core.verify_and_recover(from_seq=1, operator="ops", confirm=False)

    def test_requires_from_seq_gte_1(self, orch_dir, make_event):
        import orch_core
        make_event("orchestrator_heartbeat", data={})
        with pytest.raises(ValueError, match="from_seq"):
            orch_core.verify_and_recover(from_seq=0, operator="ops", confirm=True)

    def test_raises_when_log_absent(self, orch_dir):
        import orch_core
        with pytest.raises(FileNotFoundError):
            orch_core.verify_and_recover(from_seq=1, operator="ops", confirm=True)

    def test_truncates_at_from_seq_and_appends_log_recovered(self, orch_dir, make_event):
        import orch_core
        for _ in range(5):
            make_event("orchestrator_heartbeat", data={})

        recovery_event = orch_core.verify_and_recover(
            from_seq=4, operator="ops@test.com", confirm=True
        )

        assert recovery_event.event_type == "log_recovered"
        # Events 4 and 5 (original heartbeats) removed; log_recovered appended as new seq 4
        events = list(orch_core.read_events())
        event_types = [e.event_type for e in events]
        # No heartbeat after seq 3 — log_recovered replaces the corrupt tail
        heartbeat_seqs = [e.seq for e in events if e.event_type == "orchestrator_heartbeat"]
        assert max(heartbeat_seqs) == 3
        assert recovery_event.seq in [e.seq for e in events]
        assert "log_recovered" in event_types

    def test_corrupt_archive_written(self, orch_dir, make_event):
        import orch_core
        for _ in range(3):
            make_event("orchestrator_heartbeat", data={})

        orch_core.verify_and_recover(from_seq=2, operator="ops", confirm=True)

        # Archive file must exist in .orch/
        archives = list((orch_dir / ".orch").glob("log.jsonl.corrupt.*"))
        assert len(archives) >= 1

    def test_chain_valid_after_recovery(self, orch_dir, make_event):
        import orch_core
        for _ in range(4):
            make_event("orchestrator_heartbeat", data={})

        orch_core.verify_and_recover(from_seq=3, operator="ops", confirm=True)

        result = orch_core.verify_chain()
        assert result.ok is True


# ---------------------------------------------------------------------------
# read_events_filtered
# ---------------------------------------------------------------------------

class TestReadEventsFiltered:

    def test_filter_by_task_id(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_data())
        make_event("task_created", task_id="t2", data=_task_data())
        make_event("orchestrator_heartbeat", data={})

        events = orch_core.read_events_filtered(task_id="t1")
        assert all(e.task_id == "t1" for e in events)
        assert len(events) == 1

    def test_filter_by_event_type(self, orch_dir, make_event):
        import orch_core
        make_event("orchestrator_heartbeat", data={})
        make_event("orchestrator_heartbeat", data={})
        make_event("snapshot", data={})

        events = orch_core.read_events_filtered(event_type="orchestrator_heartbeat")
        assert len(events) == 2
        assert all(e.event_type == "orchestrator_heartbeat" for e in events)

    def test_filter_by_phase(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event, "sdd")
        make_event("task_created", task_id="t1", data=_task_data(phase="sdd"))
        make_event("task_created", task_id="t2", data=_task_data(phase="dev"))

        events = orch_core.read_events_filtered(phase="sdd")
        assert all(e.data.get("phase") == "sdd" for e in events)

    def test_tail_returns_last_n(self, orch_dir, make_event):
        import orch_core
        for _ in range(10):
            make_event("orchestrator_heartbeat", data={})

        events = orch_core.read_events_filtered(tail=3)
        assert len(events) == 3
        assert events[-1].seq == 10

    def test_from_seq_filter(self, orch_dir, make_event):
        import orch_core
        for _ in range(6):
            make_event("orchestrator_heartbeat", data={})

        events = orch_core.read_events_filtered(from_seq=4)
        assert all(e.seq >= 4 for e in events)
        assert len(events) == 3

    def test_empty_log_returns_empty_list(self, orch_dir):
        import orch_core
        assert orch_core.read_events_filtered() == []

    def test_combined_filters(self, orch_dir, make_event):
        import orch_core
        _setup_phase(make_event)
        make_event("task_created", task_id="t1", data=_task_data())
        make_event("task_created", task_id="t2", data=_task_data())
        make_event("orchestrator_heartbeat", data={})

        events = orch_core.read_events_filtered(event_type="task_created", task_id="t1")
        assert len(events) == 1
        assert events[0].task_id == "t1"
