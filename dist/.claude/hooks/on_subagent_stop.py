#!/usr/bin/env python3
"""
SubagentStop hook: synthesizes task_failed when a worker stops without emitting a terminal event.

Invariant enforced: every orchestrated worker invocation ends with exactly one
terminal event (task_completed or task_failed). If the worker stops silently
(crash, timeout, context overflow), this hook emits the missing terminal.

C1/C7 fix: reads worker context from .orch/workers/<worker_id>.json registry
instead of env vars. This works correctly under parallel dispatch (multiple
workers running simultaneously) and regardless of the hook's CWD.

The orchestrator writes a registry entry (via register_worker()) before
spawning each Agent, and removes it (via unregister_worker()) after Step 6.4
confirms a terminal event.

If the registry is empty or absent: no-op (not an orchestrated worker context).
"""
import json
import os
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (
    EventType,
    TaskStatus,
    append_event,
    get_active_workers,
    reduce_all,
    unregister_worker,
    ORCH_DIR,
)


def _has_terminal(task_id: str, attempt: int, state) -> bool:
    """Returns True if a terminal event exists for (task_id, attempt) in derived state."""
    task = state.tasks.get(task_id)
    if task is None:
        return False
    # Terminal for attempt: task is completed/dlq (final) OR task has moved past this attempt
    if task.status in (TaskStatus.COMPLETED, TaskStatus.DLQ):
        return True
    # If attempts counter exceeds this attempt, a terminal was emitted for it
    if task.attempts > attempt:
        return True
    # Status is FAILED, SCHEDULED, or RUNNING with a matching attempt means
    # task_failed was emitted (FAILED/SCHEDULED) or it's still running (RUNNING)
    if task.status in (TaskStatus.FAILED, TaskStatus.SCHEDULED) and task.attempts == attempt:
        return True
    return False


def _get_task_phase(task_id: str, state) -> str:
    """Returns phase for task_id from derived state, or empty string."""
    task = state.tasks.get(task_id)
    return task.phase if task else ""


def main() -> int:
    # Consume stdin — Claude Code passes SubagentStop JSON via stdin; not used here.
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001
        pass

    log_file = ORCH_DIR / "log.jsonl"
    if not log_file.exists():
        return 0  # no orchestrated workflow in progress

    workers = get_active_workers()
    if not workers:
        return 0  # no registered workers — not an orchestrated context

    try:
        state = reduce_all()
    except Exception:  # noqa: BLE001
        # If state derivation fails, we cannot make safe decisions — exit cleanly.
        return 0

    for entry in workers:
        task_id = entry.get("task_id")
        attempt = entry.get("attempt")
        worker_id = entry.get("worker_id")

        if not all([task_id, attempt is not None, worker_id]):
            continue

        if _has_terminal(task_id, attempt, state):
            # Terminal already emitted — clean up registry entry if still present.
            unregister_worker(worker_id)
            continue

        # Prefer phase from registry (written at claim time) to avoid a full log
        # replay. Fall back to state derivation for entries written by older code.
        phase = entry.get("phase") or _get_task_phase(task_id, state)

        try:
            append_event(
                agent=worker_id,
                event_type=EventType.TASK_FAILED.value,
                task_id=task_id,
                attempt=attempt,
                data={
                    "phase": phase,
                    "reason": "worker_exited_without_terminal",
                    "retryable": True,
                    "synthesized_by": worker_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            # Log to stderr so the failure is visible in Claude Code hook output.
            # Do not crash — the hook must always exit cleanly.
            import json as _json
            print(
                _json.dumps({
                    "hook": "on_subagent_stop",
                    "error": "append_failed",
                    "worker_id": worker_id,
                    "task_id": task_id,
                    "attempt": attempt,
                    "detail": str(exc),
                }),
                file=sys.stderr,
            )

        # Leave registry entry in place — orchestrator Step 6.4 will clean up
        # after verifying the synthesized terminal is in state.

    return 0


if __name__ == "__main__":
    sys.exit(main())
