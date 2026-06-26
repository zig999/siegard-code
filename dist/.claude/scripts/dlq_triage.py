#!/usr/bin/env python3
"""
dlq_triage.py — Classifies DLQ tasks into actionable buckets.

Usage:
    python3 .claude/scripts/dlq_triage.py [--task-id <id>] [--json]

Options:
    --task-id   Triage a specific task only.
    --json      Output machine-readable JSON (default: human-readable).

Exit codes:
    0  Triage complete.
    1  No DLQ tasks found.
    4  Error (log absent, reduce failed).

Buckets (7):
    input_issue       Spec unclear, missing input, bad schema.
    worker_issue      Worker crashed, tool failure, timeout.
    permission_issue  Auth failure, access denied, quota exceeded.
    code_issue        Bug in worker logic, unhandled case.
    quota_issue       Rate limit, token budget exceeded.
    transient_issue   Network error, temporary unavailability.
    unknown           No matching signal — requires manual review.
"""
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_DIST_DIR = _SCRIPTS_DIR.parent
_LIB = _DIST_DIR / "lib"

sys.path.insert(0, str(_LIB))

import argparse
from orch_core import (
    ORCH_DIR,
    TaskStatus,
    Tier,
    now_iso,
    reduce_all,
)

# ---------------------------------------------------------------------------
# Bucket classification
# ---------------------------------------------------------------------------

# Ordered list of (bucket, keyword patterns). First match wins.
_BUCKET_RULES: list[tuple[str, list[str]]] = [
    ("quota_issue", [
        "quota", "rate_limit", "rate limit", "token_budget", "budget_exceeded",
        "overloaded", "capacity",
    ]),
    ("permission_issue", [
        "permission", "access_denied", "unauthorized", "forbidden",
        "auth", "credential", "not_allowed",
    ]),
    ("input_issue", [
        "spec_unclear", "spec unclear", "missing_input", "missing input",
        "invalid_schema", "schema", "bad_input", "unclear",
        "ambiguous", "incomplete_spec", "validation_failed", "requirement_missing",
    ]),
    ("code_issue", [
        "unhandled", "assertion", "traceback", "exception", "syntax_error",
        "attribute_error", "typeerror", "nameerror", "keyerror", "indexerror",
        "not_implemented", "bug",
    ]),
    ("transient_issue", [
        "network", "timeout", "connection", "temporary", "retry_exhausted",
        "stale_timeout", "worker_exited_without_terminal", "transient",
    ]),
    ("worker_issue", [
        "worker", "crash", "tool_failure", "spawn_failed", "no_terminal",
        "worker_error", "agent_error",
    ]),
]

_FALLBACK_BUCKET = "unknown"


def _classify(reason: str | None, error: str | None) -> str:
    text = " ".join(filter(None, [reason, error])).lower()
    if not text:
        return _FALLBACK_BUCKET
    for bucket, patterns in _BUCKET_RULES:
        if any(p in text for p in patterns):
            return bucket
    return _FALLBACK_BUCKET


# ---------------------------------------------------------------------------
# Main triage logic
# ---------------------------------------------------------------------------

def triage_tasks(task_ids: list[str] | None = None) -> dict:
    state = reduce_all()

    dlq_tasks = [
        t for t in state.tasks.values()
        if t.status == TaskStatus.DLQ
        and (task_ids is None or t.task_id in task_ids)
    ]

    buckets: dict[str, list[dict]] = {
        "input_issue": [],
        "worker_issue": [],
        "permission_issue": [],
        "code_issue": [],
        "quota_issue": [],
        "transient_issue": [],
        "unknown": [],
    }

    for task in dlq_tasks:
        bucket = _classify(task.last_failure_reason, task.last_error)
        entry = {
            "task_id": task.task_id,
            "phase": task.phase,
            "tier": task.tier.value if hasattr(task.tier, "value") else str(task.tier),
            "attempts": task.attempts,
            "reason": task.last_failure_reason,
            "error": task.last_error,
            "suggested_action": _suggested_action(bucket, task),
        }
        buckets[bucket].append(entry)

    total_dlq = sum(len(v) for v in buckets.values())
    return {
        "generated_at": now_iso(),
        "total_dlq": total_dlq,
        "workflow_id": state.workflow_id,
        "buckets": buckets,
        "summary": {b: len(v) for b, v in buckets.items() if v},
    }


def _suggested_action(bucket: str, task) -> str:
    actions = {
        "input_issue": "Review and clarify task spec, then force-retry.",
        "worker_issue": "Investigate worker logs; fix tooling or retry.",
        "permission_issue": "Check credentials and access grants, then retry.",
        "code_issue": "Fix bug in worker logic, then retry.",
        "quota_issue": "Wait for quota reset or increase budget, then retry.",
        "transient_issue": "Retry when service is available.",
        "unknown": "Manual review required — check last_failure_reason and error.",
    }
    base = actions.get(bucket, actions["unknown"])
    if task.tier == Tier.CRITICAL:
        base = f"[CRITICAL] {base}"
    return base


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Triage DLQ tasks into actionable buckets.")
    parser.add_argument("--task-id", type=str, help="Triage a specific task only.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Output machine-readable JSON.")
    args = parser.parse_args()

    log_file = ORCH_DIR / "log.jsonl"
    if not log_file.exists():
        print(json.dumps({"error": "no_log", "detail": "log.jsonl not found"}),
              file=sys.stderr)
        return 4

    try:
        task_ids = [args.task_id] if args.task_id else None
        result = triage_tasks(task_ids)
    except Exception as exc:
        print(json.dumps({"error": "triage_failed", "detail": str(exc)}), file=sys.stderr)
        return 4

    if result["total_dlq"] == 0:
        if args.as_json:
            print(json.dumps(result))
        else:
            print("No DLQ tasks found.")
        return 1

    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"DLQ triage — {result['total_dlq']} task(s) | {result['generated_at']}")
        print()
        for bucket, tasks in result["buckets"].items():
            if not tasks:
                continue
            print(f"  [{bucket}] ({len(tasks)} task(s))")
            for t in tasks:
                tier_tag = f" [{t['tier'].upper()}]" if t["tier"] == "critical" else ""
                print(f"    {t['task_id']}{tier_tag}: {t['reason'] or '(no reason)'}")
                print(f"      → {t['suggested_action']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
