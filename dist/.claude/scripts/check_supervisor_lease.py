#!/usr/bin/env python3
"""
check_supervisor_lease.py — Is anything watching this workflow?

A phase that stalls with no supervisor running waits for the operator to notice.
Measured: 63 min in one workflow (log ends on a successful `task_completed`, three
Task Contracts sitting ready on disk), 20 min in another (a retry scheduled for
23:20:02, log ends 23:19:36). In both, nothing was broken and nothing was coming.

Supervision exists (`supervisor_tick.py`, `/u-supervise`) but is opt-in and
out-of-band: it only runs if the operator started `/loop 5m /u-supervise <wf>` or
scheduled it. Nothing in the workflow records whether they did.

This check makes that state observable. **Advisory by design** — it reports, it
does not block. Requiring a lease would break the attended mode, where the
operator drives each phase and is the supervisor; that mode is how every measured
workflow ran. `recovery_tick.py` (SessionStart) already recovers a stalled
workflow at the next session, so the lease only shortens the wait — it is not what
makes recovery possible.

A lease is evidence in the log that a supervisor acted recently: an
`orchestrator_resume_requested` or `orchestrator_resumed` event inside the TTL.

Usage:
    python3 check_supervisor_lease.py [--workflow-id ID] [--ttl-seconds N] [--now ISO]

Output (stdout, JSON, exit 0 — advisory):
    {
      "leased": bool,
      "last_supervisor_event": "<iso>" | null,
      "age_seconds": int | null,
      "ttl_seconds": int,
      "workflow_id": "<id>" | null,
      "advice": "<one-liner>"
    }
"""
import argparse
import json
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CLAUDE_DIR / "lib"))

# Two /u-supervise ticks at the documented 5-minute interval. Anything older means
# the supervisor is not running, whatever was started earlier.
DEFAULT_TTL_SECONDS = 900


def evaluate(workflow_id: str | None, ttl_seconds: int, now: str | None) -> dict:
    from orch_core import EventType, now_iso, parse_iso, read_events, reduce_all

    now = now or now_iso()
    now_dt = parse_iso(now)

    state = reduce_all()
    wf = workflow_id or state.workflow_id

    supervisor_events = (
        EventType.ORCHESTRATOR_RESUME_REQUESTED.value,
        EventType.ORCHESTRATOR_RESUMED.value,
    )
    last_ts = None
    for event in read_events():
        if event.event_type not in supervisor_events:
            continue
        data = event.data or {}
        if wf and data.get("workflow_id") not in (None, wf):
            continue
        last_ts = event.ts

    age = None
    if last_ts:
        age = int((now_dt - parse_iso(last_ts)).total_seconds())
    leased = age is not None and age <= ttl_seconds

    if leased:
        advice = f"supervisor active ({age}s ago) — a stall resumes within its interval"
    elif age is not None:
        advice = (
            f"last supervisor activity was {age}s ago, past the {ttl_seconds}s TTL — "
            "treat this workflow as unsupervised"
        )
    else:
        advice = (
            "no supervisor activity in the log. A stall here waits for the next "
            f"session (recovery_tick) unless you start one: /loop 5m /u-supervise {wf or '<workflow_id>'}"
        )

    return {
        "leased": leased,
        "last_supervisor_event": last_ts,
        "age_seconds": age,
        "ttl_seconds": ttl_seconds,
        "workflow_id": wf,
        "advice": advice,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow-id", default=None)
    ap.add_argument("--ttl-seconds", type=int, default=DEFAULT_TTL_SECONDS)
    ap.add_argument("--now", default=None)
    args = ap.parse_args()
    print(json.dumps(evaluate(args.workflow_id, args.ttl_seconds, args.now)))


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError:
        print(json.dumps({
            "leased": False, "last_supervisor_event": None, "age_seconds": None,
            "ttl_seconds": DEFAULT_TTL_SECONDS, "workflow_id": None,
            "advice": "no orchestration log yet",
        }))
    except Exception as exc:  # noqa: BLE001 — advisory check must never block
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
    sys.exit(0)
