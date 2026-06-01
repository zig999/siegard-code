#!/usr/bin/env python3
"""
Stop hook: aggregates session metrics and writes .orch/metrics/current.json.

Triggered by Claude Code on session end (settings.json Stop hook).
Reads the current OrchState via reduce_all() and writes a structured metrics
file. Never raises — all exceptions are swallowed so the hook never blocks shutdown.

Output: .orch/metrics/current.json
"""
import json
import os
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (
    reduce_all, TaskStatus, PhaseStatus, ORCH_DIR, METRICS_DIR,
    ensure_dirs, now_iso, parse_iso, read_events_filtered,
    cleanup_stale_workers, reap_stale_tasks,
)


def _detect_orphaned_phase(state) -> dict | None:
    """
    Returns a diagnostic dict when a phase_entered event exists with no tasks
    dispatched and no escalation — the phase orchestrator was never spawned.
    This happens when the meta-orchestrator is interrupted between Step 5
    (phase_entered) and Step 6 (Agent spawn).
    """
    if state.current_phase is None:
        return None
    phase = state.phases.get(state.current_phase)
    if phase is None or phase.status.value != "active":
        return None
    if state.escalation is not None:
        return None
    # If the workflow has no tasks at all it is "empty", not orphaned.
    if not state.tasks:
        return None
    phase_tasks = [t for t in state.tasks.values() if t.phase == state.current_phase]
    if phase_tasks:
        return None
    return {
        "orphaned_phase": state.current_phase,
        "entered_at": phase.entered_at,
        "action_required": "re-invoke orchestrator — phase_entered emitted but phase orchestrator was never dispatched",
    }


def _detect_stuck_improve_spec(state, orch_dir: Path) -> dict | None:
    """
    Returns a diagnostic dict when an improve workflow has completed SDD tasks but
    spec_change_status was never closed (no spec_pipeline_return event emitted).
    Indicates orchestrator-sdd ran without the spec_pipeline_return fix deployed.
    """
    sessions_dir = orch_dir / "sessions"
    if not sessions_dir.exists():
        return None
    import json as _json
    for scope_path in sessions_dir.glob("*/improve-scope.json"):
        try:
            scope = _json.loads(scope_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if scope.get("spec_change_status") != "pending_spec":
            continue
        workflow_id = scope.get("workflow_id", scope_path.parent.name)
        sdd_completed = [
            t for t in state.tasks.values()
            if t.phase == "sdd" and t.status.value == "completed"
        ]
        if not sdd_completed:
            continue
        returns = read_events_filtered(event_type="spec_pipeline_return")
        if any(e.data.get("workflow_id") == workflow_id for e in returns):
            continue
        return {
            "stuck_improve_spec": str(scope_path.relative_to(orch_dir.parent)),
            "workflow_id": workflow_id,
            "sdd_tasks_completed": len(sdd_completed),
            "action_required": (
                f"SDD phase completed but spec_change_status was never closed "
                f"(spec_pipeline_return not emitted). "
                f"Deploy latest orchestrator-sdd.md+orch_core.py and re-invoke /u-orchestrator, "
                f"OR run: python3 .claude/scripts/fix_stuck_improve.py "
                f"--session {workflow_id} --action accept_divergence"
            ),
        }
    return None


def _write_stuck_improve_alert(stuck: dict, metrics: dict) -> None:
    """Writes .orch/last_error.json with a stuck-improve-spec diagnostic."""
    payload = {
        "generated_at": now_iso(),
        "workflow_id": metrics.get("workflow_id"),
        "run_status": "stuck_improve_spec",
        "last_seq": metrics.get("last_seq"),
        "diagnostic": stuck,
    }
    out_path = ORCH_DIR / "last_error.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _compute_metrics(state=None) -> dict:
    if state is None:
        state = reduce_all()

    tasks_by_status: dict[str, int] = {}
    for t in state.tasks.values():
        key = t.status.value if hasattr(t.status, "value") else str(t.status)
        tasks_by_status[key] = tasks_by_status.get(key, 0) + 1

    phases_completed = sum(
        1 for p in state.phases.values()
        if p.status == PhaseStatus.COMPLETED
    )

    phase_durations: dict[str, float | None] = {}
    for name, p in state.phases.items():
        if p.entered_at and p.completed_at:
            entered = parse_iso(p.entered_at)
            completed = parse_iso(p.completed_at)
            phase_durations[name] = (completed - entered).total_seconds()
        else:
            phase_durations[name] = None

    total_tasks = len(state.tasks)
    completed = tasks_by_status.get("completed", 0)
    failed = tasks_by_status.get("failed", 0)
    dlq = tasks_by_status.get("dlq", 0)

    if total_tasks == 0:
        run_status = "empty"
    elif state.escalation:
        run_status = "escalated"
    elif dlq > 0 and (completed + dlq) == total_tasks:
        run_status = "completed_with_dlq"
    elif completed == total_tasks:
        run_status = "completed"
    else:
        run_status = "partial"

    return {
        "generated_at": now_iso(),
        "workflow_id": state.workflow_id,
        "run_status": run_status,
        "current_phase": state.current_phase,
        "last_seq": state.last_seq,
        "tasks_total": total_tasks,
        "tasks_by_status": tasks_by_status,
        "tasks_completed": completed,
        "tasks_failed": failed,
        "tasks_dlq": dlq,
        "phases_completed": phases_completed,
        "phase_durations": phase_durations,
        "escalations": 1 if state.escalation else 0,
        "circuit_breaker_tripped": state.circuit_breaker is not None,
    }


def _detect_stale_orchestrator(state, events: list) -> dict | None:
    """
    Returns a diagnostic when a phase is active and has pending tasks but no
    ORCHESTRATOR_HEARTBEAT was emitted within the stale threshold.

    Indicates the orchestrator LLM was alive (no crash) but stopped making
    progress — typically caused by emitting narrative text instead of events.
    """
    if state.current_phase is None:
        return None
    phase = state.phases.get(state.current_phase)
    if not phase or phase.status.value != "active":
        return None

    pending = [
        t for t in state.tasks.values()
        if t.phase == state.current_phase
        and t.status.value not in ("completed", "dlq", "skipped")
    ]
    if not pending:
        return None

    STALE_THRESHOLD_SECONDS = 900  # 15 minutes
    heartbeats = [
        e for e in events
        if e.event_type == "orchestrator_heartbeat"
        and e.data.get("phase") == state.current_phase
    ]
    if heartbeats:
        last_hb = max(heartbeats, key=lambda e: e.seq)
        try:
            age = (parse_iso(now_iso()) - parse_iso(last_hb.timestamp)).total_seconds()
            if age < STALE_THRESHOLD_SECONDS:
                return None
        except Exception:
            pass

    return {
        "stale_orchestrator": state.current_phase,
        "pending_tasks": len(pending),
        "pending_task_ids": [t.task_id for t in pending],
        "last_heartbeat": heartbeats[-1].timestamp if heartbeats else None,
        "action_required": (
            "Orchestrator stopped making progress with active tasks remaining. "
            "Re-invoke /u-orchestrator — the log is intact and execution will resume "
            "from the current state."
        ),
        "command": "/u-orchestrator",
    }


def _write_stale_orchestrator_alert(stale: dict, metrics: dict) -> None:
    payload = {
        "generated_at": now_iso(),
        "workflow_id": metrics.get("workflow_id"),
        "run_status": "stale_orchestrator",
        "last_seq": metrics.get("last_seq"),
        "diagnostic": stale,
    }
    out_path = ORCH_DIR / "last_error.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _detect_worker_stopped_failures(state) -> dict | None:
    """
    Returns a structured recovery diagnostic when the session ended with
    worker_stopped_without_terminal_event failures that were synthesized by the
    on_subagent_stop hook.

    These failures are retryable but require the orchestrator to be re-invoked.
    This function surfaces the actionable recovery steps so operators don't
    need to inspect the raw log to understand what happened.
    """
    stopped_tasks = [
        t for t in state.tasks.values()
        if t.status in (TaskStatus.FAILED, TaskStatus.SCHEDULED)
        and getattr(t, "last_failure_reason", None) == "worker_stopped_without_terminal_event"
    ]
    if not stopped_tasks:
        return None

    return {
        "worker_stopped_count": len(stopped_tasks),
        "affected_tasks": [
            {
                "task_id": t.task_id,
                "phase": t.phase,
                "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                "attempts": t.attempts,
            }
            for t in stopped_tasks
        ],
        "action_required": (
            "Re-invoke the orchestrator — these tasks were synthesized as failed by "
            "on_subagent_stop because their workers stopped without emitting a terminal event. "
            "They are retryable and will be picked up automatically on next orchestrator run."
        ),
        "command": "/u-orchestrator",
    }


_ERROR_RUN_STATUSES = frozenset({"escalated", "partial", "completed_with_dlq"})
_ERROR_EVENT_TYPES = frozenset({
    "task_failed", "task_dlq", "escalation", "circuit_breaker_tripped", "preflight_failed",
})


def _write_last_error(metrics: dict, events: list | None = None) -> None:
    """Writes .orch/last_error.json with the last error-related event from the log."""
    if events is None:
        events = list(read_events_filtered(event_type=None))
    error_events = [e for e in events if e.event_type in _ERROR_EVENT_TYPES]
    if not error_events:
        return
    last = error_events[-1]
    payload = {
        "generated_at": now_iso(),
        "workflow_id": metrics.get("workflow_id"),
        "run_status": metrics.get("run_status"),
        "last_seq": metrics.get("last_seq"),
        "last_error_event": last.to_dict(),
    }
    out_path = ORCH_DIR / "last_error.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_orphan_alert(orphan: dict, metrics: dict) -> None:
    """Writes .orch/last_error.json with an orphaned-phase diagnostic."""
    payload = {
        "generated_at": now_iso(),
        "workflow_id": metrics.get("workflow_id"),
        "run_status": "orphaned_phase",
        "last_seq": metrics.get("last_seq"),
        "diagnostic": orphan,
    }
    out_path = ORCH_DIR / "last_error.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_worker_stopped_alert(stopped: dict, metrics: dict) -> None:
    """Writes .orch/last_error.json with a worker_stopped recovery diagnostic."""
    payload = {
        "generated_at": now_iso(),
        "workflow_id": metrics.get("workflow_id"),
        "run_status": "worker_stopped_recovery_required",
        "last_seq": metrics.get("last_seq"),
        "diagnostic": stopped,
    }
    out_path = ORCH_DIR / "last_error.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    try:
        log_file = ORCH_DIR / "log.jsonl"
        if not log_file.exists():
            return

        ensure_dirs()

        # Purge stale worker registry entries from interrupted sessions before
        # computing state — prevents phantom worker_stopped detections on next run.
        try:
            cleanup_stale_workers(max_age_seconds=3600)
        except Exception:
            pass

        # prod-hardening task 06 (A2-F1): reap hung RUNNING tasks deterministically
        # at session end — backstop to the orchestrator Step 5.0 check_stale.py call.
        try:
            reap_stale_tasks()
        except Exception:
            pass

        events = list(read_events_filtered(event_type=None))
        state = reduce_all()
        metrics = _compute_metrics(state)
        metrics["orphaned_phase"] = None

        orphan = _detect_orphaned_phase(state)
        if orphan:
            metrics["orphaned_phase"] = orphan["orphaned_phase"]
            metrics["run_status"] = "orphaned_phase"
            _write_orphan_alert(orphan, metrics)

        metrics["stuck_improve_spec"] = None
        stuck = _detect_stuck_improve_spec(state, ORCH_DIR)
        if stuck:
            metrics["stuck_improve_spec"] = stuck["workflow_id"]
            if metrics.get("run_status") not in ("orphaned_phase",):
                metrics["run_status"] = "stuck_improve_spec"
            _write_stuck_improve_alert(stuck, metrics)

        metrics["stale_orchestrator"] = None
        stale = _detect_stale_orchestrator(state, events)
        if stale:
            metrics["stale_orchestrator"] = stale["stale_orchestrator"]
            if metrics.get("run_status") not in ("orphaned_phase", "stuck_improve_spec"):
                metrics["run_status"] = "stale_orchestrator"
            _write_stale_orchestrator_alert(stale, metrics)

        # Detect tasks that failed via on_subagent_stop synthesis and need
        # orchestrator re-invocation to retry. Surfaces recovery instructions
        # in last_error.json so operators don't need to read the raw log.
        metrics["worker_stopped_recovery"] = None
        stopped = _detect_worker_stopped_failures(state)
        if stopped:
            metrics["worker_stopped_recovery"] = stopped["worker_stopped_count"]
            if metrics.get("run_status") not in ("orphaned_phase", "stuck_improve_spec"):
                metrics["run_status"] = "worker_stopped_recovery_required"
            _write_worker_stopped_alert(stopped, metrics)

        out_path = METRICS_DIR / "current.json"
        out_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

        if (
            metrics.get("run_status") in _ERROR_RUN_STATUSES
            or metrics.get("circuit_breaker_tripped")
            or metrics.get("escalations", 0) > 0
        ):
            _write_last_error(metrics, events)
    except Exception:
        pass  # Hook must never block shutdown


if __name__ == "__main__":
    main()
