"""SIEGARD F3/F4 — atomic retry scheduling (BUG-4).

The stale reaper and the SubagentStop hook emit task_failed from Python, but the
matching task_scheduled_retry was emitted only later by the orchestrator LLM (Step
5.5). If the orchestrator turn ended between the two, the task stalled in FAILED with
nobody scheduling the retry. schedule_retry_if_due (called from both paths) now emits
task_scheduled_retry in the SAME Python call when the failure is retryable, so the
task advances to SCHEDULED and the next orchestrator invocation resumes it.
"""
import orch_core

FAR_FUTURE = "2999-01-01T00:00:00.000Z"


def _ep(make_event, phase="dev", wf="wf"):
    make_event("phase_declared", data={
        "workflow_id": wf, "phases": [{"name": phase, "order": 1, "required": True}]})
    make_event("phase_entered", data={"phase": phase, "order": 1, "workflow_id": wf})


def _create(make_event, tid, task_type="", tier="standard"):
    make_event("task_created", task_id=tid, data={
        "phase": "dev", "tier": tier, "type": task_type, "spec": "s", "deps": []})


def _claim(make_event, tid, attempt=1):
    make_event("task_claimed", task_id=tid, attempt=attempt, data={
        "phase": "dev", "worker_type": "impl", "worker_id": f"w{attempt}"})


def _sched(event_type="task_scheduled_retry"):
    return orch_core.read_events_filtered(event_type=event_type)


class TestReaperSchedulesRetry:

    def test_reaper_schedules_retry_atomically(self, orch_dir, make_event):
        _ep(make_event)
        _create(make_event, "t1")
        _claim(make_event, "t1")
        assert orch_core.reap_stale_tasks(FAR_FUTURE) == ["t1"]

        state = orch_core.reduce_all()
        # Was left FAILED before F3; now SCHEDULED — the retry is already in the log.
        assert state.tasks["t1"].status == orch_core.TaskStatus.SCHEDULED
        sched = _sched()
        assert len(sched) == 1 and sched[0].task_id == "t1"
        # previous_failure_seq points at the task_failed the reaper emitted.
        failed = orch_core.read_events_filtered(event_type="task_failed")
        assert sched[0].data["previous_failure_seq"] == failed[0].seq
        assert sched[0].data["next_retry_at"]  # non-empty

    def test_reaper_no_schedule_at_structural_cap(self, orch_dir, make_event):
        """A stale_timeout on attempt 2 is at the structural retry cap (should_retry
        False): the reaper emits the failure but must NOT schedule a retry — the task
        stays FAILED for the orchestrator to route to DLQ."""
        _ep(make_event)
        _create(make_event, "t1")
        _claim(make_event, "t1", attempt=1)
        fev = make_event("task_failed", task_id="t1", attempt=1, data={
            "phase": "dev", "reason": "stale_timeout", "retryable": True})
        make_event("task_scheduled_retry", task_id="t1", data={
            "phase": "dev", "next_retry_at": "2000-01-01T00:00:00.000Z",
            "backoff_seconds": 30, "previous_failure_seq": fev.seq})
        make_event("task_retried", task_id="t1", attempt=2, data={
            "phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": fev.seq + 1})
        _claim(make_event, "t1", attempt=2)   # RUNNING on attempt 2

        assert orch_core.reap_stale_tasks(FAR_FUTURE) == ["t1"]
        state = orch_core.reduce_all()
        assert state.tasks["t1"].status == orch_core.TaskStatus.FAILED
        # Only the single setup scheduled_retry — the reaper added none for attempt 2.
        assert len(_sched()) == 1

    def test_reaper_idempotent_after_schedule(self, orch_dir, make_event):
        _ep(make_event)
        _create(make_event, "t1")
        _claim(make_event, "t1")
        assert orch_core.reap_stale_tasks(FAR_FUTURE) == ["t1"]     # FAILED -> SCHEDULED
        # Second pass: SCHEDULED is not RUNNING -> nothing to reap, no extra schedule.
        assert orch_core.reap_stale_tasks(FAR_FUTURE) == []
        assert len(_sched()) == 1


class TestScheduleRetryIfDue:

    def test_noop_when_task_not_failed(self, orch_dir, make_event):
        _ep(make_event)
        _create(make_event, "t1")
        _claim(make_event, "t1")
        make_event("task_completed", task_id="t1", data={"phase": "dev", "artifacts": []})
        assert orch_core.schedule_retry_if_due("t1", previous_failure_seq=1) is None
        assert _sched() == []

    def test_noop_when_non_retryable(self, orch_dir, make_event):
        _ep(make_event)
        _create(make_event, "t1")
        _claim(make_event, "t1")
        fev = make_event("task_failed", task_id="t1", attempt=1, data={
            "phase": "dev", "reason": "validation_failed", "retryable": False})
        assert orch_core.schedule_retry_if_due("t1", fev.seq) is None
        assert orch_core.reduce_all().tasks["t1"].status == orch_core.TaskStatus.FAILED
        assert _sched() == []

    def test_schedules_retryable_failure(self, orch_dir, make_event):
        _ep(make_event)
        _create(make_event, "t1")
        _claim(make_event, "t1")
        fev = make_event("task_failed", task_id="t1", attempt=1, data={
            "phase": "dev", "reason": "internal_error", "retryable": True})
        result = orch_core.schedule_retry_if_due("t1", fev.seq)
        assert result is not None
        assert orch_core.reduce_all().tasks["t1"].status == orch_core.TaskStatus.SCHEDULED
        assert len(_sched()) == 1

    def test_noop_when_task_absent(self, orch_dir, make_event):
        _ep(make_event)
        assert orch_core.schedule_retry_if_due("ghost", previous_failure_seq=1) is None
