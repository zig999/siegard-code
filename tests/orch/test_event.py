"""
Tests for Task 1.1: Event dataclass, enums, and helpers.
Covers scenarios: 1.1 (partial), 2.5, 2.6
"""
import re
import pytest
from orch_core import (
    Event, EventType, TaskStatus, PhaseStatus, Tier,
    new_event_id, now_iso, parse_iso, sha256_hex, canonical_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestNewEventId:
    def test_prefix(self):
        assert new_event_id().startswith("evt_")

    def test_length(self):
        eid = new_event_id()
        assert len(eid) == 30  # "evt_" (4) + 26 chars

    def test_pattern(self):
        pattern = re.compile(r"^evt_[0-9A-HJKMNP-TV-Z]{26}$")
        for _ in range(20):
            assert pattern.match(new_event_id()), "event_id must match ULID-like pattern"

    def test_uniqueness(self):
        ids = [new_event_id() for _ in range(100)]
        assert len(set(ids)) == 100, "event_ids must be unique"

    def test_no_invalid_chars(self):
        # ULID alphabet excludes I, L, O, U
        for _ in range(50):
            eid = new_event_id()[4:]  # strip evt_
            for ch in "ILOU":
                assert ch not in eid


class TestNowIso:
    def test_format(self):
        ts = now_iso()
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
        assert pattern.match(ts), f"Unexpected format: {ts}"

    def test_utc(self):
        ts = now_iso()
        assert ts.endswith("Z")

    def test_parseable(self):
        ts = now_iso()
        dt = parse_iso(ts)
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# EventType enum
# ---------------------------------------------------------------------------

class TestEventType:
    def test_total_count(self):
        assert len(EventType) == 33  # +handoff_receipt (08) +suite_run_started/completed (11) +orchestrator_resume_requested/resumed (E2) +cost_projected (R11a)

    def test_task_lifecycle_count(self):
        task_types = [e for e in EventType if e.value.startswith("task_")]
        assert len(task_types) == 9

    def test_phase_lifecycle_count(self):
        phase_types = [e for e in EventType if e.value.startswith("phase_")]
        assert len(phase_types) == 7

    def test_is_worker_emittable_exact_three(self):
        emittable = [e for e in EventType if EventType.is_worker_emittable(e.value)]
        assert len(emittable) == 3

    def test_is_worker_emittable_correct_types(self):
        assert EventType.is_worker_emittable("task_progress")
        assert EventType.is_worker_emittable("task_completed")
        assert EventType.is_worker_emittable("task_failed")

    def test_is_worker_emittable_rejects_orchestrator_types(self):
        assert not EventType.is_worker_emittable("task_created")
        assert not EventType.is_worker_emittable("task_claimed")
        assert not EventType.is_worker_emittable("task_dlq")
        assert not EventType.is_worker_emittable("phase_declared")
        assert not EventType.is_worker_emittable("escalation")

    def test_is_terminal_for_attempt(self):
        assert EventType.is_terminal_for_attempt("task_completed")
        assert EventType.is_terminal_for_attempt("task_failed")
        assert not EventType.is_terminal_for_attempt("task_progress")
        assert not EventType.is_terminal_for_attempt("task_claimed")

    def test_values_set(self):
        values = EventType.values()
        assert "task_created" in values
        assert "phase_declared" in values
        assert "handoff_receipt" in values   # prod-hardening task 08
        assert "suite_run_started" in values  # prod-hardening task 11
        assert "orchestrator_resume_requested" in values  # E2 supervised auto-resume
        assert "orchestrator_resumed" in values           # E2 supervised auto-resume
        assert "cost_projected" in values                  # R11a — audit-only cost projection
        assert len(values) == 33


# ---------------------------------------------------------------------------
# Tier enum
# ---------------------------------------------------------------------------

class TestTier:
    def test_default_max_attempts(self):
        assert Tier.CRITICAL.default_max_attempts == 5
        assert Tier.STANDARD.default_max_attempts == 3
        assert Tier.BULK.default_max_attempts == 1

    def test_default_stale_seconds(self):
        assert Tier.CRITICAL.default_stale_seconds == 600
        assert Tier.STANDARD.default_stale_seconds == 300
        assert Tier.BULK.default_stale_seconds == 120

    def test_default_base_delay(self):
        assert Tier.CRITICAL.default_base_delay_s == 15.0
        assert Tier.STANDARD.default_base_delay_s == 30.0
        assert Tier.BULK.default_base_delay_s == 0.0


# ---------------------------------------------------------------------------
# TaskStatus
# ---------------------------------------------------------------------------

class TestTaskStatus:
    def test_terminal_states(self):
        assert TaskStatus.is_terminal("completed")
        assert TaskStatus.is_terminal("dlq")

    def test_cancelled_not_terminal_yet(self):
        # CANCELLED exists in the enum but no handler produces it yet (reserved).
        assert not TaskStatus.is_terminal("cancelled")

    def test_non_terminal_states(self):
        for s in ("pending", "ready", "running", "scheduled", "failed"):
            assert not TaskStatus.is_terminal(s)


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

def make_event(**kwargs) -> Event:
    defaults = dict(
        seq=1,
        event_id=new_event_id(),
        ts=now_iso(),
        agent="orchestrator",
        event_type="task_created",
        task_id="t_0001",
        attempt=1,
        data={"phase": "dev", "tier": "standard", "type": "impl", "spec": "x", "deps": []},
        prev_hash="GENESIS",
        hash="",
    )
    defaults.update(kwargs)
    return Event(**defaults)


class TestEventToDict:
    def test_round_trip(self):
        """to_dict and from_dict are inverses."""
        e = make_event()
        e.hash = e.compute_hash()
        d = e.to_dict()
        e2 = Event.from_dict(d)
        assert e2.to_dict() == d

    def test_all_fields_present(self):
        e = make_event()
        d = e.to_dict()
        expected = {"seq", "event_id", "ts", "agent", "event_type",
                    "task_id", "attempt", "data", "prev_hash", "hash"}
        assert set(d.keys()) == expected

    def test_task_id_null(self):
        e = make_event(task_id=None, event_type="phase_declared",
                       data={"workflow_id": "wf_test", "phases": []})
        d = e.to_dict()
        assert d["task_id"] is None
        e2 = Event.from_dict(d)
        assert e2.task_id is None


class TestEventHash:
    def test_compute_hash_excludes_hash_field(self):
        """Scenario 2.6: hash field is excluded from computation."""
        e = make_event(hash="original_value")
        h1 = e.compute_hash()

        e.hash = "completely_different_value"
        h2 = e.compute_hash()

        assert h1 == h2

    def test_hash_field_not_in_canonical(self):
        """Scenario 2.6: canonical_json must not contain 'hash' key."""
        e = make_event(hash="xyz")
        cj = e.canonical_json()
        parsed = json.loads(cj)
        assert "hash" not in parsed

    def test_canonical_json_deterministic_data_order(self):
        """Scenario 2.5: same event data in different order → same hash."""
        e1 = make_event(data={"b": 2, "a": 1, "phase": "dev",
                               "tier": "standard", "type": "impl",
                               "spec": "x", "deps": []})
        e2 = make_event(
            seq=e1.seq, event_id=e1.event_id, ts=e1.ts,
            data={"a": 1, "b": 2, "phase": "dev",
                  "tier": "standard", "type": "impl",
                  "spec": "x", "deps": []},
        )
        assert e1.compute_hash() == e2.compute_hash()

    def test_hash_changes_when_data_changes(self):
        e1 = make_event(data={"phase": "dev", "tier": "standard",
                               "type": "impl", "spec": "original", "deps": []})
        e2 = make_event(data={"phase": "dev", "tier": "standard",
                               "type": "impl", "spec": "modified", "deps": []})
        assert e1.compute_hash() != e2.compute_hash()

    def test_hash_is_64_hex_chars(self):
        e = make_event()
        h = e.compute_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_stable_across_calls(self):
        e = make_event()
        assert e.compute_hash() == e.compute_hash()


import json  # noqa: E402 (needed inside test methods above)
