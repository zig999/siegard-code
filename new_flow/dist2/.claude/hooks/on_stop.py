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
    ensure_dirs, now_iso, parse_iso,
)


def _compute_metrics() -> dict:
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


def main() -> None:
    try:
        log_file = ORCH_DIR / "log.jsonl"
        if not log_file.exists():
            return

        ensure_dirs()
        metrics = _compute_metrics()

        out_path = METRICS_DIR / "current.json"
        out_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass  # Hook must never block shutdown


if __name__ == "__main__":
    main()
