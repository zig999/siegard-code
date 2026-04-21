#!/usr/bin/env python3
"""
SubagentStop hook: synthesizes task_failed when a worker stops without emitting a terminal event.

Invariant enforced: every orchestrated worker invocation ends with exactly one
terminal event (task_completed or task_failed). If the worker stops silently
(crash, timeout, context overflow), this hook emits the missing terminal.

Reads (from environment, set by orchestrator before spawning):
  ORCH_TASK_ID   — task being worked on
  ORCH_ATTEMPT   — attempt number (integer)
  ORCH_WORKER_ID — worker identifier (used as agent in synthesized event)

If any of these vars is absent: no-op (not an orchestrated worker context).
If a terminal event already exists for (task_id, attempt): no-op.
Otherwise: synthesizes task_failed(retryable=true).
"""
import os
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import EventType, append_event, read_events_filtered


def _task_phase(task_id: str) -> str:
    """Returns the phase of a task from its task_created event, or '' if not found."""
    try:
        events = read_events_filtered(
            task_id=task_id,
            event_type=EventType.TASK_CREATED.value,
        )
        if events:
            return events[0].data.get("phase", "")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _has_terminal(task_id: str, attempt: int) -> bool:
    """Returns True if a terminal event exists for (task_id, attempt)."""
    try:
        events = read_events_filtered(task_id=task_id)
        for event in events:
            if (
                event.attempt == attempt
                and EventType.is_terminal_for_attempt(event.event_type)
            ):
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def main() -> int:
    # Consume stdin — Claude Code hooks receive JSON via stdin; we don't use it.
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001
        pass

    task_id = os.environ.get("ORCH_TASK_ID")
    attempt_str = os.environ.get("ORCH_ATTEMPT")
    worker_id = os.environ.get("ORCH_WORKER_ID")

    if not all([task_id, attempt_str, worker_id]):
        return 0  # not an orchestrated worker context

    try:
        attempt = int(attempt_str)
    except (ValueError, TypeError):
        return 0

    if _has_terminal(task_id, attempt):
        return 0  # terminal already emitted — nothing to do

    phase = _task_phase(task_id)

    try:
        append_event(
            agent=worker_id,
            event_type=EventType.TASK_FAILED.value,
            task_id=task_id,
            attempt=attempt,
            data={
                "phase": phase,
                "reason": "worker_stopped_without_terminal_event",
                "retryable": True,
                "synthesized_by": worker_id,
            },
        )
    except Exception:  # noqa: BLE001
        # Best-effort: don't crash the hook even if append fails.
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
