"""
Tests for Task 1.2: constants, paths, ensure_dirs, LogLock.
Covers scenarios: 8.3, 8.4
"""
import multiprocessing
import time
from pathlib import Path

import pytest
import orch_core
from orch_core import (
    ensure_dirs, LogLock, LockTimeoutError,
    ORCH_DIR, LOG_PATH, LOCK_PATH, STATE_DIR, DLQ_DIR,
    AUDIT_DIR, METRICS_DIR, BLOBS_DIR, CONFIG_PATH,
    MAX_INLINE_PAYLOAD, LOCK_TIMEOUT_S, SNAPSHOT_EVERY_N_EVENTS,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_inline_payload_limit(self):
        assert MAX_INLINE_PAYLOAD == 3500

    def test_lock_timeout(self):
        assert LOCK_TIMEOUT_S == 10.0

    def test_snapshot_threshold(self):
        assert SNAPSHOT_EVERY_N_EVENTS == 100


# ---------------------------------------------------------------------------
# ensure_dirs
# ---------------------------------------------------------------------------

class TestEnsureDirs:
    def test_creates_all_dirs(self, tmp_orch):
        for d in (orch_core.ORCH_DIR, orch_core.STATE_DIR, orch_core.DLQ_DIR,
                  orch_core.AUDIT_DIR, orch_core.METRICS_DIR, orch_core.BLOBS_DIR):
            assert d.exists(), f"Missing: {d}"
            assert d.is_dir()

    def test_idempotent(self, tmp_orch):
        """Running ensure_dirs twice must not raise."""
        orch_core.ensure_dirs()
        orch_core.ensure_dirs()


# ---------------------------------------------------------------------------
# LogLock — happy path
# ---------------------------------------------------------------------------

class TestLogLockHappyPath:
    def test_acquires_and_releases(self, tmp_orch):
        lock_path = orch_core.LOCK_PATH
        with LogLock(lock_path=lock_path):
            assert lock_path.exists()
        # After exit: should be acquirable again
        with LogLock(lock_path=lock_path):
            pass

    def test_lock_file_created(self, tmp_orch):
        with LogLock(lock_path=orch_core.LOCK_PATH):
            assert orch_core.LOCK_PATH.exists()

    def test_sequential_acquisition(self, tmp_orch):
        """Two sequential lock acquisitions must both succeed."""
        for _ in range(2):
            with LogLock(lock_path=orch_core.LOCK_PATH, timeout_s=1.0):
                pass


# ---------------------------------------------------------------------------
# Scenario 8.4: lock releases on exception
# ---------------------------------------------------------------------------

class TestLogLockReleasesOnException:
    def test_releases_on_exception(self, tmp_orch):
        """Scenario 8.4: lock must be released even when body raises."""
        lock_path = orch_core.LOCK_PATH

        with pytest.raises(RuntimeError, match="intentional"):
            with LogLock(lock_path=lock_path):
                raise RuntimeError("intentional error")

        # Lock must be free — next acquisition should succeed immediately
        with LogLock(lock_path=lock_path, timeout_s=1.0):
            pass

    def test_fd_closed_on_exception(self, tmp_orch):
        """Internal fd must not leak after exception."""
        lock = LogLock(lock_path=orch_core.LOCK_PATH)
        with pytest.raises(ValueError):
            with lock:
                raise ValueError("boom")
        assert lock._fd is None


# ---------------------------------------------------------------------------
# Scenario 8.3: lock timeout raises LockTimeoutError
# ---------------------------------------------------------------------------

def _hold_lock(lock_path: str, duration: float, ready_event, done_event) -> None:
    """Worker process: acquires lock, signals ready, holds until done."""
    import fcntl, os, time
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    ready_event.set()
    time.sleep(duration)
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
    done_event.set()


class TestLogLockTimeout:
    def test_timeout_raises_lock_timeout_error(self, tmp_orch):
        """Scenario 8.3: process B times out waiting for lock held by process A."""
        lock_path = str(orch_core.LOCK_PATH)
        ctx = multiprocessing.get_context("fork")
        ready = ctx.Event()
        done = ctx.Event()

        # Process A holds lock for 3 seconds; B times out after 0.3s
        proc = ctx.Process(target=_hold_lock, args=(lock_path, 3.0, ready, done))
        proc.start()
        ready.wait(timeout=5)  # wait until A has the lock

        with pytest.raises(LockTimeoutError):
            LogLock(lock_path=orch_core.LOCK_PATH, timeout_s=0.3).__enter__()

        proc.terminate()
        proc.join(timeout=2)

    def test_timeout_does_not_modify_log(self, tmp_orch):
        """Scenario 8.3: timed-out process must not write anything."""
        lock_path = str(orch_core.LOCK_PATH)
        ctx = multiprocessing.get_context("fork")
        ready = ctx.Event()
        done = ctx.Event()

        proc = ctx.Process(target=_hold_lock, args=(lock_path, 3.0, ready, done))
        proc.start()
        ready.wait(timeout=5)

        log_path = orch_core.LOG_PATH
        size_before = log_path.stat().st_size if log_path.exists() else 0

        with pytest.raises(LockTimeoutError):
            LogLock(lock_path=orch_core.LOCK_PATH, timeout_s=0.3).__enter__()

        size_after = log_path.stat().st_size if log_path.exists() else 0
        assert size_before == size_after

        proc.terminate()
        proc.join(timeout=2)

    def test_is_subclass_of_timeout_error(self):
        """LockTimeoutError must be a TimeoutError for standard except handling."""
        err = LockTimeoutError("test")
        assert isinstance(err, TimeoutError)
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# Concurrency: sequential seq numbers under concurrent appends
# ---------------------------------------------------------------------------

class TestLogLockConcurrency:

    def test_concurrent_appends_maintain_sequential_seqs(self, tmp_orch):
        """Multiple threads appending simultaneously must produce sequential, non-duplicate seqs."""
        import threading
        errors = []
        thread_count = 5
        events_per_thread = 4

        def append_events():
            try:
                for _ in range(events_per_thread):
                    orch_core.append_event("t", "orchestrator_heartbeat", data={})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=append_events, daemon=True) for _ in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert not errors, f"Thread errors: {errors}"

        events = list(orch_core.read_events())
        seqs = [e.seq for e in events]
        expected_count = thread_count * events_per_thread
        assert len(seqs) == expected_count
        assert sorted(seqs) == list(range(1, expected_count + 1)), "Seqs must be unique and sequential"
