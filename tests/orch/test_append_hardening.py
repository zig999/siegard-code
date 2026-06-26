"""
SIEGARD-03 — atomic log write + corrupted-tail hash guard.

Regression for the forensic package in temp/siegard-fixes/. Uses tmp_orch
(tests/orch/conftest.py) — the monkeypatch-based, NO-reload isolation that the
rest of tests/orch/ relies on (orch_dir would reload orch_core and break class
identity for sibling modules' pytest.raises checks).

- test_append_rejects_corrupted_tail : FAILS before the patch (silent append),
  PASSES once append_event guards the tail hash.
- test_concurrent_appends_stay_valid : LogLock serialization regression guard.
- test_log_has_no_torn_lines : every appended line is valid JSON.
"""
import json
import threading

import pytest
import orch_core


def _emit():
    # orchestrator_heartbeat carries a minimal schema ({"phase": ...}) — safe to spam.
    return orch_core.append_event(
        agent="test", event_type="orchestrator_heartbeat", data={"phase": "dev"}
    )


def test_append_rejects_corrupted_tail(tmp_orch):
    """Do not chain onto a corrupted tail — fail at append time, not on read."""
    _emit()
    _emit()

    # Corrupt the tail: keep valid JSON but falsify the `hash` field.
    lines = orch_core.LOG_PATH.read_text(encoding="utf-8").splitlines()
    tail = json.loads(lines[-1])
    tail["hash"] = "deadbeef" * 8
    lines[-1] = json.dumps(tail, sort_keys=True, separators=(",", ":"))
    orch_core.LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(orch_core.CorruptedLogError):
        _emit()


def test_concurrent_appends_stay_valid(tmp_orch):
    """N threads × M appends → contiguous seqs and an intact hash chain."""
    N, M = 8, 10
    errors: list[Exception] = []

    def run():
        for _ in range(M):
            try:
                _emit()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"append errors under concurrency: {errors[:3]}"

    events = list(orch_core.read_events())
    assert len(events) == N * M, "lost/duplicated events under concurrency"
    assert [e.seq for e in events] == list(range(1, N * M + 1)), "non-contiguous seqs"

    prev = "GENESIS"
    for e in events:
        assert e.prev_hash == prev, f"chain break at seq={e.seq}"
        assert e.compute_hash() == e.hash, f"invalid hash at seq={e.seq}"
        prev = e.hash


def test_log_has_no_torn_lines(tmp_orch):
    """Every log line is valid JSON after normal appends (no partial/torn line)."""
    for _ in range(5):
        _emit()
    for raw in orch_core.LOG_PATH.read_text(encoding="utf-8").splitlines():
        json.loads(raw)
