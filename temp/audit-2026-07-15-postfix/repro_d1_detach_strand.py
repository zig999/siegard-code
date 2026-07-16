#!/usr/bin/env python3
"""Repro D1 — v2.19 detach on-ramp strand.

Log state at the exact detach hand-off moment (meta returned phase_advanced):
  phase sdd COMPLETED (transitioned), phase dev PENDING, current_phase=None.
Human replied 'loop' -> /loop 5m /u-supervise wf -> entry command stopped.
Every future supervisor tick must decide 'resume' for the workflow to proceed.
This shows decide() no-ops forever -> infinite stall under active supervision.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path("/home/siegfriedneto/projects/siegard-code")
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "scripts"))
import orch_core  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="orch_d1_"))
orch_dir = tmp / ".orch"
orch_dir.mkdir()
for attr, sub in [("ORCH_DIR", ""), ("LOG_PATH", "log.jsonl"), ("LOCK_PATH", "log.jsonl.lock"),
                  ("STATE_DIR", "state"), ("DLQ_DIR", "dlq"), ("AUDIT_DIR", "audit"),
                  ("METRICS_DIR", "metrics"), ("BLOBS_DIR", "blobs"), ("WORKERS_DIR", "workers"),
                  ("CONFIG_PATH", "config.json")]:
    setattr(orch_core, attr, orch_dir / sub if sub else orch_dir)
orch_core.ensure_dirs()

ap = orch_core.append_event
ap(agent="orchestrator", event_type="phase_declared",
   data={"workflow_id": "wf-d1", "phases": [
       {"name": "sdd", "order": 1, "required": True},
       {"name": "dev", "order": 2, "required": True}]})
ap(agent="orchestrator", event_type="phase_entered",
   data={"phase": "sdd", "order": 1, "workflow_id": "wf-d1"})
ap(agent="orchestrator", event_type="task_created", task_id="s1",
   data={"phase": "sdd", "tier": "standard", "type": "spec-writer", "spec": "s",
         "deps": [], "workflow_id": "wf-d1"})
ap(agent="orchestrator", event_type="task_claimed", task_id="s1",
   data={"phase": "sdd", "worker_type": "w", "worker_id": "w1"})
ap(agent="w1", event_type="task_completed", task_id="s1", attempt=1,
   data={"phase": "sdd", "artifacts": []})
crit = ap(agent="orchestrator-sdd", event_type="phase_exit_criterion_met",
          data={"phase": "sdd", "criterion": "all_done", "evidence_seq": 5})
appr = ap(agent="orchestrator-sdd", event_type="phase_exit_approved",
          data={"phase": "sdd", "criteria_met": ["all_done"], "next_phase": "dev",
                "workflow_id": "wf-d1"})
ap(agent="orchestrator-sdd", event_type="phase_transitioned",
   data={"from_phase": "sdd", "to_phase": "dev", "evidence_seq": appr.seq,
         "workflow_id": "wf-d1"})
# ^ meta now outputs phase_advanced and STOPS (I5). Human replies 'loop'.
#   Entry command configures /loop 5m /u-supervise and STOPS. From here on,
#   the ONLY driver is supervisor_tick.decide() once per tick:

import supervisor_tick  # noqa: E402

state = orch_core.reduce_all()
events = list(orch_core.read_events())
print(f"current_phase={state.current_phase!r}  "
      f"phases={{{', '.join(f'{n}:{p.status.value}' for n, p in state.phases.items())}}}")

decision = supervisor_tick.decide(
    state, events, now=orch_core.now_iso(), threshold=900,
    policy={"enabled": True, "max_auto_resumes": 3, "cooldown_seconds": 300,
            "in_flight_ttl_seconds": 900},
    stale_config={})
print(f"tick #1: {decision}")

# Simulate hours of ticks — the decision is time-independent in this state:
decision_late = supervisor_tick.decide(
    state, events, now="2027-01-01T00:00:00.000Z", threshold=900,
    policy={"enabled": True}, stale_config={})
print(f"tick after arbitrarily long wait: {decision_late}")

stranded = (not decision.get("resume") and not decision.get("escalate")
            and not decision_late.get("resume") and not decision_late.get("escalate"))
print("VERDICT:", "D1 CONFIRMED — supervisor no-ops forever; dev never enters"
      if stranded else "not reproduced")
