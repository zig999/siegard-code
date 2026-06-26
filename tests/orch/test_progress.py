"""
Rec #8 — compute_progress(state): estimable progress for ETA / observability.

Pure function of derived state; terminal = completed | dlq | skipped.
Uses tmp_orch (no-reload isolation) per the tests/orch/ convention.
"""
import orch_core


def _emit(event_type, task_id=None, data=None):
    return orch_core.append_event(
        agent="orch", event_type=event_type, task_id=task_id, data=data or {}
    )


def test_progress_counts_terminal_and_remaining(tmp_orch):
    _emit("phase_declared", data={"workflow_id": "w", "phases": [{"name": "dev", "order": 1, "required": True}]})
    _emit("phase_entered", data={"phase": "dev", "order": 1, "workflow_id": "w"})
    for tid in ("T1", "T2", "T3"):
        _emit("task_created", task_id=tid, data={"phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": []})
    # T1 completed (terminal)
    _emit("task_claimed", task_id="T1", data={"phase": "dev", "worker_type": "impl", "worker_id": "w1"})
    _emit("task_completed", task_id="T1", data={"phase": "dev", "artifacts": [], "summary": "d"})
    # T2 -> dlq (terminal); T3 stays pending
    _emit("task_claimed", task_id="T2", data={"phase": "dev", "worker_type": "impl", "worker_id": "w2"})
    _emit("task_failed", task_id="T2", data={"phase": "dev", "reason": "non_retryable", "retryable": False})
    _emit("task_dlq", task_id="T2", data={"phase": "dev", "reason": "non_retryable", "last_error": "e"})

    prog = orch_core.compute_progress(orch_core.reduce_all())
    assert prog["tasks_total"] == 3
    assert prog["tasks_terminal"] == 2          # completed + dlq
    assert prog["tasks_remaining"] == 1
    assert prog["pct_complete"] == round(100.0 * 2 / 3, 1)
    assert prog["current_phase"] == "dev"
    assert prog["by_phase"]["dev"] == {"total": 3, "terminal": 2, "remaining": 1, "pct_complete": prog["pct_complete"]}


def test_progress_empty_state_is_zero(tmp_orch):
    _emit("phase_declared", data={"workflow_id": "w", "phases": [{"name": "dev", "order": 1, "required": True}]})
    prog = orch_core.compute_progress(orch_core.reduce_all())
    assert prog["tasks_total"] == 0
    assert prog["tasks_remaining"] == 0
    assert prog["pct_complete"] == 0.0
    assert prog["by_phase"] == {}
