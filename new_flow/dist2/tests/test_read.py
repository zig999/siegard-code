"""
Tests for Task 1.4: read_events, last_event, read_events_filtered.
Covers scenarios: 1.3, 1.4, 1.5, 1.6, 1.7
"""
import json

import pytest
import orch_core
from orch_core import (
    append_event, read_events, last_event, read_events_filtered,
    CorruptedLogError,
)


def _task(i: int, phase: str = "dev") -> dict:
    return {"phase": phase, "tier": "standard", "type": "impl",
            "spec": f"task {i}", "deps": []}


def _seed(tmp_orch, n: int, phase: str = "dev") -> list:
    return [
        append_event("orchestrator", "task_created",
                     task_id=f"t_{i:04d}", data=_task(i, phase))
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# Scenario 1.5: empty log
# ---------------------------------------------------------------------------

class TestEmptyLog:
    def test_read_events_empty(self, tmp_orch):
        assert list(read_events()) == []

    def test_last_event_empty(self, tmp_orch):
        assert last_event() is None

    def test_read_events_no_file(self, tmp_orch):
        """Log file does not exist yet."""
        assert not orch_core.LOG_PATH.exists()
        assert list(read_events()) == []

    def test_read_events_filtered_empty(self, tmp_orch):
        assert read_events_filtered() == []


# ---------------------------------------------------------------------------
# Scenario 1.3: read returns events in seq order
# ---------------------------------------------------------------------------

class TestReadOrder:
    def test_returns_all_events_in_order(self, tmp_orch):
        events = _seed(tmp_orch, 10)
        read_back = list(read_events())
        assert len(read_back) == 10
        assert [e.seq for e in read_back] == list(range(1, 11))

    def test_first_and_last_seq(self, tmp_orch):
        _seed(tmp_orch, 10)
        read_back = list(read_events())
        assert read_back[0].seq == 1
        assert read_back[-1].seq == 10

    def test_event_ids_preserved(self, tmp_orch):
        written = _seed(tmp_orch, 5)
        read_back = list(read_events())
        assert [e.event_id for e in read_back] == [e.event_id for e in written]


# ---------------------------------------------------------------------------
# Scenario 1.4: from_seq filter
# ---------------------------------------------------------------------------

class TestFromSeq:
    def test_from_seq_middle(self, tmp_orch):
        _seed(tmp_orch, 10)
        results = list(read_events(from_seq=5))
        assert len(results) == 6
        assert results[0].seq == 5
        assert results[-1].seq == 10

    def test_from_seq_first(self, tmp_orch):
        _seed(tmp_orch, 5)
        results = list(read_events(from_seq=1))
        assert len(results) == 5

    def test_from_seq_zero_returns_all(self, tmp_orch):
        _seed(tmp_orch, 5)
        assert len(list(read_events(from_seq=0))) == 5

    def test_from_seq_beyond_end(self, tmp_orch):
        _seed(tmp_orch, 5)
        assert list(read_events(from_seq=100)) == []

    def test_from_seq_exact_last(self, tmp_orch):
        _seed(tmp_orch, 5)
        results = list(read_events(from_seq=5))
        assert len(results) == 1
        assert results[0].seq == 5


# ---------------------------------------------------------------------------
# last_event
# ---------------------------------------------------------------------------

class TestLastEvent:
    def test_returns_last(self, tmp_orch):
        events = _seed(tmp_orch, 5)
        assert last_event().seq == 5
        assert last_event().event_id == events[-1].event_id

    def test_after_single_append(self, tmp_orch):
        e = append_event("orchestrator", "task_created",
                         task_id="t_0001", data=_task(1))
        assert last_event().seq == e.seq

    def test_updates_after_each_append(self, tmp_orch):
        for i in range(1, 6):
            append_event("orchestrator", "task_created",
                         task_id=f"t_{i:04d}", data=_task(i))
            assert last_event().seq == i


# ---------------------------------------------------------------------------
# Scenario 1.6: truncated last line tolerated
# ---------------------------------------------------------------------------

class TestTruncatedLastLine:
    def test_truncated_last_line_ignored(self, tmp_orch):
        _seed(tmp_orch, 3)
        # Append truncated (incomplete JSON) at the end
        with open(orch_core.LOG_PATH, "ab") as f:
            f.write(b'{"seq":4,"event_id":"evt_TRUNC')  # incomplete JSON

        results = list(read_events())
        assert len(results) == 3
        assert results[-1].seq == 3

    def test_last_event_with_truncated_tail(self, tmp_orch):
        _seed(tmp_orch, 3)
        with open(orch_core.LOG_PATH, "ab") as f:
            f.write(b'{"broken":')
        assert last_event().seq == 3

    def test_no_exception_on_truncation(self, tmp_orch):
        _seed(tmp_orch, 2)
        with open(orch_core.LOG_PATH, "ab") as f:
            f.write(b"not json at all")
        # Must not raise
        events = list(read_events())
        assert len(events) == 2


# ---------------------------------------------------------------------------
# Scenario 1.7: corruption in middle raises CorruptedLogError
# ---------------------------------------------------------------------------

class TestCorruptedLog:
    def test_corruption_in_middle_raises(self, tmp_orch):
        _seed(tmp_orch, 5)

        # Replace line 3 with invalid JSON
        lines = orch_core.LOG_PATH.read_bytes().splitlines(keepends=True)
        lines[2] = b"THIS IS NOT JSON\n"
        orch_core.LOG_PATH.write_bytes(b"".join(lines))

        with pytest.raises(CorruptedLogError):
            list(read_events())

    def test_corruption_at_line_one_raises(self, tmp_orch):
        _seed(tmp_orch, 3)
        lines = orch_core.LOG_PATH.read_bytes().splitlines(keepends=True)
        lines[0] = b"CORRUPT\n"
        orch_core.LOG_PATH.write_bytes(b"".join(lines))

        with pytest.raises(CorruptedLogError):
            list(read_events())

    def test_valid_last_line_not_treated_as_corrupt(self, tmp_orch):
        """A valid last line must not raise even though it's last."""
        _seed(tmp_orch, 3)
        events = list(read_events())
        assert len(events) == 3


# ---------------------------------------------------------------------------
# read_events_filtered
# ---------------------------------------------------------------------------

class TestReadEventsFiltered:
    def test_filter_by_task_id(self, tmp_orch):
        _seed(tmp_orch, 5)
        results = read_events_filtered(task_id="t_0003")
        assert len(results) == 1
        assert results[0].task_id == "t_0003"

    def test_filter_by_event_type(self, tmp_orch):
        _seed(tmp_orch, 3)
        append_event("orchestrator", "phase_declared",
                     data={"workflow_id": "wf_x",
                           "phases": [{"name": "dev", "order": 1, "required": True}]})
        results = read_events_filtered(event_type="phase_declared")
        assert len(results) == 1
        assert results[0].event_type == "phase_declared"

    def test_filter_by_phase(self, tmp_orch):
        _seed(tmp_orch, 3, phase="dev")
        _seed(tmp_orch, 2, phase="test")
        results = read_events_filtered(phase="test")
        assert len(results) == 2
        for e in results:
            assert e.data["phase"] == "test"

    def test_filters_are_and(self, tmp_orch):
        _seed(tmp_orch, 5)
        results = read_events_filtered(task_id="t_0002", event_type="task_created")
        assert len(results) == 1

        results = read_events_filtered(task_id="t_0002", event_type="task_completed")
        assert len(results) == 0

    def test_tail_returns_last_n(self, tmp_orch):
        _seed(tmp_orch, 10)
        results = read_events_filtered(tail=3)
        assert len(results) == 3
        assert results[0].seq == 8
        assert results[-1].seq == 10

    def test_tail_with_filter(self, tmp_orch):
        _seed(tmp_orch, 10)
        results = read_events_filtered(event_type="task_created", tail=4)
        assert len(results) == 4
        assert results[-1].seq == 10

    def test_from_seq_and_tail_combined(self, tmp_orch):
        _seed(tmp_orch, 10)
        results = read_events_filtered(from_seq=5, tail=2)
        assert len(results) == 2
        assert results[0].seq == 9
        assert results[1].seq == 10

    def test_no_filters_returns_all(self, tmp_orch):
        _seed(tmp_orch, 5)
        assert len(read_events_filtered()) == 5

    def test_tail_larger_than_results(self, tmp_orch):
        _seed(tmp_orch, 3)
        assert len(read_events_filtered(tail=100)) == 3
