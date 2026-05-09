"""
LogLock tests — acquire/release, timeout, and concurrent access.
"""
import threading
import time
from pathlib import Path

import pytest


class TestLogLockBasic:

    def test_acquire_and_release(self, orch_dir):
        import orch_core
        lock_path = orch_dir / ".orch" / "log.jsonl.lock"
        with orch_core.LogLock(lock_path=lock_path, timeout_s=2.0):
            assert True  # acquired without error

    def test_releases_on_exit_even_if_exception(self, orch_dir):
        import orch_core
        lock_path = orch_dir / ".orch" / "log.jsonl.lock"
        try:
            with orch_core.LogLock(lock_path=lock_path, timeout_s=2.0):
                raise ValueError("simulated error inside lock")
        except ValueError:
            pass
        # Lock must be free — acquire again succeeds
        with orch_core.LogLock(lock_path=lock_path, timeout_s=2.0):
            assert True

    def test_reentrant_acquire_times_out(self, orch_dir):
        """Acquiring a held lock from the same process times out because flock
        is per file-descriptor, not per process — two separate fd's block each other."""
        import orch_core
        lock_path = orch_dir / ".orch" / "log.jsonl.lock"
        acquired = threading.Event()
        released = threading.Event()

        def hold_lock():
            with orch_core.LogLock(lock_path=lock_path, timeout_s=5.0):
                acquired.set()
                released.wait(timeout=3.0)

        t = threading.Thread(target=hold_lock, daemon=True)
        t.start()
        acquired.wait(timeout=2.0)

        # Second lock attempt should time out while first thread holds it
        with pytest.raises(orch_core.LockTimeoutError):
            orch_core.LogLock(lock_path=lock_path, timeout_s=0.2).__enter__()

        released.set()
        t.join(timeout=2.0)


class TestLogLockConcurrency:

    def test_concurrent_appends_maintain_sequential_seqs(self, orch_dir):
        """Multiple threads appending simultaneously must produce sequential, non-duplicate seqs."""
        import orch_core

        errors = []
        thread_count = 5
        events_per_thread = 4

        def append_events():
            try:
                for _ in range(events_per_thread):
                    orch_core.append_event(
                        "t",
                        "orchestrator_heartbeat",
                        data={},
                    )
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
