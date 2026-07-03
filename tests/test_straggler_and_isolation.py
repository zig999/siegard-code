"""Hardening fixes for the orchestration engine (handoff 2026-06-16).

Fix 1 — superseded-attempt straggler: a late task_completed/task_failed carrying an
        OLDER event.attempt than task.attempts is an idempotent no-op, not fatal.
Fix 2 — reduce_workflow: per-workflow reduction so one corrupted workflow cannot
        block deriving the others (reduce_all is global and aborts on first illegal).
Fix 4 — detect_stale_orchestrator: an active phase with non-terminal tasks but no
        recent orchestrator_heartbeat is detected and surfaced as an actionable signal.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
REDUCE = ROOT / "dist" / ".claude" / "skills" / "orch-state" / "scripts" / "reduce.py"
CHECK = ROOT / "dist" / ".claude" / "scripts" / "check_stale.py"
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enter_phase(make_event, phase="dev", order=1, wf="wf"):
    make_event("phase_declared", data={
        "workflow_id": wf,
        "phases": [{"name": phase, "order": order, "required": True}],
    })
    make_event("phase_entered", data={"phase": phase, "order": order, "workflow_id": wf})


def _create(make_event, task_id, phase="dev"):
    make_event("task_created", task_id=task_id, data={
        "phase": phase, "tier": "standard", "type": "impl", "spec": "s", "deps": [],
    })


def _claim(make_event, task_id, attempt, phase="dev"):
    make_event("task_claimed", task_id=task_id, attempt=attempt, data={
        "phase": phase, "worker_type": "u-be-developer", "worker_id": f"w{attempt}",
    })


def _fail(make_event, task_id, attempt, phase="dev"):
    make_event("task_failed", task_id=task_id, attempt=attempt, data={
        "phase": phase, "reason": "internal_error", "retryable": True,
    })


def _schedule_retry(make_event, task_id, prev_seq, phase="dev"):
    make_event("task_scheduled_retry", task_id=task_id, data={
        "phase": phase, "next_retry_at": _now(),
        "backoff_seconds": 30.0, "previous_failure_seq": prev_seq,
    })


def _retry(make_event, task_id, attempt, sched_seq, phase="dev"):
    make_event("task_retried", task_id=task_id, attempt=attempt, data={
        "phase": phase, "previous_attempt": attempt - 1, "scheduled_retry_seq": sched_seq,
    })


def _complete(make_event, task_id, attempt, phase="dev"):
    make_event("task_completed", task_id=task_id, attempt=attempt, data={
        "phase": phase, "artifacts": [],
    })


# ---------------------------------------------------------------------------
# T1 — Fix 1: superseded-attempt straggler
# ---------------------------------------------------------------------------

class TestStragglerTolerance:

    def test_late_completed_for_superseded_attempt_is_noop(self, orch_dir, make_event):
        import orch_core
        _enter_phase(make_event)
        _create(make_event, "t1")
        _claim(make_event, "t1", 1)
        _fail(make_event, "t1", 1)          # FAILED, attempts=1
        _schedule_retry(make_event, "t1", prev_seq=4)
        _retry(make_event, "t1", 2, sched_seq=5)  # PENDING->READY, attempts=2
        # LATE: attempt-1 worker finishes and emits now (task already on attempt 2).
        _complete(make_event, "t1", 1)

        state = orch_core.reduce_all()  # must NOT raise IllegalTransition
        # Straggler ignored — task stays on attempt 2, not completed.
        assert state.tasks["t1"].status in (orch_core.TaskStatus.READY, orch_core.TaskStatus.PENDING)
        assert state.tasks["t1"].attempts == 2

    def test_new_attempt_completes_normally_after_straggler(self, orch_dir, make_event):
        import orch_core
        _enter_phase(make_event)
        _create(make_event, "t1")
        _claim(make_event, "t1", 1)
        _fail(make_event, "t1", 1)
        _schedule_retry(make_event, "t1", prev_seq=4)
        _retry(make_event, "t1", 2, sched_seq=5)
        _complete(make_event, "t1", 1)      # straggler — no-op
        _claim(make_event, "t1", 2)
        _complete(make_event, "t1", 2)      # legitimate completion of attempt 2

        state = orch_core.reduce_all()
        assert state.tasks["t1"].status == orch_core.TaskStatus.COMPLETED

    def test_late_failed_for_superseded_attempt_is_noop(self, orch_dir, make_event):
        import orch_core
        _enter_phase(make_event)
        _create(make_event, "t1")
        _claim(make_event, "t1", 1)
        _fail(make_event, "t1", 1)
        _schedule_retry(make_event, "t1", prev_seq=4)
        _retry(make_event, "t1", 2, sched_seq=5)
        _claim(make_event, "t1", 2)         # RUNNING on attempt 2
        # LATE: attempt-1 worker reports failure now — must not corrupt attempt 2.
        _fail(make_event, "t1", 1)

        state = orch_core.reduce_all()      # must NOT raise
        assert state.tasks["t1"].status == orch_core.TaskStatus.RUNNING
        assert state.tasks["t1"].attempts == 2

    def test_happy_path_first_completion_still_processed(self, orch_dir, make_event):
        """Regression guard: attempts defaults to 0, so the first completion
        (event.attempt=1) must NOT be swallowed by the straggler guard."""
        import orch_core
        _enter_phase(make_event)
        _create(make_event, "t1")
        _claim(make_event, "t1", 1)
        _complete(make_event, "t1", 1)
        state = orch_core.reduce_all()
        assert state.tasks["t1"].status == orch_core.TaskStatus.COMPLETED


# ---------------------------------------------------------------------------
# T2 — Fix 2: per-workflow isolation
# ---------------------------------------------------------------------------

class TestWorkflowIsolation:

    def _seed_two_workflows(self, make_event):
        # Workflow A — healthy, shares the phase name "dev" with B.
        _enter_phase(make_event, phase="dev", wf="A")
        _create(make_event, "tA")
        _claim(make_event, "tA", 1)
        _complete(make_event, "tA", 1)
        # Workflow B — forged illegal transition: completed without claim (READY).
        _enter_phase(make_event, phase="dev", wf="B")
        _create(make_event, "tB")
        _complete(make_event, "tB", 1)   # illegal: task is READY, never claimed

    def test_global_reduce_is_blocked_by_corrupt_workflow(self, orch_dir, make_event):
        import orch_core
        self._seed_two_workflows(make_event)
        try:
            orch_core.reduce_all()
            assert False, "expected IllegalTransition from workflow B"
        except orch_core.IllegalTransition:
            pass

    def test_healthy_workflow_reduces_despite_corrupt_sibling(self, orch_dir, make_event):
        import orch_core
        self._seed_two_workflows(make_event)
        state = orch_core.reduce_workflow("A")     # must NOT raise
        assert state.tasks["tA"].status == orch_core.TaskStatus.COMPLETED
        assert "tB" not in state.tasks               # B's events excluded

    def test_corrupt_workflow_still_raises_when_reduced_in_isolation(self, orch_dir, make_event):
        import orch_core
        self._seed_two_workflows(make_event)
        try:
            orch_core.reduce_workflow("B")
            assert False, "expected IllegalTransition scoped to workflow B"
        except orch_core.IllegalTransition:
            pass

    def test_task_bound_attribution_survives_interleaving(self, orch_dir, make_event):
        """5-a: a task_created carrying data.workflow_id binds the task; later
        events for it attribute to that workflow even after another workflow's
        phase_declared interleaves (positional fallback would misattribute)."""
        import orch_core
        _enter_phase(make_event, phase="dev", wf="A")
        make_event("task_created", task_id="dev_A_tc_001", data={
            "phase": "dev", "tier": "standard", "type": "impl", "spec": "s",
            "deps": [], "workflow_id": "A",
        })
        _claim(make_event, "dev_A_tc_001", 1)
        # Workflow B declares BEFORE A's task completes (interleaving).
        _enter_phase(make_event, phase="dev", wf="B")
        _complete(make_event, "dev_A_tc_001", 1)   # positionally under B, bound to A

        state_a = orch_core.reduce_workflow("A")
        assert state_a.tasks["dev_A_tc_001"].status == orch_core.TaskStatus.COMPLETED
        state_b = orch_core.reduce_workflow("B")
        assert "dev_A_tc_001" not in state_b.tasks

    def test_positional_fallback_preserved_for_legacy_logs(self, orch_dir, make_event):
        """Task events without data.workflow_id and no binding keep the legacy
        positional attribution (events between phase_declared boundaries)."""
        import orch_core
        self._seed_two_workflows(make_event)
        state = orch_core.reduce_workflow("A")
        assert "tA" in state.tasks and "tB" not in state.tasks

    def test_cli_workflow_flag_isolates(self, orch_dir, make_event):
        self._seed_two_workflows(make_event)
        env = {**os.environ, "ORCH_PROJECT_DIR": str(orch_dir)}
        # --workflow A succeeds
        p = subprocess.run([sys.executable, str(REDUCE), "--workflow", "A"],
                           capture_output=True, text=True, env=env)
        assert p.returncode == 0, p.stderr
        out = json.loads(p.stdout)
        assert out["tasks"]["tA"]["status"] == "completed"
        # default global reduce reports the illegal transition
        p2 = subprocess.run([sys.executable, str(REDUCE)],
                            capture_output=True, text=True, env=env)
        assert p2.returncode == 1
        assert json.loads(p2.stdout)["reason"] == "illegal_transition"


# ---------------------------------------------------------------------------
# T4 — Fix 4: stale orchestrator detection
# ---------------------------------------------------------------------------

class TestStaleOrchestratorDetection:

    def test_active_phase_with_pending_tasks_no_heartbeat_is_stale(self, orch_dir, make_event):
        import orch_core
        _enter_phase(make_event, phase="dev", wf="wf")
        _create(make_event, "t1")   # READY, never claimed — orchestrator died
        state = orch_core.reduce_all()
        events = list(orch_core.read_events_filtered())
        diag = orch_core.detect_stale_orchestrator(state, events, _now())
        assert diag is not None
        assert diag["stale_orchestrator"] == "dev"
        assert diag["pending_task_ids"] == ["t1"]
        assert diag["command"] == "/u-orchestrator"

    def test_recent_heartbeat_is_not_stale(self, orch_dir, make_event):
        import orch_core
        _enter_phase(make_event, phase="dev", wf="wf")
        _create(make_event, "t1")
        make_event("orchestrator_heartbeat", data={"phase": "dev"})
        state = orch_core.reduce_all()
        events = list(orch_core.read_events_filtered())
        assert orch_core.detect_stale_orchestrator(state, events, _now()) is None

    def test_stale_heartbeat_beyond_threshold_is_stale(self, orch_dir, make_event):
        import orch_core
        _enter_phase(make_event, phase="dev", wf="wf")
        _create(make_event, "t1")
        make_event("orchestrator_heartbeat", data={"phase": "dev"})
        state = orch_core.reduce_all()
        events = list(orch_core.read_events_filtered())
        future = (datetime.now(timezone.utc)
                  + timedelta(seconds=orch_core.ORCHESTRATOR_STALE_SECONDS + 60)).isoformat()
        diag = orch_core.detect_stale_orchestrator(state, events, future)
        assert diag is not None and diag["stale_orchestrator"] == "dev"

    def test_all_terminal_is_not_stale(self, orch_dir, make_event):
        import orch_core
        _enter_phase(make_event, phase="dev", wf="wf")
        _create(make_event, "t1")
        _claim(make_event, "t1", 1)
        _complete(make_event, "t1", 1)
        state = orch_core.reduce_all()
        events = list(orch_core.read_events_filtered())
        assert orch_core.detect_stale_orchestrator(state, events, _now()) is None

    def test_check_stale_cli_surfaces_signal(self, orch_dir, make_event):
        _enter_phase(make_event, phase="dev", wf="wf")
        _create(make_event, "t1")   # READY, no heartbeat
        env = {**os.environ, "ORCH_PROJECT_DIR": str(orch_dir)}
        p = subprocess.run([sys.executable, str(CHECK)],
                           capture_output=True, text=True, env=env)
        assert p.returncode == 0, p.stderr
        out = json.loads(p.stdout)
        assert out["stale_orchestrator"] is not None
        assert out["stale_orchestrator"]["pending_task_ids"] == ["t1"]
