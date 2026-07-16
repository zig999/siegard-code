"""Adversarial repros for the v2.20.0 audit — run against dist/.claude/lib/orch_core.py."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/siegfriedneto/projects/siegard-code/dist/.claude/lib")
import orch_core


def fresh_orch():
    d = Path(tempfile.mkdtemp()) / ".orch"
    d.mkdir()
    orch_core.ORCH_DIR = d
    orch_core.LOG_PATH = d / "log.jsonl"
    orch_core.LOCK_PATH = d / "log.jsonl.lock"
    orch_core.STATE_DIR = d / "state"
    orch_core.DLQ_DIR = d / "dlq"
    orch_core.AUDIT_DIR = d / "audit"
    orch_core.METRICS_DIR = d / "metrics"
    orch_core.BLOBS_DIR = d / "blobs"
    orch_core.WORKERS_DIR = d / "workers"
    orch_core.CONFIG_PATH = d / "config.json"
    orch_core.ensure_dirs()


def ev(agent, et, tid=None, attempt=1, data=None):
    return orch_core.append_event(agent=agent, event_type=et, task_id=tid,
                                  attempt=attempt, data=data or {})


def seed_task(tid="t1", phase="dev", wf="wf"):
    ev("o", "phase_declared", data={"workflow_id": wf, "phases": [
        {"name": "dev", "order": 1, "required": True}]})
    ev("o", "phase_entered", data={"phase": phase, "order": 1, "workflow_id": wf})
    ev("o", "task_created", tid, data={"phase": phase, "tier": "standard",
                                       "type": "impl", "spec": "s", "deps": [],
                                       "workflow_id": wf})
    ev("o", "task_claimed", tid, data={"phase": phase, "worker_type": "w",
                                       "worker_id": "w1"})


print("=== GAP 1a: late GENUINE task_failed lands over SCHEDULED (post atomic reap) ===")
fresh_orch()
seed_task()
f = ev("stale-monitor", "task_failed", "t1", 1,
       {"phase": "dev", "reason": "stale_timeout", "retryable": True})   # reaper
ev("stale-monitor", "task_scheduled_retry", "t1", 1,
   {"phase": "dev", "next_retry_at": "2099-01-01T00:00:00Z",
    "backoff_seconds": 30, "previous_failure_seq": f.seq})               # atomic schedule
# live worker was actually alive and FAILED on its own (same attempt):
ev("w1", "task_failed", "t1", 1,
   {"phase": "dev", "reason": "validation_failed", "retryable": True})
try:
    orch_core.reduce_all()
    print("OK — reduce_all survived (no poison)")
except orch_core.IllegalTransition as e:
    print(f"POISONED: IllegalTransition: {e}")

print()
print("=== GAP 1b: dual schedulers, loser cites its own no-op'd failure seq ===")
fresh_orch()
seed_task()
f_reaper = ev("stale-monitor", "task_failed", "t1", 1,
              {"phase": "dev", "reason": "stale_timeout", "retryable": True})
# hook synthesizes its own task_failed (idempotent no-op in reducer, seq NOT in evidence)
f_hook = ev("w1", "task_failed", "t1", 1,
            {"phase": "dev", "reason": "worker_exited_without_terminal",
             "retryable": True})
# reaper's schedule lands first (cites f_reaper — in evidence)
ev("stale-monitor", "task_scheduled_retry", "t1", 1,
   {"phase": "dev", "next_retry_at": "2099-01-01T00:00:00Z",
    "backoff_seconds": 30, "previous_failure_seq": f_reaper.seq})
# hook's schedule lands second (cites f_hook — the no-op'd duplicate, NOT in evidence)
ev("stale-monitor", "task_scheduled_retry", "t1", 1,
   {"phase": "dev", "next_retry_at": "2099-01-01T00:00:00Z",
    "backoff_seconds": 30, "previous_failure_seq": f_hook.seq})
try:
    orch_core.reduce_all()
    print("OK — duplicate absorbed")
except orch_core.IllegalTransition as e:
    print(f"POISONED: IllegalTransition: {e}")

print()
print("=== GAP 4: concurrent requeue -> duplicate task_retried ===")
fresh_orch()
seed_task()
f = ev("w1", "task_failed", "t1", 1,
       {"phase": "dev", "reason": "validation_failed", "retryable": True})
ev("o", "task_scheduled_retry", "t1", 1,
   {"phase": "dev", "next_retry_at": "2020-01-01T00:00:00Z",
    "backoff_seconds": 30, "previous_failure_seq": f.seq})
# two orchestrators both saw the due SCHEDULED task and both appended task_retried
ev("orchestrator", "task_retried", "t1", 2,
   {"phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": f.seq + 1})
ev("orchestrator", "task_retried", "t1", 2,
   {"phase": "dev", "previous_attempt": 1, "scheduled_retry_seq": f.seq + 1})
try:
    orch_core.reduce_all()
    print("OK — duplicate task_retried absorbed")
except orch_core.IllegalTransition as e:
    print(f"POISONED: IllegalTransition: {e}")

print()
print("=== GAP 2: forward re-entry after return — review stays COMPLETED ===")
fresh_orch()
wf = "wf"
ev("o", "phase_declared", data={"workflow_id": wf, "phases": [
    {"name": "dev", "order": 1, "required": True},
    {"name": "review", "order": 2, "required": True}]})
ev("o", "phase_entered", data={"phase": "dev", "order": 1, "workflow_id": wf})
ev("o", "task_created", "d1", data={"phase": "dev", "tier": "standard",
                                    "type": "impl", "spec": "s", "deps": [],
                                    "workflow_id": wf})
ev("o", "task_claimed", "d1", data={"phase": "dev", "worker_type": "w", "worker_id": "w1"})
ev("w1", "task_completed", "d1", data={"phase": "dev", "artifacts": ["a"]})
ev("o", "phase_exit_approved", data={"phase": "dev", "criteria_met": ["c"],
                                     "next_phase": "review", "workflow_id": wf})
s = orch_core.reduce_all().last_seq
ev("o", "phase_transitioned", data={"from_phase": "dev", "to_phase": "review",
                                    "evidence_seq": s, "workflow_id": wf})
ev("o", "phase_entered", data={"phase": "review", "order": 2, "workflow_id": wf})
# review rejects -> creates a rework task in dev and returns
ev("orchestrator-review", "task_created", "d1_r1",
   data={"phase": "dev", "tier": "standard", "type": "impl", "spec": "fix",
         "deps": [], "workflow_id": wf})
s = orch_core.reduce_all().last_seq
ev("orchestrator-review", "phase_transitioned",
   data={"from_phase": "review", "to_phase": "dev", "evidence_seq": s,
         "workflow_id": wf})
st = orch_core.reduce_all()
print(f"after return: dev={st.phases['dev'].status.value} "
      f"review={st.phases['review'].status.value}  (fix works for first leg)")
# meta re-enters dev, rework completes, dev exits forward again
ev("o", "phase_entered", data={"phase": "dev", "order": 1, "workflow_id": wf})
ev("o", "task_claimed", "d1_r1", data={"phase": "dev", "worker_type": "w",
                                       "worker_id": "w2"})
ev("w2", "task_completed", "d1_r1", data={"phase": "dev", "artifacts": ["a2"]})
ev("o", "phase_exit_approved", data={"phase": "dev", "criteria_met": ["c"],
                                     "next_phase": "review", "workflow_id": wf})
s = orch_core.reduce_all().last_seq
ev("o", "phase_transitioned", data={"from_phase": "dev", "to_phase": "review",
                                    "evidence_seq": s, "workflow_id": wf})
st = orch_core.reduce_all()
print(f"after rework forward hop: dev={st.phases['dev'].status.value} "
      f"review={st.phases['review'].status.value}")
pending = [p.name for p in st.phases.values()
           if p.status == orch_core.PhaseStatus.PENDING]
phases_payload = [{"name": n, "order": p.order, "required": p.required,
                   "status": p.status.value} for n, p in st.phases.items()]
run_status = orch_core._m3_derive_run_status(
    {"raw_run_status": st.run_status, "phases": phases_payload})
print(f"meta 'lowest order pending' candidates: {pending}")
print(f"M3 run_status: {run_status}  <-- review re-pass was SKIPPED; "
      f"rework never re-reviewed")

print()
print("=== GAP 6: _workflow_is_terminal with zero required phases ===")
fresh_orch()
ev("o", "phase_declared", data={"workflow_id": "wf", "phases": [
    {"name": "dev", "order": 1, "required": False}]})
ev("o", "phase_entered", data={"phase": "dev", "order": 1, "workflow_id": "wf"})
st = orch_core.reduce_all()
sys.path.insert(0, "/home/siegfriedneto/projects/siegard-code/dist/.claude/hooks")
import importlib
on_stop = importlib.import_module("on_stop")
phases_payload = [{"name": n, "order": p.order, "required": p.required,
                   "status": p.status.value} for n, p in st.phases.items()]
m3 = orch_core._m3_derive_run_status({"raw_run_status": st.run_status,
                                      "phases": phases_payload})
print(f"phase dev ACTIVE, required=False: _workflow_is_terminal="
      f"{on_stop._workflow_is_terminal(st)}  M3 run_status={m3}")
