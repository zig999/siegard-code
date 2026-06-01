#!/usr/bin/env python3
"""
recover_retry_sequence.py — Detects and repairs out-of-order retry events in the
orchestration log.

Failure pattern (emitted by orchestrator-sdd when missing the retry re-queue step):

    task_failed (seq N)
    task_claimed (seq N+k, attempt > 1)   ← ILLEGAL: task is FAILED, not READY
    task_completed (seq N+k+1)
    task_scheduled_retry (seq N+k+2)       ← should have been BEFORE claim
    task_retried (seq N+k+3)               ← should have been BEFORE claim
    task_claimed (seq N+k+4, duplicate)
    task_completed (seq N+k+5, duplicate)

Resolution: truncate from the first out-of-order event (the premature task_claimed),
archive the tail, and let the operator re-invoke /u-orchestrator to re-execute the
retry with correct event ordering.

Usage:
    python3 recover_retry_sequence.py [--project-dir PATH] [--dry-run] [--operator NAME]

Flags:
    --project-dir PATH   Override ORCH_PROJECT_DIR (default: current directory)
    --dry-run            Report the issue without modifying the log
    --operator NAME      Operator identity written into log_recovered event (default: operator)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _early_resolve_project_dir() -> Path:
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg in ("--project-dir", "-project-dir") and i < len(sys.argv):
            return Path(sys.argv[i + 1]).resolve()
        if arg.startswith("--project-dir="):
            return Path(arg.split("=", 1)[1]).resolve()
    env = os.environ.get("ORCH_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return Path(".").resolve()


_project_dir = _early_resolve_project_dir()
os.environ["ORCH_PROJECT_DIR"] = str(_project_dir)

_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (  # noqa: E402
    EventType,
    TaskStatus,
    CorruptedLogError,
    read_events,
    verify_and_recover,
)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _detect_premature_claims(project_dir: Path) -> list[dict]:
    """
    Scans the log for task_claimed events that precede the task_retried event
    after a task_failed — i.e., the claim is illegal because the retry sequence
    was not emitted first.

    Returns a list of incidents, each with:
        task_id       — affected task
        failed_seq    — seq of the task_failed event
        bad_claim_seq — seq of the premature task_claimed
        found_retried — whether task_retried was eventually emitted after the claim
    """
    import orch_core as _oc
    orch_dir = project_dir / ".orch"
    log = orch_dir / "log.jsonl"
    if not log.exists():
        return []

    _oc.ORCH_DIR = orch_dir
    _oc.LOG_PATH = log

    # Read all events, tracking per-task state
    # state: maps task_id -> {"status": str, "failed_seq": int, "attempts": int}
    task_state: dict[str, dict] = {}
    incidents: list[dict] = []

    try:
        events = list(read_events())
    except CorruptedLogError as exc:
        print(f"[warn] log parse error: {exc}", file=sys.stderr)
        events = []

    for ev in events:
        et = ev.event_type
        tid = ev.task_id

        if et == EventType.TASK_CREATED.value and tid:
            task_state[tid] = {"status": "pending", "failed_seq": None, "attempts": 0}

        elif et == EventType.TASK_CLAIMED.value and tid and tid in task_state:
            ts = task_state[tid]
            if ts["status"] == "failed":
                # Premature claim: task is FAILED but orchestrator tried to claim it
                # without emitting task_scheduled_retry + task_retried first.
                incidents.append({
                    "task_id": tid,
                    "failed_seq": ts["failed_seq"],
                    "bad_claim_seq": ev.seq,
                    "found_retried": False,
                })
            else:
                ts["status"] = "running"

        elif et == EventType.TASK_COMPLETED.value and tid and tid in task_state:
            task_state[tid]["status"] = "completed"

        elif et == EventType.TASK_FAILED.value and tid and tid in task_state:
            ts = task_state[tid]
            ts["status"] = "failed"
            ts["failed_seq"] = ev.seq
            ts["attempts"] = ev.attempt

        elif et == EventType.TASK_SCHEDULED_RETRY.value and tid and tid in task_state:
            task_state[tid]["status"] = "scheduled"

        elif et == EventType.TASK_RETRIED.value and tid and tid in task_state:
            task_state[tid]["status"] = "pending"
            # If there's a matching open incident for this task, mark it as having
            # received the retry events eventually (after the premature claim).
            for inc in incidents:
                if inc["task_id"] == tid and not inc["found_retried"]:
                    inc["found_retried"] = True
                    break

    return incidents


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------

def _recover(incident: dict, operator: str, dry_run: bool, yes: bool = False) -> None:
    task_id = incident["task_id"]
    bad_seq = incident["bad_claim_seq"]
    failed_seq = incident["failed_seq"]
    found_retried = incident["found_retried"]

    print(f"\nIncident: task={task_id!r}")
    print(f"  task_failed at seq {failed_seq}")
    print(f"  premature task_claimed at seq {bad_seq}")
    print(f"  retry events eventually emitted: {'yes' if found_retried else 'no'}")
    print()
    print(f"  Resolution: truncate log from seq {bad_seq}")
    print(f"  After truncation: task is in FAILED state — re-invoke /u-orchestrator")
    print(f"  to re-execute the retry with correct event ordering.")

    if dry_run:
        print("\n  [dry-run] No changes made.")
        return

    confirm = "yes" if yes else input(f"\n  Truncate log from seq {bad_seq}? [yes/no]: ").strip().lower()
    if confirm != "yes":
        print("  Aborted.")
        return

    try:
        recovery_event = verify_and_recover(
            from_seq=bad_seq,
            operator=operator,
            confirm=True,
        )
        print(f"\n  Log truncated. log_recovered event at seq {recovery_event.seq}.")
        print(f"  Corrupt tail archived to: {recovery_event.data.get('corrupt_file_path', '?')}")
        print(f"\n  Next step: re-invoke /u-orchestrator to resume the workflow.")
    except Exception as exc:
        print(f"\n  ERROR during recovery: {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Detect and repair out-of-order retry events in orchestration log"
    )
    p.add_argument("--project-dir", default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="Report without modifying the log")
    p.add_argument("--operator", default="operator",
                   help="Operator identity for log_recovered event")
    p.add_argument("--yes", action="store_true",
                   help="Non-interactive: confirm truncation without the input() prompt (task 11/A5-F5)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    project_dir = Path(args.project_dir).resolve() if args.project_dir else _project_dir

    import orch_core as _oc
    _oc.ORCH_DIR = project_dir / ".orch"
    _oc.LOG_PATH = _oc.ORCH_DIR / "log.jsonl"

    if not _oc.LOG_PATH.exists():
        print(json.dumps({"status": "ok", "message": "no log found", "incidents": 0}))
        return 0

    incidents = _detect_premature_claims(project_dir)

    if not incidents:
        print(json.dumps({"status": "ok", "message": "no out-of-order retry incidents found", "incidents": 0}))
        return 0

    print(json.dumps({
        "status": "incidents_found",
        "count": len(incidents),
        "incidents": [
            {
                "task_id": i["task_id"],
                "failed_seq": i["failed_seq"],
                "bad_claim_seq": i["bad_claim_seq"],
                "found_retried": i["found_retried"],
                "truncate_from": i["bad_claim_seq"],
            }
            for i in incidents
        ],
    }, indent=2))

    if args.dry_run:
        print("\n[dry-run] No changes made.")
        return 1

    # Process first incident only (truncating from the earliest bad seq covers all)
    # Sort by bad_claim_seq ascending to truncate from the earliest point.
    incidents_sorted = sorted(incidents, key=lambda x: x["bad_claim_seq"])
    _recover(incidents_sorted[0], operator=args.operator, dry_run=False, yes=args.yes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
