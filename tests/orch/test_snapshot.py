"""Task 1.8 — state snapshot cache + verified-prefix verify cache.

Contract under test:
  - reduce_all() with a valid snapshot replays ONLY the tail (mechanical
    proof: an early corrupted line is never read) and produces a state
    IDENTICAL to the full replay.
  - Every cache anomaly (tampered hash, engine change, truncated log,
    corrupt JSON, ORCH_SNAPSHOT=0) silently falls back to the full replay.
  - verify_chain_cached() is strict-mode-equivalent: happy path re-hashes
    only the tail; every anomaly defers to the canonical full verify.
The snapshot is a disposable derived cache (P1): deleting it is always safe.
"""
import json

import pytest

import orch_core


THRESHOLD = orch_core.SNAPSHOT_EVERY_N_EVENTS  # 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bulk_events(make_event, n: int, prefix: str = "t") -> None:
    """Append n legal events fast: unique task_created per event."""
    for i in range(n):
        make_event(
            "task_created", task_id=f"{prefix}_{i:04d}",
            data={"phase": "dev", "tier": "standard", "type": "impl",
                  "spec": f"do {i}", "deps": []},
        )


def _declare_phase(make_event) -> None:
    make_event("phase_declared", data={
        "workflow_id": "wf-snap",
        "phases": [{"name": "dev", "order": 1, "required": True}],
    })
    make_event("phase_entered", data={"phase": "dev", "order": 1,
                                      "workflow_id": "wf-snap"})


def _full_reduce_dict(monkeypatch) -> dict:
    """Ground truth: reduce with the snapshot cache disabled."""
    monkeypatch.setenv("ORCH_SNAPSHOT", "0")
    try:
        return orch_core.reduce_all().to_dict()
    finally:
        monkeypatch.delenv("ORCH_SNAPSHOT", raising=False)


def _snapshot_file():
    return orch_core.STATE_DIR / "snapshot.json"


def _corrupt_line_in_place(line_no: int) -> None:
    """Overwrite log line `line_no` (0-based) with same-length garbage —
    offsets of every other line stay stable."""
    raw = orch_core.LOG_PATH.read_bytes()
    lines = raw.split(b"\n")
    lines[line_no] = b"X" * len(lines[line_no])
    orch_core.LOG_PATH.write_bytes(b"\n".join(lines))


# ---------------------------------------------------------------------------
# Round-trip fidelity
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_rich_state_roundtrips_exactly(self, orch_dir, make_event):
        _declare_phase(make_event)
        _bulk_events(make_event, 3)
        make_event("task_claimed", task_id="t_0000",
                   data={"phase": "dev", "worker_id": "w1", "worker_type": "impl"})
        make_event("task_completed", task_id="t_0000",
                   data={"phase": "dev", "artifacts": ["a.md"]})
        make_event("task_claimed", task_id="t_0001",
                   data={"phase": "dev", "worker_id": "w2", "worker_type": "impl"})
        make_event("task_failed", task_id="t_0001",
                   data={"phase": "dev", "reason": "internal_error",
                         "retryable": True})
        state = orch_core.reduce_all()
        rebuilt = orch_core.OrchState.from_dict(state.to_dict())
        assert rebuilt.to_dict() == state.to_dict()


# ---------------------------------------------------------------------------
# Snapshot write policy
# ---------------------------------------------------------------------------

class TestSnapshotWrite:
    def test_not_written_below_threshold(self, orch_dir, make_event):
        _declare_phase(make_event)
        _bulk_events(make_event, 10)
        orch_core.reduce_all()
        assert not _snapshot_file().exists()

    def test_written_after_threshold(self, orch_dir, make_event):
        _declare_phase(make_event)
        _bulk_events(make_event, THRESHOLD + 5)
        state = orch_core.reduce_all()
        snap_path = _snapshot_file()
        assert snap_path.exists()
        snap = json.loads(snap_path.read_text())
        assert snap["seq"] == state.last_seq
        assert snap["engine_rev"] == orch_core._engine_rev()
        assert snap["state"] == state.to_dict()

    def test_kill_switch_disables_write(self, orch_dir, make_event, monkeypatch):
        monkeypatch.setenv("ORCH_SNAPSHOT", "0")
        _declare_phase(make_event)
        _bulk_events(make_event, THRESHOLD + 5)
        orch_core.reduce_all()
        assert not _snapshot_file().exists()


# ---------------------------------------------------------------------------
# Equivalence — snapshot path == full path, always
# ---------------------------------------------------------------------------

class TestEquivalence:
    def test_snapshot_reduce_equals_full_reduce(self, orch_dir, make_event,
                                                monkeypatch):
        _declare_phase(make_event)
        _bulk_events(make_event, THRESHOLD + 5)
        orch_core.reduce_all()  # primes the snapshot
        assert _snapshot_file().exists()
        # grow a tail past the snapshot, including task transitions
        _bulk_events(make_event, 20, prefix="tail")
        make_event("task_claimed", task_id="tail_0000",
                   data={"phase": "dev", "worker_id": "w9", "worker_type": "impl"})
        make_event("task_completed", task_id="tail_0000",
                   data={"phase": "dev", "artifacts": []})
        snapshot_view = orch_core.reduce_all().to_dict()
        assert snapshot_view == _full_reduce_dict(monkeypatch)

    def test_empty_tail_equals_full(self, orch_dir, make_event, monkeypatch):
        _declare_phase(make_event)
        _bulk_events(make_event, THRESHOLD + 5)
        orch_core.reduce_all()
        # no new events: snapshot boundary == last event
        assert orch_core.reduce_all().to_dict() == _full_reduce_dict(monkeypatch)


# ---------------------------------------------------------------------------
# Mechanical proof of O(tail): the snapshot path never reads the prefix
# ---------------------------------------------------------------------------

class TestTailOnlyReplay:
    def test_early_corruption_invisible_to_snapshot_path(self, orch_dir,
                                                         make_event):
        _declare_phase(make_event)
        _bulk_events(make_event, THRESHOLD + 5)
        clean_state = orch_core.reduce_all()          # primes snapshot
        _bulk_events(make_event, 5, prefix="tail")
        _corrupt_line_in_place(4)                     # deep in the prefix
        # Full replay must reject the corrupted log...
        with pytest.raises(orch_core.CorruptedLogError):
            list(orch_core.read_events())
        # ...while the snapshot path never touches that byte range.
        state = orch_core.reduce_all()
        assert state.last_seq == clean_state.last_seq + 5


# ---------------------------------------------------------------------------
# Invalidation — every anomaly falls back to the full replay
# ---------------------------------------------------------------------------

class TestInvalidation:
    def _prime(self, make_event) -> None:
        _declare_phase(make_event)
        _bulk_events(make_event, THRESHOLD + 5)
        orch_core.reduce_all()
        assert _snapshot_file().exists()

    def _tamper(self, **overrides) -> None:
        snap = json.loads(_snapshot_file().read_text())
        snap.update(overrides)
        _snapshot_file().write_text(json.dumps(snap))

    def test_tampered_event_hash_falls_back(self, orch_dir, make_event,
                                            monkeypatch):
        self._prime(make_event)
        self._tamper(event_hash="0" * 64)
        assert orch_core.reduce_all().to_dict() == _full_reduce_dict(monkeypatch)

    def test_engine_rev_change_falls_back(self, orch_dir, make_event,
                                          monkeypatch):
        self._prime(make_event)
        self._tamper(engine_rev="deadbeefdeadbeef")
        assert orch_core.reduce_all().to_dict() == _full_reduce_dict(monkeypatch)

    def test_boundary_beyond_eof_falls_back(self, orch_dir, make_event,
                                            monkeypatch):
        self._prime(make_event)
        self._tamper(boundary_offset=orch_core.LOG_PATH.stat().st_size + 999)
        assert orch_core.reduce_all().to_dict() == _full_reduce_dict(monkeypatch)

    def test_corrupt_snapshot_json_falls_back(self, orch_dir, make_event,
                                              monkeypatch):
        self._prime(make_event)
        _snapshot_file().write_text("{not json")
        assert orch_core.reduce_all().to_dict() == _full_reduce_dict(monkeypatch)

    def test_log_truncation_falls_back(self, orch_dir, make_event, monkeypatch):
        """Recovery truncates the log → snapshot points past EOF → full replay
        of the shorter log, no stale state leaks."""
        self._prime(make_event)
        raw_lines = orch_core.LOG_PATH.read_bytes().splitlines()
        keep = raw_lines[: THRESHOLD // 2]
        orch_core.LOG_PATH.write_bytes(b"\n".join(keep) + b"\n")
        state = orch_core.reduce_all()
        assert state.to_dict() == _full_reduce_dict(monkeypatch)
        assert state.last_seq <= THRESHOLD // 2

    def test_deleting_snapshot_is_always_safe(self, orch_dir, make_event,
                                              monkeypatch):
        self._prime(make_event)
        _snapshot_file().unlink()
        assert orch_core.reduce_all().to_dict() == _full_reduce_dict(monkeypatch)


# ---------------------------------------------------------------------------
# verify_chain_cached — strict-equivalent, tail-only happy path
# ---------------------------------------------------------------------------

class TestVerifyCached:
    def _cache_file(self):
        return orch_core.STATE_DIR / "verify_cache.json"

    def test_clean_log_ok_and_cache_written(self, orch_dir, make_event):
        _declare_phase(make_event)
        _bulk_events(make_event, 30)
        full = orch_core.verify_chain(mode="strict")
        cached = orch_core.verify_chain_cached()
        assert cached.ok is True
        assert cached.events_verified == full.events_verified
        assert self._cache_file().exists()

    def test_incremental_counts_whole_chain(self, orch_dir, make_event):
        _declare_phase(make_event)
        _bulk_events(make_event, 30)
        orch_core.verify_chain_cached()               # primes cache
        _bulk_events(make_event, 10, prefix="tail")
        cached = orch_core.verify_chain_cached()      # verifies only the tail
        assert cached.ok is True
        assert cached.events_verified == \
            orch_core.verify_chain(mode="strict").events_verified

    def test_tampered_tail_detected_with_authoritative_report(
            self, orch_dir, make_event):
        _declare_phase(make_event)
        _bulk_events(make_event, 30)
        orch_core.verify_chain_cached()
        _bulk_events(make_event, 10, prefix="tail")
        _corrupt_line_in_place(35)                    # inside the new tail
        result = orch_core.verify_chain_cached()
        assert result.ok is False                     # deferred to full verify

    def test_tampered_old_boundary_falls_back_to_full(self, orch_dir,
                                                      make_event):
        """Corrupt the CACHED boundary line after the log has grown past it:
        the boundary re-read mismatches → canonical full verify → the now
        mid-log corruption is detected. (Corrupting the very LAST line is a
        different case — indistinguishable from a torn write and tolerated,
        by verify_chain's own semantics.)"""
        _declare_phase(make_event)
        _bulk_events(make_event, 30)
        orch_core.verify_chain_cached()               # boundary = line 31
        old_boundary = len(orch_core.LOG_PATH.read_bytes().splitlines()) - 1
        _bulk_events(make_event, 10, prefix="tail")   # boundary now mid-log
        _corrupt_line_in_place(old_boundary)
        result = orch_core.verify_chain_cached()
        assert result.ok is False

    def test_kill_switch_bypasses_cache(self, orch_dir, make_event, monkeypatch):
        monkeypatch.setenv("ORCH_SNAPSHOT", "0")
        _declare_phase(make_event)
        _bulk_events(make_event, 10)
        result = orch_core.verify_chain_cached()
        assert result.ok is True
        assert not self._cache_file().exists()

    def test_truncated_log_after_cache_recovers(self, orch_dir, make_event):
        _declare_phase(make_event)
        _bulk_events(make_event, 30)
        orch_core.verify_chain_cached()
        raw_lines = orch_core.LOG_PATH.read_bytes().splitlines()
        orch_core.LOG_PATH.write_bytes(b"\n".join(raw_lines[:10]) + b"\n")
        result = orch_core.verify_chain_cached()      # boundary past EOF → full
        assert result.ok is True
        assert result.events_verified == 10
