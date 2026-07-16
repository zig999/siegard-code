#!/usr/bin/env python3
"""Repro: two candidate log-poison vectors surviving v2.20.0.

Poison D — late GENUINE task_failed from a live worker landing on SCHEDULED
  (reaper synthesized stale failure + atomic retry; worker was alive and then
  genuinely failed). v2.20.0 reconciled only the task_completed path.

Poison C — double task_retried from two concurrent requeue_due_tasks.py ticks
  (TOCTOU outside the log lock, same pattern as fixed Poison B but for
  task_retried; no append precondition, no reducer absorb).

Also re-verifies the two v2.20.0 fixes still hold (control group).
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path("/home/siegfriedneto/projects/siegard-code")
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))
import orch_core  # noqa: E402

RESULTS = []


def fresh_orch():
    tmp = Path(tempfile.mkdtemp(prefix="orch_repro_"))
    orch_dir = tmp / ".orch"
    orch_dir.mkdir()
    orch_core.ORCH_DIR = orch_dir
    orch_core.LOG_PATH = orch_dir / "log.jsonl"
    orch_core.LOCK_PATH = orch_dir / "log.jsonl.lock"
    orch_core.STATE_DIR = orch_dir / "state"
    orch_core.DLQ_DIR = orch_dir / "dlq"
    orch_core.AUDIT_DIR = orch_dir / "audit"
    orch_core.METRICS_DIR = orch_dir / "metrics"
    orch_core.BLOBS_DIR = orch_dir / "blobs"
    orch_core.WORKERS_DIR = orch_dir / "workers"
    orch_core.CONFIG_PATH = orch_dir / "config.json"
    orch_core.ensure_dirs()


def seed_reaped_scheduled(tid="t1"):
    """task_created -> claimed -> reaper-synthesized task_failed -> atomic scheduled_retry.
    Leaves the task SCHEDULED with last_failure_reason=stale_timeout (synthesized)."""
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": "wf-x", "phases": [{"name": "dev", "order": 1, "required": True}]})
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": "dev", "order": 1, "workflow_id": "wf-x"})
    orch_core.append_event(
        agent="orchestrator", event_type="task_created", task_id=tid,
        data={"phase": "dev", "tier": "standard", "type": "impl", "spec": "s",
              "deps": [], "workflow_id": "wf-x"})
    orch_core.append_event(
        agent="orchestrator", event_type="task_claimed", task_id=tid,
        data={"phase": "dev", "worker_type": "w", "worker_id": "w1"})
    f = orch_core.append_event(
        agent="stale-monitor", event_type="task_failed", task_id=tid, attempt=1,
        data={"phase": "dev", "reason": "stale_timeout", "retryable": True})
    orch_core.append_event(
        agent="stale-monitor", event_type="task_scheduled_retry", task_id=tid, attempt=1,
        data={"phase": "dev", "next_retry_at": "2020-01-01T00:00:00.000Z",
              "backoff_seconds": 1, "previous_failure_seq": f.seq})
    return f


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, "OK"))
    except orch_core.IllegalTransition as e:
        RESULTS.append((name, f"POISONED: IllegalTransition: {e}"))
    except Exception as e:  # noqa: BLE001
        RESULTS.append((name, f"ERROR: {type(e).__name__}: {e}"))


# ---- Control 1 (fixed in v2.20.0): late task_completed on SCHEDULED reconciles
def control_late_completed():
    fresh_orch()
    seed_reaped_scheduled()
    orch_core.append_event(
        agent="w1", event_type="task_completed", task_id="t1", attempt=1,
        data={"phase": "dev", "artifacts": []})
    st = orch_core.reduce_all()
    assert st.tasks["t1"].status == orch_core.TaskStatus.COMPLETED
    assert any(a.get("reason") == "reconciled_false_positive_completion" for a in st.anomalies)


# ---- Control 2 (fixed in v2.20.0): duplicate task_scheduled_retry absorbed
def control_dup_scheduled_retry():
    fresh_orch()
    f = seed_reaped_scheduled()
    orch_core.append_event(
        agent="stale-monitor", event_type="task_scheduled_retry", task_id="t1", attempt=1,
        data={"phase": "dev", "next_retry_at": "2020-01-01T00:00:01.000Z",
              "backoff_seconds": 2, "previous_failure_seq": f.seq})
    st = orch_core.reduce_all()
    assert any(a.get("reason") == "duplicate_scheduled_retry_absorbed" for a in st.anomalies)


# ---- Poison D: late GENUINE task_failed from the live worker on SCHEDULED
def poison_d_late_failed():
    fresh_orch()
    seed_reaped_scheduled()
    # Worker was alive all along (false-positive stale), then genuinely failed:
    orch_core.append_event(
        agent="w1", event_type="task_failed", task_id="t1", attempt=1,
        data={"phase": "dev", "reason": "validation_failed", "retryable": True})
    orch_core.reduce_all()  # poisoned log raises here — and on EVERY future reduce


# ---- Poison C: double task_retried (two concurrent requeue ticks, TOCTOU)
def poison_c_double_retried():
    fresh_orch()
    seed_reaped_scheduled()
    # Both ticks reduce_all() concurrently, both see SCHEDULED due, both append:
    for _ in range(2):
        orch_core.append_event(
            agent="orchestrator", event_type="task_retried", task_id="t1", attempt=2,
            data={"phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": 4})
    orch_core.reduce_all()


# ---- Post-promotion stragglers (should be safe: attempt guard)
def straggler_after_promotion():
    fresh_orch()
    seed_reaped_scheduled()
    orch_core.append_event(
        agent="orchestrator", event_type="task_retried", task_id="t1", attempt=2,
        data={"phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": 4})
    orch_core.append_event(  # old worker's late failure, attempt=1 < attempts=2
        agent="w1", event_type="task_failed", task_id="t1", attempt=1,
        data={"phase": "dev", "reason": "validation_failed", "retryable": True})
    orch_core.append_event(  # old worker's late completion
        agent="w1", event_type="task_completed", task_id="t1", attempt=1,
        data={"phase": "dev", "artifacts": []})
    st = orch_core.reduce_all()
    assert st.tasks["t1"].status in (orch_core.TaskStatus.PENDING, orch_core.TaskStatus.READY)


check("CONTROL late task_completed on SCHEDULED (v2.20.0 fix)", control_late_completed)
check("CONTROL duplicate task_scheduled_retry (v2.20.0 fix)", control_dup_scheduled_retry)
check("POISON-D late genuine task_failed on SCHEDULED", poison_d_late_failed)
check("POISON-C double task_retried (concurrent requeue ticks)", poison_c_double_retried)
check("straggler events after promotion (attempt guard)", straggler_after_promotion)

for name, verdict in RESULTS:
    print(f"{verdict:70s} <- {name}")
