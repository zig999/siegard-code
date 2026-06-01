#!/usr/bin/env python3
"""Runtime stale-task reaper CLI (prod-hardening task 06).

Thin wrapper over orch_core.reap_stale_tasks(): scans RUNNING tasks past their
tier's stale threshold (Tier.default_stale_seconds) and emits
task_failed(reason=stale_timeout) from Python. Invoked by orchestrators at
dispatch Step 5.0 and by on_stop.py. Closes A2-F1 (stale_tasks() previously had
zero runtime callers — timeout enforcement was prompt-trusted).

Usage:
    check_stale.py            # reap stale tasks using the current time
    check_stale.py --now <ISO>  # override "now" (testing)

Output (stdout): {"stale_count": <int>, "failed": [<task_id>, ...]}
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from orch_core import reap_stale_tasks  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Reap stale RUNNING tasks (emit stale_timeout).")
    ap.add_argument("--now", default=None, help="ISO 8601 override for current time (testing).")
    args = ap.parse_args()
    reaped = reap_stale_tasks(args.now)
    print(json.dumps({"stale_count": len(reaped), "failed": reaped}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "detail": str(exc)}), file=sys.stderr)
        sys.exit(1)
