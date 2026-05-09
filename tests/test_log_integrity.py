"""
Log integrity tests — SHA-256 hash chain, corruption detection, read_events.
"""
import json
import pytest


def _task_created_data() -> dict:
    return {"phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []}


class TestHashChain:

    def test_first_event_prev_hash_is_genesis(self, orch_dir, make_event):
        import orch_core
        e = make_event("task_created", task_id="t1", data=_task_created_data())
        assert e.prev_hash == "GENESIS"

    def test_second_event_prev_hash_matches_first_hash(self, orch_dir, make_event):
        import orch_core
        e1 = make_event("task_created", task_id="t1", data=_task_created_data())
        e2 = make_event("task_created", task_id="t2", data=_task_created_data())
        assert e2.prev_hash == e1.hash

    def test_hash_is_deterministic(self, orch_dir, make_event):
        import orch_core
        e = make_event("task_created", task_id="t1", data=_task_created_data())
        assert e.hash == e.compute_hash()

    def test_seq_increments(self, orch_dir, make_event):
        import orch_core
        e1 = make_event("task_created", task_id="t1", data=_task_created_data())
        e2 = make_event("task_created", task_id="t2", data=_task_created_data())
        e3 = make_event("task_created", task_id="t3", data=_task_created_data())
        assert e1.seq == 1
        assert e2.seq == 2
        assert e3.seq == 3


class TestReadEvents:

    def test_yields_events_in_order(self, orch_dir, make_event):
        import orch_core
        for i in range(5):
            make_event("task_created", task_id=f"t{i}", data=_task_created_data())
        events = list(orch_core.read_events())
        assert [e.seq for e in events] == [1, 2, 3, 4, 5]

    def test_from_seq_filters_earlier_events(self, orch_dir, make_event):
        import orch_core
        for i in range(5):
            make_event("task_created", task_id=f"t{i}", data=_task_created_data())
        events = list(orch_core.read_events(from_seq=3))
        assert all(e.seq >= 3 for e in events)
        assert len(events) == 3

    def test_empty_log_yields_nothing(self, orch_dir):
        import orch_core
        events = list(orch_core.read_events())
        assert events == []

    def test_truncated_last_line_tolerated(self, orch_dir, make_event):
        import orch_core
        make_event("task_created", task_id="t1", data=_task_created_data())
        log_path = orch_dir / ".orch" / "log.jsonl"
        # Append an incomplete JSON line (simulates crash mid-write)
        with open(log_path, "ab") as f:
            f.write(b'{"seq":2,"event_type":"task_created"')  # no closing brace/newline
        # Should return the valid first event without raising
        events = list(orch_core.read_events())
        assert len(events) == 1
        assert events[0].seq == 1


class TestCorruptedLog:

    def test_invalid_json_in_middle_raises_corrupted_log_error(self, orch_dir, make_event):
        import orch_core
        make_event("task_created", task_id="t1", data=_task_created_data())
        make_event("task_created", task_id="t2", data=_task_created_data())
        make_event("task_created", task_id="t3", data=_task_created_data())

        log_path = orch_dir / ".orch" / "log.jsonl"
        lines = log_path.read_bytes().splitlines()

        # Corrupt the second line (middle of the log)
        lines[1] = b'NOT_VALID_JSON'
        log_path.write_bytes(b'\n'.join(lines) + b'\n')

        with pytest.raises(orch_core.CorruptedLogError):
            list(orch_core.read_events())


class TestLastEvent:

    def test_returns_none_on_empty_log(self, orch_dir):
        import orch_core
        assert orch_core.last_event() is None

    def test_returns_last_appended_event(self, orch_dir, make_event):
        import orch_core
        make_event("task_created", task_id="t1", data=_task_created_data())
        e2 = make_event("task_created", task_id="t2", data=_task_created_data())
        last = orch_core.last_event()
        assert last.seq == e2.seq
        assert last.event_id == e2.event_id
