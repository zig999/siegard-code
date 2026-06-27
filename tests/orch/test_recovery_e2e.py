"""
M4 — E2E test: corrupted log recovery via verify_and_recover.

Scenario:
  1. Write a valid workflow log (tasks created, claimed, completed).
  2. Physically corrupt a byte in the middle of the log.
  3. verify_chain reports ok=False.
  4. verify_and_recover truncates the corrupt portion.
  5. reduce_all() succeeds on the recovered log.
  6. log_recovered event is present in the log.
  7. Verify chain passes on recovered log.
"""
import json
import os
import pytest
import orch_core
from orch_core import (
    append_event,
    reduce_all,
    verify_chain,
    verify_and_recover,
    EventType,
    TaskStatus,
    PhaseStatus,
)


def _write_valid_workflow(phase="dev"):
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": "wf_recovery_test",
        "phases": [{"name": phase, "order": 1, "required": True}],
    })
    append_event("orchestrator", "phase_entered", data={"phase": phase, "order": 1, "workflow_id": "wf-fix"})
    append_event("orchestrator", "task_created", task_id="t_001", data={
        "phase": phase, "tier": "standard", "type": "impl",
        "spec": "recovery test task", "deps": [],
    })
    append_event("worker", "task_claimed", task_id="t_001", attempt=1, data={
        "phase": phase, "worker_type": "impl", "worker_id": "w_001",
    })
    append_event("worker", "task_completed", task_id="t_001", attempt=1, data={
        "phase": phase, "artifacts": ["t_001.out"], "summary": "done",
    })


def _log_path():
    """Returns the current monkeypatched LOG_PATH from orch_core."""
    return orch_core.LOG_PATH


def _corrupt_middle_line() -> int:
    """Corrupts one byte in the 3rd line of the log. Returns the seq of that line."""
    log_path = _log_path()
    lines = log_path.read_bytes().splitlines(keepends=True)
    assert len(lines) >= 3, "need at least 3 lines to corrupt the middle"
    # Parse the 3rd line to get its seq
    target_idx = 2
    original = lines[target_idx]
    try:
        d = json.loads(original)
        seq = d["seq"]
    except (json.JSONDecodeError, KeyError):
        seq = -1
    # Corrupt: replace first '{' with '!'
    corrupted = original.replace(b"{", b"!", 1)
    lines[target_idx] = corrupted
    log_path.write_bytes(b"".join(lines))
    return seq


class TestRecoveryE2E:
    # test_verify_detects_corruption removed — corruption detection is owned by
    # test_verify.py (TestVerifyCorruptJSON). The full corrupt→recover→verify-ok chain remains below.

    def test_verify_and_recover_restores_integrity(self, tmp_orch):
        """M4.2: after verify_and_recover, verify_chain passes."""
        _write_valid_workflow()
        corrupt_seq = _corrupt_middle_line()
        assert corrupt_seq > 0

        verify_and_recover(from_seq=corrupt_seq, operator="test", confirm=True)

        result = verify_chain(mode="strict")
        assert result.ok is True

    # test_recovered_log_is_reducible, test_log_recovered_event_is_in_log,
    # test_recover_without_confirm_raises removed — these per-assertion checks duplicate
    # test_verify_and_recover.py unit tests (test_after_recovery_verify_strict_passes,
    # test_recovery_emits_log_recovered_event, test_confirm_false_raises).

    def test_state_before_corruption_is_preserved(self, tmp_orch):
        """M4.6: events before the corrupted seq are preserved after recovery."""
        _write_valid_workflow()
        # Corrupt the 4th line (task_claimed) — first 3 events should survive
        log_path = _log_path()
        lines = log_path.read_bytes().splitlines(keepends=True)
        target_idx = 3
        seq = json.loads(lines[target_idx])["seq"]
        lines[target_idx] = lines[target_idx].replace(b"{", b"!", 1)
        log_path.write_bytes(b"".join(lines))

        verify_and_recover(from_seq=seq, operator="test", confirm=True)

        state = reduce_all()
        # phase_declared, phase_entered, task_created survived → task exists in pending/ready
        assert "t_001" in state.tasks
        assert state.tasks["t_001"].status in (TaskStatus.PENDING, TaskStatus.READY)
