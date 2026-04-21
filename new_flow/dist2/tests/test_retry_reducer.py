"""Tests for Task 4.2 — reducer integration for task_scheduled_retry and task_retried.

Covers scenarios 3.10, 3.11, and retry decision criteria (4.5, 4.6 covered in test_retry.py).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).parents[1] / ".claude" / "lib"
SKILLS_DIR = Path(__file__).parents[1] / ".claude" / "skills"
APPEND = str(SKILLS_DIR / "orch-log" / "scripts" / "append.py")
EMIT = str(SKILLS_DIR / "orch-report" / "scripts" / "emit.py")

sys.path.insert(0, str(LIB))

from orch_core import (
    OrchState,
    RetryPolicy,
    TaskState,
    TaskStatus,
    Tier,
    apply_event,
    backoff_seconds,
    default_config,
    load_retry_policy,
    now_iso,
    parse_iso,
    reduce_all,
    should_retry,
    tasks_ready_for_retry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _append(cwd, agent, event_type, task_id=None, attempt=1, data=None):
    cmd = [
        sys.executable, APPEND,
        "--agent", agent,
        "--event-type", event_type,
        "--attempt", str(attempt),
        "--data", json.dumps(data or {}),
    ]
    if task_id:
        cmd += ["--task-id", task_id]
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _emit(cwd, worker_id, kind, task_id, attempt=1, data=None):
    env = {"ORCH_WORKER_ID": worker_id, "PATH": "/usr/bin:/bin"}
    r = subprocess.run(
        [sys.executable, EMIT, "--kind", kind, "--task-id", task_id,
         "--attempt", str(attempt), "--data", json.dumps(data or {})],
        cwd=str(cwd), capture_output=True, text=True, env=env
    )
    assert r.returncode == 0, r.stderr


def _bootstrap(cwd, task_id="t_001", tier="standard", task_type="impl"):
    """Bootstrap a single task to READY state."""
    _append(cwd, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_test", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(cwd, "orchestrator", "phase_entered", data={"phase": "default", "order": 1})
    _append(cwd, "orchestrator", "task_created", task_id,
            data={"phase": "default", "deps": [], "tier": tier, "type": task_type, "spec": "x"})
    return _append(cwd, "orchestrator", "task_claimed", task_id,
                   data={"phase": "default", "worker_type": "test-worker", "worker_id": "w1"})


def _state(cwd) -> OrchState:
    import os
    old = os.getcwd()
    os.chdir(str(cwd))
    try:
        return reduce_all()
    finally:
        os.chdir(old)


# ---------------------------------------------------------------------------
# Scenario 3.10 — task_scheduled_retry moves failed → scheduled
# ---------------------------------------------------------------------------

class TestTaskScheduledRetry:
    def test_failed_to_scheduled(self, tmp_path):
        """Scenario 3.10: task_scheduled_retry on a failed task sets status=scheduled."""
        _bootstrap(tmp_path)
        _emit(tmp_path, "w1", "failed", "t_001",
              data={"phase": "default", "reason": "transient_error", "retryable": True})

        s = _state(tmp_path)
        assert s.tasks["t_001"].status == TaskStatus.FAILED

        evt = _append(tmp_path, "orchestrator", "task_scheduled_retry", "t_001",
                      data={
                          "phase": "default",
                          "next_retry_at": "2099-01-01T00:00:00+00:00",
                          "backoff_seconds": 45.0,
                          "previous_failure_seq": s.tasks["t_001"].evidence[-1],
                      })

        s2 = _state(tmp_path)
        assert s2.tasks["t_001"].status == TaskStatus.SCHEDULED
        assert s2.tasks["t_001"].next_retry_at == "2099-01-01T00:00:00+00:00"

    def test_scheduled_retry_sets_next_retry_at(self, tmp_path):
        _bootstrap(tmp_path)
        _emit(tmp_path, "w1", "failed", "t_001",
              data={"phase": "default", "reason": "err", "retryable": True})

        _append(tmp_path, "orchestrator", "task_scheduled_retry", "t_001",
                data={
                    "phase": "default",
                    "next_retry_at": "2030-06-15T12:00:00+00:00",
                    "backoff_seconds": 30.0,
                    "previous_failure_seq": 1,
                })

        s = _state(tmp_path)
        assert s.tasks["t_001"].next_retry_at == "2030-06-15T12:00:00+00:00"

    def test_scheduled_retry_on_non_failed_raises(self, tmp_path):
        """Cannot apply task_scheduled_retry to a task that is not in failed status."""
        _bootstrap(tmp_path)
        # task is currently RUNNING (claimed, not failed yet)
        s = _state(tmp_path)
        assert s.tasks["t_001"].status == TaskStatus.RUNNING

        # Attempt to emit task_scheduled_retry directly to a running task
        r = subprocess.run(
            [sys.executable, APPEND,
             "--agent", "orchestrator",
             "--event-type", "task_scheduled_retry",
             "--task-id", "t_001",
             "--attempt", "1",
             "--data", json.dumps({
                 "phase": "default",
                 "next_retry_at": "2099-01-01T00:00:00+00:00",
                 "backoff_seconds": 30.0,
                 "previous_failure_seq": 1,
             })],
            cwd=str(tmp_path), capture_output=True, text=True
        )
        # append.py writes the event regardless; the illegality is at reduce time.
        # reduce_all() should raise IllegalTransition when processing this sequence.
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            from orch_core import IllegalTransition
            with pytest.raises(IllegalTransition):
                reduce_all()
        finally:
            os.chdir(old)


# ---------------------------------------------------------------------------
# Scenario 3.11 — task_retried moves scheduled → pending/ready
# ---------------------------------------------------------------------------

class TestTaskRetried:
    def test_scheduled_to_ready_no_deps(self, tmp_path):
        """Scenario 3.11: task_retried on scheduled task with no deps → ready."""
        _bootstrap(tmp_path)
        _emit(tmp_path, "w1", "failed", "t_001",
              data={"phase": "default", "reason": "err", "retryable": True})
        _append(tmp_path, "orchestrator", "task_scheduled_retry", "t_001",
                data={
                    "phase": "default",
                    "next_retry_at": "2000-01-01T00:00:00+00:00",
                    "backoff_seconds": 1.0,
                    "previous_failure_seq": 1,
                })

        s = _state(tmp_path)
        assert s.tasks["t_001"].status == TaskStatus.SCHEDULED
        scheduled_seq = s.tasks["t_001"].evidence[-1]

        _append(tmp_path, "orchestrator", "task_retried", "t_001", attempt=2,
                data={
                    "phase": "default",
                    "previous_attempt": 1,
                    "scheduled_retry_seq": scheduled_seq,
                })

        s2 = _state(tmp_path)
        assert s2.tasks["t_001"].status == TaskStatus.READY
        assert s2.tasks["t_001"].attempts == 2
        assert s2.tasks["t_001"].next_retry_at is None

    def test_retried_task_worker_id_cleared(self, tmp_path):
        """After task_retried, worker_id is cleared so the task can be claimed fresh."""
        _bootstrap(tmp_path)
        _emit(tmp_path, "w1", "failed", "t_001",
              data={"phase": "default", "reason": "err", "retryable": True})
        _append(tmp_path, "orchestrator", "task_scheduled_retry", "t_001",
                data={
                    "phase": "default",
                    "next_retry_at": "2000-01-01T00:00:00+00:00",
                    "backoff_seconds": 1.0,
                    "previous_failure_seq": 1,
                })
        s = _state(tmp_path)
        sched_seq = s.tasks["t_001"].evidence[-1]
        # worker_id should still be set from the claim
        assert s.tasks["t_001"].worker_id == "w1"

        _append(tmp_path, "orchestrator", "task_retried", "t_001", attempt=2,
                data={"phase": "default", "previous_attempt": 1, "scheduled_retry_seq": sched_seq})

        s2 = _state(tmp_path)
        assert s2.tasks["t_001"].worker_id is None

    def test_task_retried_increments_attempts(self, tmp_path):
        """After task_retried, attempts equals the new attempt number."""
        _bootstrap(tmp_path)
        _emit(tmp_path, "w1", "failed", "t_001",
              data={"phase": "default", "reason": "err", "retryable": True})
        _append(tmp_path, "orchestrator", "task_scheduled_retry", "t_001",
                data={
                    "phase": "default",
                    "next_retry_at": "2000-01-01T00:00:00+00:00",
                    "backoff_seconds": 1.0,
                    "previous_failure_seq": 1,
                })
        s = _state(tmp_path)
        sched_seq = s.tasks["t_001"].evidence[-1]

        _append(tmp_path, "orchestrator", "task_retried", "t_001", attempt=2,
                data={"phase": "default", "previous_attempt": 1, "scheduled_retry_seq": sched_seq})

        s2 = _state(tmp_path)
        assert s2.tasks["t_001"].attempts == 2

    def test_task_retried_clears_next_retry_at(self, tmp_path):
        _bootstrap(tmp_path)
        _emit(tmp_path, "w1", "failed", "t_001",
              data={"phase": "default", "reason": "err", "retryable": True})
        _append(tmp_path, "orchestrator", "task_scheduled_retry", "t_001",
                data={
                    "phase": "default",
                    "next_retry_at": "2000-01-01T00:00:00+00:00",
                    "backoff_seconds": 1.0,
                    "previous_failure_seq": 1,
                })
        s = _state(tmp_path)
        sched_seq = s.tasks["t_001"].evidence[-1]

        _append(tmp_path, "orchestrator", "task_retried", "t_001", attempt=2,
                data={"phase": "default", "previous_attempt": 1, "scheduled_retry_seq": sched_seq})

        s2 = _state(tmp_path)
        assert s2.tasks["t_001"].next_retry_at is None


# ---------------------------------------------------------------------------
# tasks_ready_for_retry — integration with real log
# ---------------------------------------------------------------------------

class TestTasksReadyForRetryIntegration:
    def test_expired_scheduled_task_detected(self, tmp_path):
        """tasks_ready_for_retry returns a scheduled task whose backoff has expired."""
        _bootstrap(tmp_path)
        _emit(tmp_path, "w1", "failed", "t_001",
              data={"phase": "default", "reason": "err", "retryable": True})
        _append(tmp_path, "orchestrator", "task_scheduled_retry", "t_001",
                data={
                    "phase": "default",
                    "next_retry_at": "2000-01-01T00:00:00+00:00",
                    "backoff_seconds": 1.0,
                    "previous_failure_seq": 1,
                })

        s = _state(tmp_path)
        ready = tasks_ready_for_retry(s, now_iso())
        assert len(ready) == 1
        assert ready[0].task_id == "t_001"

    def test_future_scheduled_task_not_detected(self, tmp_path):
        """tasks_ready_for_retry ignores tasks whose backoff hasn't expired yet."""
        _bootstrap(tmp_path)
        _emit(tmp_path, "w1", "failed", "t_001",
              data={"phase": "default", "reason": "err", "retryable": True})
        _append(tmp_path, "orchestrator", "task_scheduled_retry", "t_001",
                data={
                    "phase": "default",
                    "next_retry_at": "2099-01-01T00:00:00+00:00",
                    "backoff_seconds": 9999.0,
                    "previous_failure_seq": 1,
                })

        s = _state(tmp_path)
        ready = tasks_ready_for_retry(s, now_iso())
        assert ready == []


# ---------------------------------------------------------------------------
# Full retry cycle: failed → scheduled → retried → claimed → completed
# ---------------------------------------------------------------------------

class TestRetryFullCycle:
    def test_full_retry_cycle_completes(self, tmp_path):
        """End-to-end: task fails, gets scheduled, retried, claimed, then completed."""
        _bootstrap(tmp_path)

        # Attempt 1: worker fails with retryable=True
        _emit(tmp_path, "w1", "failed", "t_001",
              data={"phase": "default", "reason": "transient", "retryable": True})

        s = _state(tmp_path)
        assert s.tasks["t_001"].status == TaskStatus.FAILED

        policy = load_retry_policy("standard")
        assert should_retry(s.tasks["t_001"], policy) is True

        backoff = backoff_seconds(s.tasks["t_001"].attempts, policy.base_delay_s, policy.cap_s,
                                  jitter_range=(1.0, 1.0))
        failure_seq = s.tasks["t_001"].evidence[-1]

        _append(tmp_path, "orchestrator", "task_scheduled_retry", "t_001",
                data={
                    "phase": "default",
                    "next_retry_at": "2000-01-01T00:00:00+00:00",
                    "backoff_seconds": backoff,
                    "previous_failure_seq": failure_seq,
                })

        s2 = _state(tmp_path)
        assert s2.tasks["t_001"].status == TaskStatus.SCHEDULED
        sched_seq = s2.tasks["t_001"].evidence[-1]

        # Backoff expired — emit task_retried (attempt 2)
        _append(tmp_path, "orchestrator", "task_retried", "t_001", attempt=2,
                data={"phase": "default", "previous_attempt": 1, "scheduled_retry_seq": sched_seq})

        s3 = _state(tmp_path)
        assert s3.tasks["t_001"].status == TaskStatus.READY
        assert s3.tasks["t_001"].attempts == 2

        # Orchestrator claims for attempt 2
        _append(tmp_path, "orchestrator", "task_claimed", "t_001", attempt=2,
                data={"phase": "default", "worker_type": "test-worker", "worker_id": "w2"})

        # Worker succeeds on attempt 2
        _emit(tmp_path, "w2", "completed", "t_001", attempt=2,
              data={"phase": "default", "artifacts": [], "summary": "done on retry"})

        s4 = _state(tmp_path)
        assert s4.tasks["t_001"].status == TaskStatus.COMPLETED
        assert s4.tasks["t_001"].attempts == 2

    def test_non_retryable_failure_goes_to_dlq(self, tmp_path):
        """task_failed with retryable=false → DLQ immediately (no retry)."""
        _bootstrap(tmp_path)
        _emit(tmp_path, "w1", "failed", "t_001",
              data={"phase": "default", "reason": "spec_unclear", "retryable": False})

        s = _state(tmp_path)
        assert s.tasks["t_001"].status == TaskStatus.FAILED

        policy = load_retry_policy("standard")
        assert should_retry(s.tasks["t_001"], policy) is False

        _append(tmp_path, "orchestrator", "task_dlq", "t_001",
                data={"phase": "default", "reason": "non_retryable",
                      "last_error": "spec_unclear"})

        s2 = _state(tmp_path)
        assert s2.tasks["t_001"].status == TaskStatus.DLQ

    def test_max_attempts_exceeded_goes_to_dlq(self, tmp_path):
        """After max_attempts failures, should_retry=False → DLQ."""
        _bootstrap(tmp_path, tier="standard")

        policy = load_retry_policy("standard")
        # max_attempts=3 for standard; run 3 fail/retry cycles

        for attempt in range(1, policy.max_attempts + 1):
            _emit(tmp_path, "w1", "failed", "t_001", attempt=attempt,
                  data={"phase": "default", "reason": "err", "retryable": True})
            s = _state(tmp_path)

            if should_retry(s.tasks["t_001"], policy):
                failure_seq = s.tasks["t_001"].evidence[-1]
                _append(tmp_path, "orchestrator", "task_scheduled_retry", "t_001",
                        data={
                            "phase": "default",
                            "next_retry_at": "2000-01-01T00:00:00+00:00",
                            "backoff_seconds": 1.0,
                            "previous_failure_seq": failure_seq,
                        })
                s2 = _state(tmp_path)
                sched_seq = s2.tasks["t_001"].evidence[-1]
                _append(tmp_path, "orchestrator", "task_retried", "t_001",
                        attempt=attempt + 1,
                        data={"phase": "default", "previous_attempt": attempt,
                              "scheduled_retry_seq": sched_seq})
                # Claim for next attempt
                _append(tmp_path, "orchestrator", "task_claimed", "t_001", attempt=attempt + 1,
                        data={"phase": "default", "worker_type": "test-worker", "worker_id": "w1"})
            else:
                # Should_retry=False: send to DLQ
                _append(tmp_path, "orchestrator", "task_dlq", "t_001",
                        data={"phase": "default", "reason": "max_attempts_exceeded",
                              "last_error": "err"})
                break

        s_final = _state(tmp_path)
        assert s_final.tasks["t_001"].status == TaskStatus.DLQ
        assert s_final.tasks["t_001"].attempts == policy.max_attempts
