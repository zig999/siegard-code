"""
Tests for Task 1.3: append_event with hash chain.
Covers scenarios: 1.1, 1.2, 1.3 (partial), 1.4 (partial), 1.8, 1.9
"""
import json

import pytest
import orch_core
from orch_core import (
    append_event, Event,
    EventValidationError, UnknownEventType,
    LOG_PATH,
)


def _task_data(**kwargs) -> dict:
    base = {"phase": "dev", "tier": "standard", "type": "impl",
            "spec": "do something", "deps": []}
    base.update(kwargs)
    return base


def _phase_data(**kwargs) -> dict:
    base = {"workflow_id": "wf_test",
            "phases": [{"name": "dev", "order": 1, "required": True}]}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Scenario 1.1: first event in empty log
# ---------------------------------------------------------------------------

class TestFirstEvent:
    def test_seq_is_one(self, tmp_orch):
        e = append_event("orchestrator", "task_created",
                         task_id="t_0001", data=_task_data())
        assert e.seq == 1

    def test_prev_hash_is_genesis(self, tmp_orch):
        e = append_event("orchestrator", "task_created",
                         task_id="t_0001", data=_task_data())
        assert e.prev_hash == "GENESIS"

    def test_hash_computed_correctly(self, tmp_orch):
        e = append_event("orchestrator", "task_created",
                         task_id="t_0001", data=_task_data())
        assert e.hash == e.compute_hash()
        assert len(e.hash) == 64

    def test_event_id_format(self, tmp_orch):
        import re
        e = append_event("orchestrator", "task_created",
                         task_id="t_0001", data=_task_data())
        assert re.match(r"^evt_[0-9A-HJKMNP-TV-Z]{26}$", e.event_id)

    def test_ts_format(self, tmp_orch):
        import re
        e = append_event("orchestrator", "task_created",
                         task_id="t_0001", data=_task_data())
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", e.ts)

    def test_log_contains_one_line(self, tmp_orch):
        append_event("orchestrator", "task_created",
                     task_id="t_0001", data=_task_data())
        lines = orch_core.LOG_PATH.read_text().splitlines()
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# Scenario 1.2: monotonic seq and chained prev_hash
# ---------------------------------------------------------------------------

class TestSequentialEvents:
    def test_seq_monotonic(self, tmp_orch):
        events = [
            append_event("orchestrator", "task_created",
                         task_id=f"t_{i:04d}", data=_task_data())
            for i in range(1, 4)
        ]
        assert [e.seq for e in events] == [1, 2, 3]

    def test_prev_hash_chain(self, tmp_orch):
        e1 = append_event("orchestrator", "task_created",
                          task_id="t_0001", data=_task_data())
        e2 = append_event("orchestrator", "task_created",
                          task_id="t_0002", data=_task_data())
        e3 = append_event("orchestrator", "task_created",
                          task_id="t_0003", data=_task_data())

        assert e2.prev_hash == e1.hash
        assert e3.prev_hash == e2.hash

    def test_all_event_ids_unique(self, tmp_orch):
        events = [
            append_event("orchestrator", "task_created",
                         task_id=f"t_{i:04d}", data=_task_data())
            for i in range(1, 101)
        ]
        ids = [e.event_id for e in events]
        assert len(set(ids)) == 100


# ---------------------------------------------------------------------------
# Serialization and file format
# ---------------------------------------------------------------------------

class TestSerializationFormat:
    def test_written_line_is_valid_json(self, tmp_orch):
        append_event("orchestrator", "task_created",
                     task_id="t_0001", data=_task_data())
        raw = orch_core.LOG_PATH.read_bytes()
        assert raw.endswith(b"\n")
        parsed = json.loads(raw.decode("utf-8").strip())
        assert isinstance(parsed, dict)

    def test_written_event_round_trips(self, tmp_orch):
        e = append_event("orchestrator", "task_created",
                         task_id="t_0001", data=_task_data())
        raw = orch_core.LOG_PATH.read_text().strip()
        recovered = Event.from_dict(json.loads(raw))
        assert recovered.seq == e.seq
        assert recovered.hash == e.hash
        assert recovered.prev_hash == e.prev_hash

    def test_multiple_events_one_line_each(self, tmp_orch):
        for i in range(1, 4):
            append_event("orchestrator", "task_created",
                         task_id=f"t_{i:04d}", data=_task_data())
        lines = [l for l in orch_core.LOG_PATH.read_text().splitlines() if l.strip()]
        assert len(lines) == 3
        for line in lines:
            assert json.loads(line)  # each line is valid JSON

    def test_uses_append_mode(self, tmp_orch):
        """File must grow monotonically — never truncated."""
        e1 = append_event("orchestrator", "task_created",
                          task_id="t_0001", data=_task_data())
        size_after_1 = orch_core.LOG_PATH.stat().st_size
        e2 = append_event("orchestrator", "task_created",
                          task_id="t_0002", data=_task_data())
        size_after_2 = orch_core.LOG_PATH.stat().st_size
        assert size_after_2 > size_after_1


# ---------------------------------------------------------------------------
# Scenario 1.8: unknown event_type rejected
# ---------------------------------------------------------------------------

class TestUnknownEventType:
    def test_raises_unknown_event_type(self, tmp_orch):
        with pytest.raises(UnknownEventType):
            append_event("orchestrator", "invalid_event_type", data={})

    def test_nothing_written_on_unknown_type(self, tmp_orch):
        with pytest.raises(UnknownEventType):
            append_event("orchestrator", "bad_type", data={})
        assert not orch_core.LOG_PATH.exists() or orch_core.LOG_PATH.stat().st_size == 0

    def test_empty_string_rejected(self, tmp_orch):
        with pytest.raises(UnknownEventType):
            append_event("orchestrator", "", data={})


# ---------------------------------------------------------------------------
# Scenario 1.9: `phase` required in task_created
# ---------------------------------------------------------------------------

class TestRequiredDataFields:
    def test_task_created_missing_phase_raises(self, tmp_orch):
        with pytest.raises(EventValidationError, match="phase"):
            append_event("orchestrator", "task_created", task_id="t_0001",
                         data={"tier": "standard", "type": "impl",
                               "spec": "x", "deps": []})

    def test_nothing_written_on_validation_error(self, tmp_orch):
        with pytest.raises(EventValidationError):
            append_event("orchestrator", "task_created", task_id="t_0001",
                         data={"tier": "standard"})
        assert not orch_core.LOG_PATH.exists() or orch_core.LOG_PATH.stat().st_size == 0

    def test_task_created_missing_tier_raises(self, tmp_orch):
        with pytest.raises(EventValidationError, match="tier"):
            append_event("orchestrator", "task_created", task_id="t_0001",
                         data={"phase": "dev", "type": "impl", "spec": "x", "deps": []})

    def test_task_completed_missing_artifacts_raises(self, tmp_orch):
        with pytest.raises(EventValidationError, match="artifacts"):
            append_event("worker-code-writer-1", "task_completed",
                         task_id="t_0001", data={"phase": "dev", "summary": "done"})

    def test_task_failed_missing_retryable_raises(self, tmp_orch):
        with pytest.raises(EventValidationError, match="retryable"):
            append_event("worker-code-writer-1", "task_failed",
                         task_id="t_0001", data={"phase": "dev", "reason": "oops"})

    def test_task_failed_invalid_reason_raises(self, tmp_orch):
        """task_failed with an invalid reason enum value must raise EventValidationError."""
        with pytest.raises(EventValidationError):
            append_event("worker-code-writer-1", "task_failed",
                         task_id="t_0001",
                         data={"phase": "dev", "reason": "bad_custom_reason", "retryable": False})

    def test_global_events_do_not_require_phase(self, tmp_orch):
        """phase_declared is a global event — no task-level phase field required."""
        e = append_event("orchestrator", "phase_declared",
                         data=_phase_data())
        assert e.seq == 1

    def test_valid_task_created_succeeds(self, tmp_orch):
        e = append_event("orchestrator", "task_created",
                         task_id="t_0001", data=_task_data())
        assert e.event_type == "task_created"


# ---------------------------------------------------------------------------
# Lock released on exception during write
# ---------------------------------------------------------------------------

class TestLockReleasedOnError:
    def test_subsequent_write_succeeds_after_error(self, tmp_orch):
        """If append raises internally, lock must be released so next call works."""
        from unittest.mock import patch

        call_count = 0
        real_open = __builtins__["open"] if isinstance(__builtins__, dict) else open

        def patched_open(path, mode="r", *args, **kwargs):
            nonlocal call_count
            if "ab" in str(mode):
                call_count += 1
                if call_count == 1:
                    raise OSError("simulated disk error")
            return real_open(path, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=patched_open):
            with pytest.raises(OSError, match="simulated disk error"):
                append_event("orchestrator", "task_created",
                             task_id="t_0001", data=_task_data())

        # patch is gone — paths still redirected by tmp_orch; next call must succeed
        e = append_event("orchestrator", "task_created",
                         task_id="t_0001", data=_task_data())
        assert e.seq == 1
