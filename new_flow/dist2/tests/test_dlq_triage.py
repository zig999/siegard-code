"""Tests for Task 4.6 — dlq_triage.py and escalation detection helpers.

Covers scenarios 10.3 (E03), 10.4 (E06), 10.5 (E04).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).parents[1] / ".claude" / "lib"
HOOKS_DIR = Path(__file__).parents[1] / ".claude" / "hooks"
SKILLS_DIR = Path(__file__).parents[1] / ".claude" / "skills"
APPEND = str(SKILLS_DIR / "orch-log" / "scripts" / "append.py")
EMIT = str(SKILLS_DIR / "orch-report" / "scripts" / "emit.py")
TRIAGE = str(HOOKS_DIR / "dlq_triage.py")

sys.path.insert(0, str(LIB))
sys.path.insert(0, str(HOOKS_DIR))

from orch_core import (
    OrchState,
    TaskState,
    TaskStatus,
    Tier,
    detect_critical_dlq,
    detect_deadlock,
    detect_dependency_cycle,
)
import dlq_triage as dt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(
    task_id: str,
    status: TaskStatus,
    tier: str = "standard",
    deps: list[str] | None = None,
    reason: str | None = None,
    error: str | None = None,
) -> TaskState:
    return TaskState(
        task_id=task_id,
        phase="default",
        status=status,
        tier=Tier(tier),
        task_type="impl",
        spec="x",
        deps=deps or [],
        last_failure_reason=reason,
        last_error=error,
    )


def _state(*tasks: TaskState) -> OrchState:
    return OrchState(tasks={t.task_id: t for t in tasks})


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


# ---------------------------------------------------------------------------
# detect_dependency_cycle
# ---------------------------------------------------------------------------

class TestDetectDependencyCycle:
    def test_no_cycle_empty(self):
        assert detect_dependency_cycle(_state()) == []

    def test_no_cycle_linear_chain(self):
        a = _task("t_001", TaskStatus.READY)
        b = _task("t_002", TaskStatus.PENDING, deps=["t_001"])
        assert detect_dependency_cycle(_state(a, b)) == []

    def test_direct_cycle(self):
        """Scenario 10.3: A→B and B→A forms a cycle."""
        a = _task("t_001", TaskStatus.PENDING, deps=["t_002"])
        b = _task("t_002", TaskStatus.PENDING, deps=["t_001"])
        result = detect_dependency_cycle(_state(a, b))
        assert len(result) > 0

    def test_three_node_cycle(self):
        a = _task("t_001", TaskStatus.PENDING, deps=["t_003"])
        b = _task("t_002", TaskStatus.PENDING, deps=["t_001"])
        c = _task("t_003", TaskStatus.PENDING, deps=["t_002"])
        result = detect_dependency_cycle(_state(a, b, c))
        assert len(result) > 0

    def test_completed_tasks_excluded(self):
        """Completed tasks don't participate in cycle detection."""
        a = _task("t_001", TaskStatus.COMPLETED, deps=["t_002"])
        b = _task("t_002", TaskStatus.COMPLETED, deps=["t_001"])
        assert detect_dependency_cycle(_state(a, b)) == []

    def test_dlq_tasks_excluded(self):
        a = _task("t_001", TaskStatus.DLQ, deps=["t_002"])
        b = _task("t_002", TaskStatus.DLQ, deps=["t_001"])
        assert detect_dependency_cycle(_state(a, b)) == []

    def test_partial_graph_no_cycle(self):
        a = _task("t_001", TaskStatus.READY)
        b = _task("t_002", TaskStatus.PENDING, deps=["t_001"])
        c = _task("t_003", TaskStatus.PENDING, deps=["t_002"])
        assert detect_dependency_cycle(_state(a, b, c)) == []


# ---------------------------------------------------------------------------
# detect_deadlock
# ---------------------------------------------------------------------------

class TestDetectDeadlock:
    def test_empty_state_no_deadlock(self):
        assert detect_deadlock(_state()) is False

    def test_ready_tasks_no_deadlock(self):
        a = _task("t_001", TaskStatus.READY)
        assert detect_deadlock(_state(a)) is False

    def test_running_tasks_no_deadlock(self):
        a = _task("t_001", TaskStatus.RUNNING)
        assert detect_deadlock(_state(a)) is False

    def test_scheduled_tasks_no_deadlock(self):
        a = _task("t_001", TaskStatus.SCHEDULED)
        assert detect_deadlock(_state(a)) is False

    def test_all_terminal_no_deadlock(self):
        """All tasks completed — not deadlock, it's normal completion."""
        a = _task("t_001", TaskStatus.COMPLETED)
        b = _task("t_002", TaskStatus.DLQ)
        assert detect_deadlock(_state(a, b)) is False

    def test_pending_dep_on_dlq_is_deadlock(self):
        """Scenario 10.4: pending task whose only dep is in DLQ → deadlock."""
        dlq = _task("t_001", TaskStatus.DLQ)
        pending = _task("t_002", TaskStatus.PENDING, deps=["t_001"])
        assert detect_deadlock(_state(dlq, pending)) is True

    def test_pending_dep_on_missing_task_is_deadlock(self):
        pending = _task("t_001", TaskStatus.PENDING, deps=["t_nonexistent"])
        assert detect_deadlock(_state(pending)) is True

    def test_cycle_among_pending_is_deadlock(self):
        a = _task("t_001", TaskStatus.PENDING, deps=["t_002"])
        b = _task("t_002", TaskStatus.PENDING, deps=["t_001"])
        assert detect_deadlock(_state(a, b)) is True

    def test_pending_with_pending_dep_not_deadlock(self):
        """t_002 depends on t_001 (also pending) — may resolve if t_001 becomes ready."""
        a = _task("t_001", TaskStatus.PENDING, deps=[])  # no deps, can become ready
        b = _task("t_002", TaskStatus.PENDING, deps=["t_001"])
        assert detect_deadlock(_state(a, b)) is False


# ---------------------------------------------------------------------------
# detect_critical_dlq
# ---------------------------------------------------------------------------

class TestDetectCriticalDlq:
    def test_no_dlq_returns_empty(self):
        a = _task("t_001", TaskStatus.COMPLETED, tier="critical")
        assert detect_critical_dlq(_state(a)) == []

    def test_standard_dlq_not_returned(self):
        a = _task("t_001", TaskStatus.DLQ, tier="standard")
        assert detect_critical_dlq(_state(a)) == []

    def test_critical_dlq_returned(self):
        """Scenario 10.5: critical task in DLQ triggers E04."""
        a = _task("t_001", TaskStatus.DLQ, tier="critical")
        result = detect_critical_dlq(_state(a))
        assert "t_001" in result

    def test_multiple_critical_dlq(self):
        a = _task("t_001", TaskStatus.DLQ, tier="critical")
        b = _task("t_002", TaskStatus.DLQ, tier="critical")
        c = _task("t_003", TaskStatus.DLQ, tier="standard")
        result = detect_critical_dlq(_state(a, b, c))
        assert set(result) == {"t_001", "t_002"}


# ---------------------------------------------------------------------------
# DLQ triage bucket classification
# ---------------------------------------------------------------------------

class TestBucketClassification:
    def test_spec_unclear_is_input_issue(self):
        assert dt._classify("spec_unclear", None) == "input_issue"

    def test_network_error_is_transient(self):
        assert dt._classify("network_error", None) == "transient_issue"

    def test_stale_timeout_is_transient(self):
        assert dt._classify("stale_timeout", None) == "transient_issue"

    def test_worker_exited_is_transient(self):
        assert dt._classify("worker_exited_without_terminal", None) == "transient_issue"

    def test_permission_denied_is_permission_issue(self):
        assert dt._classify("access_denied", None) == "permission_issue"

    def test_quota_exceeded_is_quota_issue(self):
        assert dt._classify("quota_exceeded", None) == "quota_issue"

    def test_rate_limit_is_quota_issue(self):
        assert dt._classify("rate_limit", None) == "quota_issue"

    def test_traceback_is_code_issue(self):
        assert dt._classify(None, "traceback in worker logic") == "code_issue"

    def test_empty_reason_is_unknown(self):
        assert dt._classify(None, None) == "unknown"

    def test_error_field_used_when_reason_empty(self):
        assert dt._classify(None, "quota exceeded") == "quota_issue"

    def test_all_7_buckets_exist(self):
        expected = {
            "input_issue", "worker_issue", "permission_issue",
            "code_issue", "quota_issue", "transient_issue", "unknown",
        }
        result = dt.triage_tasks.__code__.co_consts  # just check implementation exists
        # Verify buckets are all present in the triage dict
        sample_state = OrchState()
        import os
        import tempfile
        # We don't need a real log — just verify classify covers all buckets
        patterns = [
            ("spec_unclear", "input_issue"),
            ("worker crash", "worker_issue"),
            ("access_denied", "permission_issue"),
            ("traceback", "code_issue"),
            ("quota", "quota_issue"),
            ("network", "transient_issue"),
            ("", "unknown"),
        ]
        for reason, expected_bucket in patterns:
            assert dt._classify(reason, None) == expected_bucket, \
                f"reason={reason!r} expected {expected_bucket}"


# ---------------------------------------------------------------------------
# dlq_triage.py CLI
# ---------------------------------------------------------------------------

class TestDlqTriageCLI:
    def _append(self, cwd, agent, event_type, task_id=None, attempt=1, data=None):
        return _append(cwd, agent, event_type, task_id, attempt, data)

    def _setup_dlq_task(self, cwd, task_id="t_001", reason="spec_unclear", tier="standard"):
        self._append(cwd, "orchestrator", "phase_declared",
                     data={"workflow_id": "wf_triage",
                           "phases": [{"name": "default", "order": 1, "required": True}]})
        self._append(cwd, "orchestrator", "phase_entered",
                     data={"phase": "default", "order": 1})
        self._append(cwd, "orchestrator", "task_created", task_id,
                     data={"phase": "default", "deps": [], "tier": tier,
                           "type": "impl", "spec": "x"})
        self._append(cwd, "orchestrator", "task_claimed", task_id,
                     data={"phase": "default", "worker_type": "test-worker",
                           "worker_id": "w1"})
        _emit(cwd, "w1", "failed", task_id,
              data={"phase": "default", "reason": reason, "retryable": False})
        self._append(cwd, "orchestrator", "task_dlq", task_id,
                     data={"phase": "default", "reason": "non_retryable",
                           "last_error": reason})

    def test_no_log_exits_4(self, tmp_path):
        r = subprocess.run(
            [sys.executable, TRIAGE, "--json"],
            cwd=str(tmp_path), capture_output=True, text=True
        )
        assert r.returncode == 4

    def test_no_dlq_exits_1(self, tmp_path):
        self._append(tmp_path, "orchestrator", "phase_declared",
                     data={"workflow_id": "wf_t",
                           "phases": [{"name": "default", "order": 1, "required": True}]})
        self._append(tmp_path, "orchestrator", "phase_entered",
                     data={"phase": "default", "order": 1})
        r = subprocess.run(
            [sys.executable, TRIAGE, "--json"],
            cwd=str(tmp_path), capture_output=True, text=True
        )
        assert r.returncode == 1

    def test_dlq_task_classified_correctly(self, tmp_path):
        self._setup_dlq_task(tmp_path, reason="spec_unclear")
        r = subprocess.run(
            [sys.executable, TRIAGE, "--json"],
            cwd=str(tmp_path), capture_output=True, text=True
        )
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["total_dlq"] == 1
        assert len(out["buckets"]["input_issue"]) == 1
        assert out["buckets"]["input_issue"][0]["task_id"] == "t_001"

    def test_output_has_all_bucket_keys(self, tmp_path):
        self._setup_dlq_task(tmp_path)
        r = subprocess.run(
            [sys.executable, TRIAGE, "--json"],
            cwd=str(tmp_path), capture_output=True, text=True
        )
        out = json.loads(r.stdout)
        expected_buckets = {
            "input_issue", "worker_issue", "permission_issue",
            "code_issue", "quota_issue", "transient_issue", "unknown",
        }
        assert set(out["buckets"].keys()) == expected_buckets

    def test_suggested_action_present(self, tmp_path):
        self._setup_dlq_task(tmp_path, reason="spec_unclear")
        r = subprocess.run(
            [sys.executable, TRIAGE, "--json"],
            cwd=str(tmp_path), capture_output=True, text=True
        )
        out = json.loads(r.stdout)
        task_entry = out["buckets"]["input_issue"][0]
        assert "suggested_action" in task_entry
        assert len(task_entry["suggested_action"]) > 0

    def test_critical_task_has_critical_prefix(self, tmp_path):
        self._setup_dlq_task(tmp_path, reason="spec_unclear", tier="critical")
        r = subprocess.run(
            [sys.executable, TRIAGE, "--json"],
            cwd=str(tmp_path), capture_output=True, text=True
        )
        out = json.loads(r.stdout)
        task_entry = out["buckets"]["input_issue"][0]
        assert "[CRITICAL]" in task_entry["suggested_action"]
