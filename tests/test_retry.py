"""
Retry policy and circuit breaker tests.
"""
import pytest


# ---------------------------------------------------------------------------
# backoff_seconds
# ---------------------------------------------------------------------------

class TestBackoffSeconds:

    def test_attempt_1_equals_base_delay(self):
        import orch_core
        # formula: min(base * 2^0, cap) * jitter = base * jitter
        # With jitter (0.8, 1.2), result must be in [base*0.8, base*1.2]
        base = 30.0
        cap = 600.0
        for _ in range(20):
            result = orch_core.backoff_seconds(1, base_delay_s=base, cap_s=cap, jitter_range=(0.8, 1.2))
            assert base * 0.8 <= result <= base * 1.2

    def test_doubles_each_attempt(self):
        import orch_core
        base = 10.0
        cap = 10000.0
        # No jitter for deterministic check
        for attempt in range(1, 6):
            raw = base * (2 ** (attempt - 1))
            result = orch_core.backoff_seconds(attempt, base_delay_s=base, cap_s=cap, jitter_range=(1.0, 1.0))
            assert abs(result - raw) < 0.001, f"attempt={attempt}: expected {raw}, got {result}"

    def test_capped_at_cap_s(self):
        import orch_core
        cap = 60.0
        # High attempt number would exceed cap without capping
        for _ in range(20):
            result = orch_core.backoff_seconds(20, base_delay_s=30.0, cap_s=cap, jitter_range=(0.8, 1.2))
            assert result <= cap * 1.2  # jitter can push slightly above cap

    def test_attempt_zero_treated_as_one(self):
        import orch_core
        base = 30.0
        r0 = orch_core.backoff_seconds(0, base_delay_s=base, cap_s=600.0, jitter_range=(1.0, 1.0))
        r1 = orch_core.backoff_seconds(1, base_delay_s=base, cap_s=600.0, jitter_range=(1.0, 1.0))
        assert abs(r0 - r1) < 0.001


# ---------------------------------------------------------------------------
# should_retry
# ---------------------------------------------------------------------------

def _make_task_state(status="failed", attempts=1, retryable=True, reason=None):
    import orch_core
    return orch_core.TaskState(
        task_id="t1",
        phase="sdd",
        status=orch_core.TaskStatus.FAILED,
        deps=[],
        tier="standard",
        task_type="spec",
        spec="x",
        attempts=attempts,
        last_failure_retryable=retryable,
        last_failure_reason=reason,
    )


class TestShouldRetry:

    def test_retries_when_under_max_attempts(self):
        import orch_core
        policy = orch_core.RetryPolicy(max_attempts=3, base_delay_s=30.0, cap_s=600.0)
        task = _make_task_state(attempts=1, retryable=True)
        assert orch_core.should_retry(task, policy) is True

    def test_no_retry_when_not_retryable(self):
        import orch_core
        policy = orch_core.RetryPolicy(max_attempts=3, base_delay_s=30.0, cap_s=600.0)
        task = _make_task_state(attempts=1, retryable=False)
        assert orch_core.should_retry(task, policy) is False

    def test_no_retry_when_max_attempts_reached(self):
        import orch_core
        policy = orch_core.RetryPolicy(max_attempts=3, base_delay_s=30.0, cap_s=600.0)
        task = _make_task_state(attempts=3, retryable=True)
        assert orch_core.should_retry(task, policy) is False

    def test_structural_reason_caps_at_one_retry(self):
        import orch_core
        policy = orch_core.RetryPolicy(max_attempts=5, base_delay_s=30.0, cap_s=600.0)
        # Second attempt with a structural reason should not retry again
        task = _make_task_state(attempts=2, retryable=True, reason="worker_exited_without_terminal")
        assert orch_core.should_retry(task, policy) is False

    def test_structural_reason_first_attempt_allows_retry(self):
        import orch_core
        policy = orch_core.RetryPolicy(max_attempts=5, base_delay_s=30.0, cap_s=600.0)
        task = _make_task_state(attempts=1, retryable=True, reason="worker_exited_without_terminal")
        assert orch_core.should_retry(task, policy) is True


# ---------------------------------------------------------------------------
# evaluate_circuit_state
# ---------------------------------------------------------------------------

class TestCircuitBreaker:

    def _now_iso(self):
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
               f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"

    def _state_with_failures(self, count: int):
        import orch_core
        state = orch_core.OrchState()
        now = self._now_iso()
        state.failure_timestamps = [now] * count
        return state

    def test_does_not_trip_below_threshold(self):
        import orch_core
        cfg = orch_core.default_config()
        cfg["circuit_breaker"]["failure_threshold"] = 50
        state = self._state_with_failures(49)
        result = orch_core.evaluate_circuit_state(state, self._now_iso(), config=cfg)
        assert result["should_trip"] is False

    def test_trips_at_threshold(self):
        import orch_core
        cfg = orch_core.default_config()
        cfg["circuit_breaker"]["failure_threshold"] = 50
        state = self._state_with_failures(50)
        result = orch_core.evaluate_circuit_state(state, self._now_iso(), config=cfg)
        assert result["should_trip"] is True

    def test_already_tripped_does_not_re_trip(self, orch_dir, make_event):
        import orch_core
        make_event("circuit_breaker_tripped", data={
            "window_start": "2026-01-01T00:00:00.000Z",
            "window_end": "2026-01-01T00:10:00.000Z",
            "failure_count": 55,
            "threshold": 50,
        })
        state = orch_core.reduce_all()
        # Add failures to state manually so circuit is also above threshold
        state.failure_timestamps = [self._now_iso()] * 60

        result = orch_core.evaluate_circuit_state(state, self._now_iso())
        assert result["already_tripped"] is True
        assert result["should_trip"] is False

    def test_disabled_circuit_breaker_never_trips(self):
        import orch_core
        cfg = orch_core.default_config()
        cfg["circuit_breaker"]["enabled"] = False
        state = self._state_with_failures(1000)
        result = orch_core.evaluate_circuit_state(state, self._now_iso(), config=cfg)
        assert result["should_trip"] is False

    def test_failures_outside_window_not_counted(self):
        import orch_core
        from datetime import datetime, timezone, timedelta
        cfg = orch_core.default_config()
        cfg["circuit_breaker"]["window_minutes"] = 10
        cfg["circuit_breaker"]["failure_threshold"] = 5
        state = orch_core.OrchState()
        # Old failures outside 10-minute window
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        state.failure_timestamps = [old_ts] * 100
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        result = orch_core.evaluate_circuit_state(state, now, config=cfg)
        assert result["failure_count"] == 0
        assert result["should_trip"] is False
