#!/usr/bin/env python3
"""Runtime stale-task reaper CLI (prod-hardening task 06).

Thin wrapper over orch_core.reap_stale_tasks(): scans RUNNING tasks past their
tier's stale threshold (Tier.default_stale_seconds) and emits
task_failed(reason=stale_timeout) from Python. Invoked by orchestrators at
dispatch Step 5.0 and by on_stop.py. Closes A2-F1 (stale_tasks() previously had
zero runtime callers — timeout enforcement was prompt-trusted).

Also surfaces the orthogonal stale-ORCHESTRATOR signal (Fix 4): the active phase
has non-terminal tasks but no orchestrator_heartbeat within the threshold. Since
this CLI runs at the live orchestrator's Step 5.0, surfacing the signal here is
the actionable, in-band hand-off that tells the orchestrator to resume dispatch
of the remaining tasks — no human read of last_error.json required. Detection
only: verify_and_recover stays manual (it is destructive).

Usage:
    check_stale.py            # reap stale tasks using the current time
    check_stale.py --now <ISO>  # override "now" (testing)

Output (stdout):
    {"stale_count": <int>, "failed": [<task_id>, ...], "stale_orchestrator": <dict|null>}
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from orch_core import (  # noqa: E402
    detect_stale_orchestrator,
    now_iso,
    reap_stale_tasks,
    reduce_all,
    read_events_filtered,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Reap stale RUNNING tasks (emit stale_timeout).")
    ap.add_argument("--now", default=None, help="ISO 8601 override for current time (testing).")
    args = ap.parse_args()
    now = args.now or now_iso()
    reaped = reap_stale_tasks(now)

    # Fix 4: detect a stalled orchestrator (non-terminal tasks, no heartbeat) and
    # surface it in-band so the live orchestrator resumes dispatch. Best-effort —
    # never let detection failure mask the reaper result.
    stale_orch = None
    try:
        state = reduce_all()
        events = list(read_events_filtered())
        stale_orch = detect_stale_orchestrator(state, events, now)
    except Exception:  # noqa: BLE001
        stale_orch = None

    print(json.dumps({
        "stale_count": len(reaped),
        "failed": reaped,
        "stale_orchestrator": stale_orch,
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "detail": str(exc)}), file=sys.stderr)
        sys.exit(1)
