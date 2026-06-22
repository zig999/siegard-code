#!/usr/bin/env python3
"""
SubagentStop hook: synthesizes task_failed when a worker stops without emitting a terminal event.

Invariant enforced: every orchestrated worker invocation ends with exactly one
terminal event (task_completed or task_failed). If the worker stops silently
(crash, timeout, context overflow), this hook emits the missing terminal.

C1/C7: reads worker context from .orch/workers/<worker_id>.json registry instead
of env vars, so it works regardless of the hook's CWD.

F-03 — correlation gate: SubagentStop fires on the stop of ANY subagent and its
stdin payload carries no key (it has session_id/transcript_path, not the
orchestrator's worker_id) that correlates it to a specific registry entry. The old
code failed EVERY non-terminal registered worker on each stop — that killed sibling
workers still mid-flight and spawned retries racing the originals (the real F-03
incident was exactly this multi-worker over-synthesis). The gate now splits on how
many non-terminal workers are registered:
  • Exactly one → this stop unambiguously refers to it; a stopped subagent emits no
    more events, so it is dead → synthesize immediately (no sibling to race).
  • More than one → cannot tell which stopped → defer to the stale reaper, which
    only fails workers silent past their task-type threshold (worker_liveness_expired).
A genuinely dead worker in the multi-worker case still gets a terminal once its
window expires, via reap_stale_tasks at Step 5.0 / session end.

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
    _elapsed_seconds,
    append_event,
    get_active_workers,
    load_config,
    now_iso,
    reduce_all,
    unregister_worker,
    worker_liveness_expired,
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


# SIEGARD-01: best-effort root-cause hint for a worker that stopped without a
# terminal event. The synthesized failure otherwise carries only the generic
# reason "worker_exited_without_terminal", leaving context overflow, a tool error
# and a forgotten terminal indistinguishable in the log. Fields are additive and
# best-effort: registered_at is always present (register_worker writes it);
# spawn_context_chars is a future enrichment of the registry (dormant until then).
def _infer_cause(entry: dict) -> dict:
    out: dict = {}
    reg = entry.get("registered_at")
    if reg:
        try:
            elapsed = _elapsed_seconds(now_iso(), reg)
            out["elapsed_s"] = round(elapsed, 1)
            if elapsed < 10:
                out["suspected_cause"] = "tool_error_or_missing_input"
            elif elapsed > 120:
                out["suspected_cause"] = "context_limit_or_timeout"
            else:
                out["suspected_cause"] = "unknown"
        except Exception:  # noqa: BLE001
            out["suspected_cause"] = "unknown"
    cc = entry.get("spawn_context_chars")
    if isinstance(cc, int):
        out["spawn_context_chars"] = cc
        if cc > 150_000:
            out["suspected_cause"] = "context_limit"
    return out


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

    try:
        # Empty dict (not None): worker_liveness_expired/stale_threshold_seconds
        # treat {} as "no policy" and fall back to Tier enum defaults. Passing None
        # would make them re-call load_config() and re-raise the same ConfigError,
        # crashing the hook on a malformed config and silently disabling ALL terminal
        # synthesis exactly when config is broken.
        config = load_config()
    except Exception:  # noqa: BLE001
        config = {}
    now = now_iso()

    # F-03 correlation: SubagentStop carries no key identifying WHICH subagent
    # stopped. Count the registered workers that have not yet emitted a terminal —
    # the synthesis decision depends on whether this stop is unambiguous.
    non_terminal = [
        e for e in workers
        if e.get("task_id") and e.get("attempt") is not None and e.get("worker_id")
        and not _has_terminal(e["task_id"], e["attempt"], state)
    ]
    single_candidate = len(non_terminal) == 1

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

        # F-03 gate. Two cases:
        #  • Exactly ONE non-terminal worker: this stop unambiguously refers to it,
        #    and a stopped subagent emits no further events — it is dead. Synthesize
        #    immediately. No sibling exists to race, so the F-03 corruption (which was
        #    a MULTI-worker over-synthesis: a sibling's stop killing a live worker)
        #    cannot occur. This avoids stranding the task for a full stale window.
        #  • MULTIPLE non-terminal workers: we cannot tell which one stopped, so we
        #    must not kill a possibly-live sibling. Defer to the stale reaper, which
        #    only fails workers silent past their task-type threshold.
        task = state.tasks.get(task_id)
        if not single_candidate and task is not None and not worker_liveness_expired(task, now, config):
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
                    **_infer_cause(entry),  # SIEGARD-01: suspected_cause, elapsed_s, spawn_context_chars
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
