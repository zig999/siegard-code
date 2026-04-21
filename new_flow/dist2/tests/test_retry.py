"""Tests for Task 4.1 — RetryPolicy, backoff_seconds, should_retry, tasks_ready_for_retry."""
import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

LIB = Path(__file__).parents[1] / ".claude" / "lib"
sys.path.insert(0, str(LIB))

from orch_core import (
    OrchState,
    RetryPolicy,
    TaskState,
    TaskStatus,
    Tier,
    backoff_seconds,
    default_config,
    load_config,
    load_retry_policy,
    now_iso,
    parse_iso,
    should_retry,
    tasks_ready_for_retry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(
    task_id: str = "t_001",
    status: TaskStatus = TaskStatus.FAILED,
    tier: str = "standard",
    attempts: int = 1,
    retryable: bool | None = True,
    next_retry_at: str | None = None,
    task_type: str = "impl",
) -> TaskState:
    return TaskState(
        task_id=task_id,
        phase="default",
        status=status,
        tier=Tier(tier),
        task_type=task_type,
        spec="x",
        deps=[],
        attempts=attempts,
        last_failure_retryable=retryable,
        next_retry_at=next_retry_at,
    )


def _state(*tasks: TaskState) -> OrchState:
    return OrchState(tasks={t.task_id: t for t in tasks})


# ---------------------------------------------------------------------------
# backoff_seconds
# ---------------------------------------------------------------------------

class TestBackoffSeconds:
    def test_attempt_1_returns_base(self):
        val = backoff_seconds(1, base_delay_s=30.0, cap_s=600.0, jitter_range=(1.0, 1.0))
        assert val == pytest.approx(30.0)

    def test_attempt_2_doubles(self):
        val = backoff_seconds(2, base_delay_s=30.0, cap_s=600.0, jitter_range=(1.0, 1.0))
        assert val == pytest.approx(60.0)

    def test_attempt_3_quadruples(self):
        val = backoff_seconds(3, base_delay_s=30.0, cap_s=600.0, jitter_range=(1.0, 1.0))
        assert val == pytest.approx(120.0)

    def test_capped_at_cap_s(self):
        # attempt 10 with base 30 would be 30 * 2^9 = 15360 >> cap=600
        val = backoff_seconds(10, base_delay_s=30.0, cap_s=600.0, jitter_range=(1.0, 1.0))
        assert val == pytest.approx(600.0)

    def test_jitter_within_range(self):
        # Run many iterations to check jitter stays within [0.8, 1.2] × raw
        raw = 30.0
        for _ in range(200):
            val = backoff_seconds(1, base_delay_s=raw, cap_s=600.0)
            assert raw * 0.8 <= val <= raw * 1.2 + 1e-9

    def test_zero_attempts_treated_as_one(self):
        val_zero = backoff_seconds(0, base_delay_s=30.0, cap_s=600.0, jitter_range=(1.0, 1.0))
        val_one  = backoff_seconds(1, base_delay_s=30.0, cap_s=600.0, jitter_range=(1.0, 1.0))
        assert val_zero == pytest.approx(val_one)

    def test_cap_times_jitter_upper_bound(self):
        # Maximum possible value is cap_s × jitter_high
        val = backoff_seconds(100, base_delay_s=30.0, cap_s=600.0, jitter_range=(0.8, 1.2))
        assert val <= 600.0 * 1.2 + 1e-9


# ---------------------------------------------------------------------------
# RetryPolicy — per tier
# ---------------------------------------------------------------------------

class TestRetryPolicyByTier:
    def test_critical_defaults(self):
        cfg = default_config()
        p = RetryPolicy.for_tier("critical", cfg)
        assert p.max_attempts == 5
        assert p.base_delay_s == 15.0
        assert p.cap_s == 600.0

    def test_standard_defaults(self):
        cfg = default_config()
        p = RetryPolicy.for_tier("standard", cfg)
        assert p.max_attempts == 3
        assert p.base_delay_s == 30.0

    def test_bulk_defaults(self):
        cfg = default_config()
        p = RetryPolicy.for_tier("bulk", cfg)
        assert p.max_attempts == 1
        assert p.base_delay_s == 0.0

    def test_unknown_tier_falls_back_to_standard(self):
        cfg = default_config()
        p = RetryPolicy.for_tier("unknown_tier_xyz", cfg)
        assert p.max_attempts == 3  # standard defaults

    def test_config_override_applied(self):
        cfg = default_config()
        cfg["retry_policy"]["defaults_by_tier"]["standard"]["max_attempts"] = 7
        p = RetryPolicy.for_tier("standard", cfg)
        assert p.max_attempts == 7


# ---------------------------------------------------------------------------
# RetryPolicy — task_type override
# ---------------------------------------------------------------------------

class TestRetryPolicyByTaskType:
    def test_override_takes_precedence(self):
        cfg = default_config()
        cfg["retry_policy"]["overrides_by_task_type"]["critical_job"] = {
            "max_attempts": 10,
            "base_delay_s": 5.0,
            "cap_s": 120.0,
        }
        p = RetryPolicy.for_task("critical_job", "standard", cfg)
        assert p.max_attempts == 10
        assert p.base_delay_s == 5.0
        assert p.cap_s == 120.0

    def test_no_override_falls_back_to_tier(self):
        cfg = default_config()
        p = RetryPolicy.for_task("unknown_type", "critical", cfg)
        assert p.max_attempts == 5  # critical defaults

    def test_partial_override_inherits_tier_defaults(self):
        cfg = default_config()
        cfg["retry_policy"]["overrides_by_task_type"]["test_type"] = {"max_attempts": 9}
        p = RetryPolicy.for_task("test_type", "standard", cfg)
        assert p.max_attempts == 9
        assert p.base_delay_s == 30.0  # inherited from standard

    def test_empty_task_type_falls_back_to_tier(self):
        cfg = default_config()
        p = RetryPolicy.for_task("", "bulk", cfg)
        assert p.max_attempts == 1


# ---------------------------------------------------------------------------
# load_retry_policy
# ---------------------------------------------------------------------------

class TestLoadRetryPolicy:
    def test_returns_retry_policy_instance(self):
        p = load_retry_policy("standard")
        assert isinstance(p, RetryPolicy)

    def test_with_task_type_override_via_config_path(self, tmp_path):
        import json
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({
            "retry_policy": {
                "overrides_by_task_type": {
                    "fast_task": {"max_attempts": 2, "base_delay_s": 5.0, "cap_s": 60.0}
                }
            }
        }))
        p = load_retry_policy("standard", task_type="fast_task", config_path=cfg_path)
        assert p.max_attempts == 2

    def test_missing_config_file_uses_defaults(self, tmp_path):
        p = load_retry_policy("standard", config_path=tmp_path / "nonexistent.json")
        assert p.max_attempts == 3


# ---------------------------------------------------------------------------
# should_retry
# ---------------------------------------------------------------------------

class TestShouldRetry:
    def test_retryable_within_attempts(self):
        t = _task(attempts=1, retryable=True)
        p = RetryPolicy(max_attempts=3, base_delay_s=30.0, cap_s=600.0)
        assert should_retry(t, p) is True

    def test_retryable_false_blocks_retry(self):
        t = _task(attempts=1, retryable=False)
        p = RetryPolicy(max_attempts=3, base_delay_s=30.0, cap_s=600.0)
        assert should_retry(t, p) is False

    def test_attempts_at_max_blocks_retry(self):
        t = _task(attempts=3, retryable=True)
        p = RetryPolicy(max_attempts=3, base_delay_s=30.0, cap_s=600.0)
        assert should_retry(t, p) is False

    def test_attempts_above_max_blocks_retry(self):
        t = _task(attempts=5, retryable=True)
        p = RetryPolicy(max_attempts=3, base_delay_s=30.0, cap_s=600.0)
        assert should_retry(t, p) is False

    def test_retryable_none_is_treated_as_true(self):
        t = _task(attempts=1, retryable=None)
        p = RetryPolicy(max_attempts=3, base_delay_s=30.0, cap_s=600.0)
        assert should_retry(t, p) is True

    def test_exactly_one_attempt_remaining(self):
        t = _task(attempts=2, retryable=True)
        p = RetryPolicy(max_attempts=3, base_delay_s=30.0, cap_s=600.0)
        assert should_retry(t, p) is True


# ---------------------------------------------------------------------------
# tasks_ready_for_retry
# ---------------------------------------------------------------------------

class TestTasksReadyForRetry:
    def test_empty_state_returns_empty(self):
        result = tasks_ready_for_retry(_state(), now_iso())
        assert result == []

    def test_scheduled_task_with_past_retry_at(self):
        t = _task(status=TaskStatus.SCHEDULED, next_retry_at="2000-01-01T00:00:00+00:00")
        result = tasks_ready_for_retry(_state(t), now_iso())
        assert len(result) == 1
        assert result[0].task_id == "t_001"

    def test_scheduled_task_with_future_retry_at_not_returned(self):
        t = _task(status=TaskStatus.SCHEDULED, next_retry_at="2099-01-01T00:00:00+00:00")
        result = tasks_ready_for_retry(_state(t), now_iso())
        assert result == []

    def test_scheduled_task_no_retry_at_is_ready(self):
        t = _task(status=TaskStatus.SCHEDULED, next_retry_at=None)
        result = tasks_ready_for_retry(_state(t), now_iso())
        assert len(result) == 1

    def test_non_scheduled_tasks_ignored(self):
        for status in [TaskStatus.FAILED, TaskStatus.RUNNING, TaskStatus.COMPLETED, TaskStatus.PENDING]:
            t = _task(status=status, next_retry_at="2000-01-01T00:00:00+00:00")
            result = tasks_ready_for_retry(_state(t), now_iso())
            assert result == [], f"Expected empty for status {status}"

    def test_multiple_tasks_only_past_returned(self):
        past = _task("t_001", status=TaskStatus.SCHEDULED, next_retry_at="2000-01-01T00:00:00+00:00")
        future = _task("t_002", status=TaskStatus.SCHEDULED, next_retry_at="2099-01-01T00:00:00+00:00")
        result = tasks_ready_for_retry(_state(past, future), now_iso())
        assert len(result) == 1
        assert result[0].task_id == "t_001"
