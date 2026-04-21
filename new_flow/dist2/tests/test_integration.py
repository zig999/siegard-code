"""
Integration tests: full round-trip through the log.

Each test writes events via append_event (real I/O, hash chain, locking),
then reads and reduces via reduce_all() or read_events(). Nothing is mocked.

Scenarios:
  I.1 - Happy path: full task lifecycle in one phase
  I.2 - Retry cycle: failed → scheduled → retried → completed
  I.3 - DLQ path: failed non-retryable → dlq
  I.4 - Dependency chain: t_002 waits for t_001
  I.5 - Phase transition: sdd → dev, tasks promoted correctly
  I.6 - Hash chain survives the full workflow (verify_chain passes)
  I.7 - Blob payload survives round-trip through log and reducer
"""
import pytest
import orch_core
from orch_core import (
    append_event,
    read_events,
    reduce_all,
    verify_chain,
    load_blob_data,
    is_blob_ref,
    TaskStatus,
    PhaseStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _declare_phase(name="dev", order=1):
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": "wf_integration",
        "phases": [{"name": name, "order": order, "required": True}],
    })
    append_event("orchestrator", "phase_entered", data={"phase": name, "order": order})


def _create_task(task_id, phase="dev", deps=None):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": phase, "tier": "standard", "type": "impl",
        "spec": f"spec for {task_id}", "deps": deps or [],
    })


def _claim(task_id, attempt=1, worker="w_001", phase="dev"):
    append_event("worker", "task_claimed", task_id=task_id, attempt=attempt, data={
        "phase": phase, "worker_type": "impl", "worker_id": worker,
    })


def _complete(task_id, attempt=1, phase="dev"):
    append_event("worker", "task_completed", task_id=task_id, attempt=attempt, data={
        "phase": phase, "artifacts": [f"{task_id}.out"], "summary": "done",
    })


def _fail(task_id, attempt=1, retryable=True, phase="dev"):
    append_event("worker", "task_failed", task_id=task_id, attempt=attempt, data={
        "phase": phase, "reason": "timeout", "retryable": retryable,
    })


# ---------------------------------------------------------------------------
# I.1 — Happy path: full task lifecycle
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_full_lifecycle_state(self, tmp_orch):
        """I.1: orchestrator creates task, worker claims and completes it."""
        _declare_phase()
        _create_task("t_0001")
        _claim("t_0001", attempt=1)
        _complete("t_0001", attempt=1)

        state = reduce_all()

        task = state.tasks["t_0001"]
        assert task.status == TaskStatus.COMPLETED
        assert task.worker_id == "w_001"
        assert task.claimed_at is not None

    def test_full_lifecycle_log_has_all_events(self, tmp_orch):
        """I.1: log contains exactly the events we wrote."""
        _declare_phase()
        _create_task("t_0001")
        _claim("t_0001")
        _complete("t_0001")

        events = list(read_events())
        event_types = [e.event_type for e in events]
        assert "phase_declared" in event_types
        assert "phase_entered" in event_types
        assert "task_created" in event_types
        assert "task_claimed" in event_types
        assert "task_completed" in event_types

    def test_full_lifecycle_seqs_monotonic(self, tmp_orch):
        """I.1: seq numbers are strictly increasing after full lifecycle."""
        _declare_phase()
        _create_task("t_0001")
        _claim("t_0001")
        _complete("t_0001")

        seqs = [e.seq for e in read_events()]
        assert seqs == sorted(seqs)
        assert len(seqs) == len(set(seqs))

    def test_multiple_tasks_all_completed(self, tmp_orch):
        """I.1: three tasks created and completed, all show completed state."""
        _declare_phase()
        for i in range(1, 4):
            _create_task(f"t_{i:04d}")
        for i in range(1, 4):
            _claim(f"t_{i:04d}", attempt=1, worker=f"w_{i:03d}")
            _complete(f"t_{i:04d}", attempt=1)

        state = reduce_all()
        for i in range(1, 4):
            assert state.tasks[f"t_{i:04d}"].status == TaskStatus.COMPLETED

    def test_phase_is_active_in_state(self, tmp_orch):
        """I.1: phase_entered → state.current_phase is set."""
        _declare_phase("dev", order=1)
        state = reduce_all()
        assert state.current_phase == "dev"
        assert state.phases["dev"].status == PhaseStatus.ACTIVE


# ---------------------------------------------------------------------------
# I.2 — Retry cycle
# ---------------------------------------------------------------------------

class TestRetryCycle:
    def test_retry_full_cycle_completes(self, tmp_orch):
        """I.2: task fails, gets retried, then completes."""
        _declare_phase()
        _create_task("t_0001")
        _claim("t_0001", attempt=1)
        _fail("t_0001", attempt=1, retryable=True)

        append_event("orchestrator", "task_scheduled_retry", task_id="t_0001", data={
            "phase": "dev", "next_retry_at": "2026-04-21T01:00:00Z",
            "backoff_seconds": 30, "previous_failure_seq": 4,
        })
        append_event("orchestrator", "task_retried", task_id="t_0001", attempt=2, data={
            "phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": 5,
        })
        _claim("t_0001", attempt=2, worker="w_002")
        _complete("t_0001", attempt=2)

        state = reduce_all()
        task = state.tasks["t_0001"]
        assert task.status == TaskStatus.COMPLETED
        assert task.attempts == 2

    def test_retry_intermediate_state_was_scheduled(self, tmp_orch):
        """I.2: after task_scheduled_retry, state is 'scheduled'."""
        _declare_phase()
        _create_task("t_0001")
        _claim("t_0001", attempt=1)
        _fail("t_0001", attempt=1, retryable=True)
        append_event("orchestrator", "task_scheduled_retry", task_id="t_0001", data={
            "phase": "dev", "next_retry_at": "2026-04-21T01:00:00Z",
            "backoff_seconds": 30, "previous_failure_seq": 4,
        })

        # Read partial state — only up to this point
        from orch_core import apply_event, OrchState, Event
        state = reduce_all()
        assert state.tasks["t_0001"].status == TaskStatus.SCHEDULED
        assert state.tasks["t_0001"].next_retry_at == "2026-04-21T01:00:00Z"


# ---------------------------------------------------------------------------
# I.3 — DLQ path
# ---------------------------------------------------------------------------

class TestDLQPath:
    def test_non_retryable_ends_in_dlq(self, tmp_orch):
        """I.3: worker fails with retryable=false → orchestrator sends to DLQ."""
        _declare_phase()
        _create_task("t_0001")
        _claim("t_0001", attempt=1)
        _fail("t_0001", attempt=1, retryable=False)
        append_event("orchestrator", "task_dlq", task_id="t_0001", data={
            "phase": "dev", "reason": "non_retryable", "last_error": "exit code 1",
        })

        state = reduce_all()
        assert state.tasks["t_0001"].status == TaskStatus.DLQ

    def test_dlq_task_does_not_block_other_tasks(self, tmp_orch):
        """I.3: DLQ task and independent task coexist correctly."""
        _declare_phase()
        _create_task("t_0001")
        _create_task("t_0002")
        _claim("t_0001", attempt=1, worker="w_001")
        _fail("t_0001", attempt=1, retryable=False)
        append_event("orchestrator", "task_dlq", task_id="t_0001", data={
            "phase": "dev", "reason": "non_retryable", "last_error": "x",
        })
        _claim("t_0002", attempt=1, worker="w_002")
        _complete("t_0002", attempt=1)

        state = reduce_all()
        assert state.tasks["t_0001"].status == TaskStatus.DLQ
        assert state.tasks["t_0002"].status == TaskStatus.COMPLETED


# ---------------------------------------------------------------------------
# I.4 — Dependency chain
# ---------------------------------------------------------------------------

class TestDependencyChain:
    def test_dependent_task_ready_after_dep_completes(self, tmp_orch):
        """I.4: t_0002 depends on t_0001; becomes ready after t_0001 completes."""
        _declare_phase()
        _create_task("t_0001", deps=[])
        _create_task("t_0002", deps=["t_0001"])

        state = reduce_all()
        assert state.tasks["t_0001"].status == TaskStatus.READY
        assert state.tasks["t_0002"].status == TaskStatus.PENDING

        _claim("t_0001", attempt=1)
        _complete("t_0001", attempt=1)

        state = reduce_all()
        assert state.tasks["t_0001"].status == TaskStatus.COMPLETED
        assert state.tasks["t_0002"].status == TaskStatus.READY

    def test_chain_of_three(self, tmp_orch):
        """I.4: t_003 depends on t_002 depends on t_001 — sequential promotion."""
        _declare_phase()
        _create_task("t_0001", deps=[])
        _create_task("t_0002", deps=["t_0001"])
        _create_task("t_0003", deps=["t_0002"])

        _claim("t_0001")
        _complete("t_0001")

        state = reduce_all()
        assert state.tasks["t_0002"].status == TaskStatus.READY
        assert state.tasks["t_0003"].status == TaskStatus.PENDING

        _claim("t_0002")
        _complete("t_0002")

        state = reduce_all()
        assert state.tasks["t_0003"].status == TaskStatus.READY


# ---------------------------------------------------------------------------
# I.5 — Phase transition
# ---------------------------------------------------------------------------

class TestPhaseTransition:
    def test_tasks_promoted_after_phase_transition(self, tmp_orch):
        """I.5: task in dev phase is pending until dev activates."""
        append_event("orchestrator", "phase_declared", data={
            "workflow_id": "wf_integration",
            "phases": [
                {"name": "sdd", "order": 1, "required": True},
                {"name": "dev", "order": 2, "required": True},
            ],
        })
        append_event("orchestrator", "phase_entered", data={"phase": "sdd", "order": 1})
        _create_task("t_spec", phase="sdd", deps=[])
        _create_task("t_impl", phase="dev", deps=[])

        state = reduce_all()
        assert state.tasks["t_spec"].status == TaskStatus.READY
        assert state.tasks["t_impl"].status == TaskStatus.PENDING  # dev not active yet

        # Complete sdd work and transition
        _claim("t_spec", phase="sdd")
        _complete("t_spec", phase="sdd")
        append_event("orchestrator", "phase_exit_approved", data={
            "phase": "sdd", "criteria_met": ["all_done"], "next_phase": "dev",
        })
        append_event("orchestrator", "phase_transitioned", data={
            "from_phase": "sdd", "to_phase": "dev", "evidence_seq": 1,
        })
        append_event("orchestrator", "phase_entered", data={"phase": "dev", "order": 2})

        state = reduce_all()
        assert state.phases["sdd"].status == PhaseStatus.COMPLETED
        assert state.phases["dev"].status == PhaseStatus.ACTIVE
        assert state.tasks["t_impl"].status == TaskStatus.READY


# ---------------------------------------------------------------------------
# I.6 — Hash chain integrity survives full workflow
# ---------------------------------------------------------------------------

class TestHashChainIntegrity:
    def test_verify_chain_passes_after_full_workflow(self, tmp_orch):
        """I.6: verify_chain is OK after a realistic multi-event workflow."""
        _declare_phase()
        for i in range(1, 6):
            _create_task(f"t_{i:04d}")
        for i in range(1, 4):
            _claim(f"t_{i:04d}", attempt=1, worker=f"w_{i:03d}")
            _complete(f"t_{i:04d}", attempt=1)
        _claim("t_0004", attempt=1)
        _fail("t_0004", attempt=1, retryable=False)
        append_event("orchestrator", "task_dlq", task_id="t_0004", data={
            "phase": "dev", "reason": "non_retryable", "last_error": "x",
        })

        result = verify_chain(mode="strict")
        assert result.ok is True
        assert result.events_verified >= 10

    def test_verify_chain_audit_also_passes(self, tmp_orch):
        """I.6: audit mode also reports no errors on intact log."""
        _declare_phase()
        _create_task("t_0001")
        _claim("t_0001")
        _complete("t_0001")

        result = verify_chain(mode="audit")
        assert result.ok is True


# ---------------------------------------------------------------------------
# I.7 — Blob payload round-trip through log and reducer
# ---------------------------------------------------------------------------

class TestBlobRoundTrip:
    def test_large_payload_survives_reduce_all(self, tmp_orch):
        """I.7: task with large spec (externalized blob) is correctly reduced."""
        large_spec = "x" * 10_000
        _declare_phase()
        append_event("orchestrator", "task_created", task_id="t_0001", data={
            "phase": "dev", "tier": "standard", "type": "impl",
            "spec": large_spec, "deps": [],
        })
        _claim("t_0001")
        _complete("t_0001")

        state = reduce_all()
        assert state.tasks["t_0001"].status == TaskStatus.COMPLETED

    def test_large_payload_blob_ref_in_log(self, tmp_orch):
        """I.7: event in log has _blob_ref when payload is large."""
        large_spec = "x" * 10_000
        _declare_phase()
        ev = append_event("orchestrator", "task_created", task_id="t_0001", data={
            "phase": "dev", "tier": "standard", "type": "impl",
            "spec": large_spec, "deps": [],
        })
        assert is_blob_ref(ev.data)

    def test_large_payload_recoverable_via_load_blob_data(self, tmp_orch):
        """I.7: original data is recoverable from the event after reduce."""
        large_spec = "y" * 10_000
        _declare_phase()
        ev = append_event("orchestrator", "task_created", task_id="t_0001", data={
            "phase": "dev", "tier": "standard", "type": "impl",
            "spec": large_spec, "deps": [],
        })

        # Read the event back from log and recover full data
        events = list(read_events())
        task_ev = next(e for e in events if e.event_type == "task_created")
        recovered = load_blob_data(task_ev)
        assert recovered["spec"] == large_spec
