#!/usr/bin/env python3
"""
Siegard Monitor — live TUI for orchestration state.

Usage:
    python monitor.py [--project-dir PATH] [--interval N] [--once]

Flags:
    --project-dir PATH   Override ORCH_PROJECT_DIR env var
    --interval N         Poll interval in seconds (default: 2)
    --once               Render one frame to stdout and exit (no curses)
"""
from __future__ import annotations

import argparse
import curses
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Early arg parse: ORCH_PROJECT_DIR must be set BEFORE importing orch_core
# because that module computes ORCH_DIR at module load time (not lazily).
# ---------------------------------------------------------------------------
def _early_resolve_project_dir() -> Path:
    """Parse --project-dir / ORCH_PROJECT_DIR without consuming sys.argv.

    Resolution order:
      1. --project-dir flag
      2. ORCH_PROJECT_DIR env var
      3. Walk up from cwd looking for .orch/log.jsonl
      4. cwd fallback
    """
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg in ("--project-dir", "-project-dir") and i < len(sys.argv):
            return Path(sys.argv[i + 1]).resolve()
        if arg.startswith("--project-dir="):
            return Path(arg.split("=", 1)[1]).resolve()
    env = os.environ.get("ORCH_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    # Walk up from cwd looking for .orch/log.jsonl
    candidate = Path(".").resolve()
    while True:
        if (candidate / ".orch" / "log.jsonl").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return Path(".").resolve()

_project_dir_early = _early_resolve_project_dir()
os.environ["ORCH_PROJECT_DIR"] = str(_project_dir_early)

# ---------------------------------------------------------------------------
# Bootstrap: resolve lib relative to this script
# ---------------------------------------------------------------------------
_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (  # noqa: E402
    CorruptedLogError,
    IllegalTransition,
    OrchState,
    PhaseStatus,
    TaskStatus,
    reduce_all,
    read_events_filtered,
    is_blob_ref,
    load_blob_data,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "1.0.0"
MIN_COLS = 80
MIN_ROWS = 24

STATUS_ORDER = [
    TaskStatus.RUNNING,
    TaskStatus.READY,
    TaskStatus.PENDING,
    TaskStatus.SCHEDULED,
    TaskStatus.FAILED,
    TaskStatus.DLQ,
    TaskStatus.CANCELLED,
    TaskStatus.COMPLETED,
]

STATUS_ICON = {
    TaskStatus.RUNNING:   "▶",
    TaskStatus.READY:     "○",
    TaskStatus.PENDING:   "·",
    TaskStatus.SCHEDULED: "↻",
    TaskStatus.FAILED:    "✗",
    TaskStatus.DLQ:       "☠",
    TaskStatus.CANCELLED: "⊘",
    TaskStatus.COMPLETED: "✓",
}

PHASE_ICON = {
    PhaseStatus.PENDING:       "○",
    PhaseStatus.ACTIVE:        "►",
    PhaseStatus.EXIT_APPROVED: "✓",
    PhaseStatus.COMPLETED:     "✓",
    PhaseStatus.PAUSED:        "‖",
}

# curses color pair IDs
C_HEADER   = 1
C_RUNNING  = 2
C_READY    = 3
C_PENDING  = 4
C_FAILED   = 5
C_DLQ      = 6
C_DONE     = 7
C_ALERT    = 8
C_DIM      = 9

STATUS_COLOR = {
    TaskStatus.RUNNING:   C_RUNNING,
    TaskStatus.READY:     C_READY,
    TaskStatus.PENDING:   C_PENDING,
    TaskStatus.SCHEDULED: C_PENDING,
    TaskStatus.FAILED:    C_FAILED,
    TaskStatus.DLQ:       C_DLQ,
    TaskStatus.CANCELLED: C_DIM,
    TaskStatus.COMPLETED: C_DONE,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short_ts(iso: str | None) -> str:
    """Convert ISO timestamp to HH:MM display string."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M")
    except Exception:
        return iso[:5]


def _trunc(s: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(s) <= width:
        return s
    return s[: max(0, width - 1)] + "…"


def _stat_key(path: Path) -> tuple[float, int]:
    try:
        st = os.stat(path)
        return (st.st_mtime, st.st_size)
    except OSError:
        return (0.0, 0)


def _last_checkpoint(task_id: str) -> str | None:
    """Returns the checkpoint label from the last task_progress event for task_id, or None."""
    try:
        events = read_events_filtered(task_id=task_id, event_type="task_progress", tail=1)
        if not events:
            return None
        data = events[-1].data
        if is_blob_ref(data):
            data = load_blob_data(events[-1])
        return data.get("checkpoint") or None
    except Exception:
        return None


def _load_state(project_dir: Path) -> tuple[OrchState | None, str | None]:
    """Return (state, error_msg). error_msg is None on success."""
    import orch_core as _oc
    # Re-resolve paths in case project_dir changed (supports dynamic reload).
    orch_dir = project_dir / ".orch"
    log = orch_dir / "log.jsonl"
    if not log.exists():
        return None, "waiting for log…"
    # Point orch_core to the right directory before calling reduce_all.
    _oc.ORCH_DIR = orch_dir
    _oc.LOG_PATH = log
    try:
        state = reduce_all()
        return state, None
    except CorruptedLogError as exc:
        return None, f"CORRUPTED LOG: {exc}"
    except IllegalTransition as exc:
        return None, f"ILLEGAL TRANSITION: {exc}"
    except Exception as exc:  # noqa: BLE001
        return None, f"ERROR: {exc}"


# ---------------------------------------------------------------------------
# Multi-workflow index (re-scans the log; does NOT mutate engine state)
# ---------------------------------------------------------------------------

UNKNOWN_WORKFLOW = "_unknown"
_ORCHESTRATOR_PREFIXES = ("orchestrator-", "u-orchestrator-")
_TASK_EVENT_TYPES = {
    "task_created", "task_claimed", "task_progress", "task_completed",
    "task_failed", "task_dlq", "task_skipped", "task_retried",
    "task_scheduled_retry",
}
_TERMINAL_EVENTS = {"task_completed", "task_failed", "task_dlq", "task_skipped"}


def _new_workflow_record() -> dict[str, Any]:
    return {
        "first_seq": None,
        "last_seq": 0,
        "phases": [],
        "current_phase": None,
        "status": "unknown",
        "agents_running": [],
        "agents_executed": [],
        "agents_failed": [],
        "phase_details": {},   # phase_name → {status, order, entered_at, completed_at, approved_at, criteria_met}
        "task_statuses": {},   # task_id → current task state dict
    }


def _collect_workflow_index(project_dir: Path) -> tuple[dict[str, dict], str | None]:
    """
    Re-scan the log and group events by workflow_id.

    workflow_id is set by `phase_declared.data.workflow_id`. Every event
    between one phase_declared and the next is attributed to that workflow.
    Events emitted before any phase_declared land in UNKNOWN_WORKFLOW.

    Returns (workflows, error). On hard error returns ({}, error_msg).
    """
    import orch_core as _oc
    orch_dir = project_dir / ".orch"
    log = orch_dir / "log.jsonl"
    if not log.exists():
        return {}, "waiting for log…"
    _oc.ORCH_DIR = orch_dir
    _oc.LOG_PATH = log

    workflows: dict[str, dict] = {}
    # Per workflow: per (task_id, attempt) the most recent state record.
    task_state: dict[str, dict[tuple[str, int], dict]] = {}
    current_wf: str | None = None

    try:
        events = list(read_events_filtered())
    except CorruptedLogError as exc:
        return {}, f"CORRUPTED LOG: {exc}"
    except Exception as exc:  # noqa: BLE001
        return {}, f"ERROR: {exc}"

    for event in events:
        et = event.event_type
        data = event.data
        if is_blob_ref(data):
            try:
                data = load_blob_data(event)
            except Exception:  # noqa: BLE001
                data = {}

        if et == "phase_declared":
            wf_id = data.get("workflow_id")
            if wf_id:
                current_wf = wf_id
                w = workflows.setdefault(wf_id, _new_workflow_record())
                if w["first_seq"] is None:
                    w["first_seq"] = event.seq
                phases = data.get("phases", [])
                if isinstance(phases, list):
                    for i, phase_def in enumerate(phases):
                        pname = phase_def["name"] if isinstance(phase_def, dict) else str(phase_def)
                        order = phase_def.get("order", i) if isinstance(phase_def, dict) else i
                        if pname not in w["phases"]:
                            w["phases"].append(pname)
                        w["phase_details"].setdefault(pname, {
                            "status": "pending", "order": order,
                            "entered_at": None, "completed_at": None,
                            "approved_at": None, "criteria_met": [],
                        })

        # Prefer workflow_id embedded in event data (new events) over tracked current_wf (legacy).
        wf = data.get("workflow_id") or current_wf or UNKNOWN_WORKFLOW
        w = workflows.setdefault(wf, _new_workflow_record())
        if w["first_seq"] is None:
            w["first_seq"] = event.seq
        if event.seq > (w["last_seq"] or 0):
            w["last_seq"] = event.seq

        pd_map = w["phase_details"]
        if et == "phase_entered":
            w["current_phase"] = data.get("phase")
            w["status"] = "active"
            pname = data.get("phase")
            if pname:
                pd = pd_map.setdefault(pname, {
                    "status": "pending", "order": len(pd_map),
                    "entered_at": None, "completed_at": None,
                    "approved_at": None, "criteria_met": [],
                })
                pd["status"] = "active"
                pd["entered_at"] = event.ts
        elif et == "phase_transitioned":
            to_phase = data.get("to_phase")
            if to_phase:
                w["current_phase"] = to_phase
            declared = w["phases"]
            if not to_phase or (declared and to_phase not in declared):
                w["status"] = "done"
            else:
                w["status"] = "active"
            from_phase = data.get("from_phase")
            if from_phase and from_phase in pd_map:
                pd_map[from_phase]["status"] = "completed"
                pd_map[from_phase]["completed_at"] = event.ts
        elif et == "phase_exit_approved":
            next_phase = data.get("next_phase")
            declared = w["phases"]
            if not next_phase or (declared and next_phase not in declared):
                w["status"] = "done"
            pname = data.get("phase")
            if pname and pname in pd_map:
                pd_map[pname]["status"] = "exit_approved"
                pd_map[pname]["approved_at"] = event.ts
                criteria = data.get("criteria_met", [])
                if isinstance(criteria, list):
                    pd_map[pname]["criteria_met"].extend(criteria)
        elif et == "phase_paused":
            pname = data.get("phase")
            if pname and pname in pd_map:
                pd_map[pname]["status"] = "paused"
        elif et == "phase_resumed":
            pname = data.get("phase")
            if pname and pname in pd_map:
                pd_map[pname]["status"] = "active"

        # --- task_statuses: per-task_id current state (for TASKS section) ---
        if et in _TASK_EVENT_TYPES and event.task_id:
            tid = event.task_id
            ts_map = w["task_statuses"]
            ts = ts_map.setdefault(tid, {
                "task_id": tid,
                "status": "pending",
                "worker_id": None,
                "attempts": 0,
                "max_attempts": data.get("max_attempts", 3),
                "claimed_at": None,
                "last_event_at": None,
                "last_failure_reason": None,
                "next_retry_at": None,
            })
            ts["last_event_at"] = event.ts
            if et == "task_created":
                ts["status"] = "pending"
                ts["max_attempts"] = data.get("max_attempts", ts["max_attempts"])
            elif et == "task_claimed":
                ts["status"] = "running"
                ts["worker_id"] = data.get("worker_id")
                ts["claimed_at"] = event.ts
                ts["attempts"] += 1
            elif et == "task_completed":
                ts["status"] = "completed"
            elif et == "task_failed":
                ts["status"] = "failed"
                ts["last_failure_reason"] = data.get("reason")
            elif et == "task_scheduled_retry":
                ts["status"] = "scheduled"
                ts["next_retry_at"] = data.get("next_retry_at")
            elif et == "task_retried":
                ts["status"] = "running"
            elif et == "task_dlq":
                ts["status"] = "dlq"
                ts["last_failure_reason"] = data.get("reason")
            elif et == "task_skipped":
                ts["status"] = "cancelled"

        if et in _TASK_EVENT_TYPES and event.task_id:
            attempt = event.attempt or 1
            key = (event.task_id, attempt)
            te_map = task_state.setdefault(wf, {})
            te = te_map.setdefault(key, {
                "task_id": event.task_id,
                "attempt": attempt,
                "phase": data.get("phase"),
                "worker_type": None,
                "worker_id": None,
                "claimed_at": None,
                "last_event_at": None,
                "last_event_type": None,
                "last_progress": None,
                "reason": None,
            })
            te["last_event_at"] = event.ts
            te["last_event_type"] = et
            if data.get("phase"):
                te["phase"] = data.get("phase")

            if et == "task_claimed":
                te["worker_type"] = data.get("worker_type")
                te["worker_id"] = data.get("worker_id")
                te["claimed_at"] = event.ts
            elif et == "task_progress":
                te["last_progress"] = data.get("checkpoint") or data.get("note")
            elif et in ("task_failed", "task_dlq"):
                te["reason"] = data.get("reason")

    # Materialize per-workflow agent lists from task_state.
    for wf_id, te_map in task_state.items():
        w = workflows.setdefault(wf_id, _new_workflow_record())
        for te in te_map.values():
            kind = te.get("last_event_type")
            if kind in _TERMINAL_EVENTS:
                if kind == "task_completed":
                    w["agents_executed"].append(te)
                else:
                    w["agents_failed"].append(te)
            elif kind in ("task_claimed", "task_progress", "task_retried"):
                w["agents_running"].append(te)
            # task_created / task_scheduled_retry alone → not yet in flight; skip

        w["agents_running"].sort(key=lambda x: x.get("claimed_at") or "")
        w["agents_executed"].sort(key=lambda x: x.get("last_event_at") or "")
        w["agents_failed"].sort(key=lambda x: x.get("last_event_at") or "")

    return workflows, None


def _find_active_workflow(workflows: dict[str, dict]) -> tuple[str, dict] | None:
    """Return (workflow_id, record) for the most recently active workflow, or None."""
    active = [(wf_id, w) for wf_id, w in workflows.items() if w["status"] == "active"]
    if not active:
        return None
    return max(active, key=lambda item: item[1]["last_seq"] or 0)


def _wf_phases(wf: dict) -> dict:
    """Convert workflow phase_details to SimpleNamespace objects for rendering."""
    from types import SimpleNamespace
    result = {}
    for name, pd in wf["phase_details"].items():
        try:
            ps = PhaseStatus(pd["status"])
        except ValueError:
            ps = PhaseStatus.PENDING
        result[name] = SimpleNamespace(
            status=ps,
            order=pd.get("order", 0),
            entered_at=pd.get("entered_at"),
            completed_at=pd.get("completed_at"),
            approved_at=pd.get("approved_at"),
            criteria_met=pd.get("criteria_met", []),
        )
    return result


def _wf_tasks(wf: dict) -> dict:
    """Convert workflow task_statuses to SimpleNamespace objects for rendering."""
    from types import SimpleNamespace
    result = {}
    for tid, ts in wf["task_statuses"].items():
        try:
            status = TaskStatus(ts["status"])
        except ValueError:
            status = TaskStatus.PENDING
        result[tid] = SimpleNamespace(
            task_id=tid,
            status=status,
            worker_id=ts.get("worker_id"),
            attempts=ts.get("attempts", 1),
            max_attempts=ts.get("max_attempts", 3),
            claimed_at=ts.get("claimed_at"),
            last_event_at=ts.get("last_event_at"),
            last_failure_reason=ts.get("last_failure_reason"),
            next_retry_at=ts.get("next_retry_at"),
        )
    return result


def _is_orchestrator_agent(worker_type: str | None) -> bool:
    if not worker_type:
        return False
    return any(worker_type.startswith(p) for p in _ORCHESTRATOR_PREFIXES)


def _filter_orchestrators(agents: list[dict], show: bool) -> list[dict]:
    if show:
        return agents
    return [a for a in agents if not _is_orchestrator_agent(a.get("worker_type"))]


# ---------------------------------------------------------------------------
# Plain-text renderer (--once mode)
# ---------------------------------------------------------------------------

def render_plain(state: OrchState | None, error: str | None) -> None:
    if error:
        print(f"  {error}")
        return

    assert state is not None

    phase_label = state.current_phase or "(none)"
    run_badge = "● DONE" if state.run_status == "completed" else "● LIVE"
    print(f"SIEGARD MONITOR  [{phase_label}]  seq={state.last_seq}  {run_badge}")
    print()

    _plain_phases(state)
    print()
    _plain_tasks(state)

    if state.circuit_breaker:
        print()
        print(f"  ⚡ CIRCUIT BREAKER: {state.circuit_breaker.get('status', '?')}")

    if state.escalation:
        print()
        code = state.escalation.get("code", "?")
        reason = state.escalation.get("reason", "")
        print(f"  ⚠ ESCALATION {code}: {reason}")


def _plain_phases(state: OrchState) -> None:
    if not state.phases:
        print("  Phases: (none)")
        return
    print("PHASES")
    for name, p in sorted(state.phases.items(), key=lambda kv: kv[1].order):
        ps = p.status.value if hasattr(p.status, "value") else str(p.status)
        icon = PHASE_ICON.get(PhaseStatus(ps) if ps in PhaseStatus._value2member_map_ else PhaseStatus.PENDING, "○")
        ts = _short_ts(p.entered_at if ps == "active" else p.completed_at)
        qualifier = f"(since {ts})" if ps == "active" else f"(completed {ts})" if ps == "completed" else ""
        print(f"  {icon} {name}  {qualifier}")


def render_plain_multi(workflows: dict[str, dict], error: str | None,
                       *, workflow_filter: str | None = None,
                       running_only: bool = False,
                       show_orchestrators: bool = False) -> None:
    """Plain-text multi-workflow renderer for --once mode."""
    if error:
        print(f"  {error}")
        return
    if not workflows:
        print("  No workflows found in log.")
        return

    items = sorted(workflows.items(), key=lambda kv: -(kv[1]["last_seq"] or 0))

    if workflow_filter:
        items = [(k, v) for k, v in items if k == workflow_filter]
        if not items:
            print(f"  Workflow not found: {workflow_filter}")
            return

    if running_only:
        items = [(k, v) for k, v in items if v["status"] != "done"]
        if not items:
            print("  No live workflows.")
            return

    print(f"SIEGARD MONITOR — {len(items)} workflow(s)")
    print()

    for wf_id, w in items:
        phase = w["current_phase"] or "(none)"
        status = w["status"]
        badge = {
            "active":  "● LIVE",
            "done":    "● DONE",
            "unknown": "● ?",
        }.get(status, "● ?")
        wf_label = wf_id if wf_id != UNKNOWN_WORKFLOW else "(orphan events — no phase_declared)"
        print(f"▼ {wf_label}  [{phase}]  seq={w['last_seq']}  {badge}")

        running = _filter_orchestrators(w["agents_running"], show_orchestrators)
        executed = _filter_orchestrators(w["agents_executed"], show_orchestrators)
        failed = _filter_orchestrators(w["agents_failed"], show_orchestrators)

        if running:
            print(f"   Agents running ({len(running)}):")
            for a in running:
                wt = (a.get("worker_type") or "—")[:22]
                tid = (a.get("task_id") or "—")[:18]
                claimed = _short_ts(a.get("claimed_at"))
                cp = a.get("last_progress")
                cp_str = f"  ⤳ {cp}" if cp else ""
                print(f"     {wt:<22} {tid:<18}  attempt {a.get('attempt')}  claimed {claimed}{cp_str}")

        if executed:
            print(f"   Agents executed ({len(executed)}):")
            for a in executed:
                wt = (a.get("worker_type") or "—")[:22]
                tid = (a.get("task_id") or "—")[:18]
                ts = _short_ts(a.get("last_event_at"))
                print(f"     {wt:<22} ✓ {tid:<18}  {ts}")

        if failed:
            print(f"   Agents failed ({len(failed)}):")
            for a in failed:
                wt = (a.get("worker_type") or "—")[:22]
                tid = (a.get("task_id") or "—")[:18]
                kind = a.get("last_event_type", "")
                reason = (a.get("reason") or "")[:40]
                print(f"     {wt:<22} ✗ {tid:<18}  {kind}  {reason}")

        if not running:
            if w["status"] == "active":
                phase = w["current_phase"] or "?"
                print(f"   ⟳ {phase}  [orchestrator dispatching…]")
            elif not (executed or failed):
                hint = "" if show_orchestrators else " (run with --show-orchestrators to include meta agents)"
                print(f"   (no leaf-agent activity recorded{hint})")
        print()


def _plain_tasks(state: OrchState) -> None:
    if not state.tasks:
        print("  Tasks: (none)")
        return
    print("TASKS")
    by_status: dict[TaskStatus, list] = {s: [] for s in STATUS_ORDER}
    for t in state.tasks.values():
        s = t.status if isinstance(t.status, TaskStatus) else TaskStatus(t.status)
        by_status.setdefault(s, []).append(t)

    for status in STATUS_ORDER:
        tasks = by_status.get(status, [])
        if not tasks:
            continue
        if status == TaskStatus.COMPLETED:
            print(f"  ✓ completed  ({len(tasks)})")
            continue
        for t in tasks:
            icon = STATUS_ICON.get(status, "?")
            worker = t.worker_id or "—"
            ts = _short_ts(t.claimed_at if status == TaskStatus.RUNNING else t.last_event_at)
            attempt_str = f"  attempt {t.attempts}/{t.max_attempts}" if t.attempts > 1 else ""
            dlq_str = "  ← DLQ" if status == TaskStatus.DLQ else ""
            print(f"  {t.task_id[:16]:<16}  [{status.value:<14}]  {worker[:24]:<24}  {ts}{attempt_str}{dlq_str}")


# ---------------------------------------------------------------------------
# Curses renderer
# ---------------------------------------------------------------------------

def _init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_HEADER,  curses.COLOR_CYAN,    -1)
    curses.init_pair(C_RUNNING, curses.COLOR_GREEN,   -1)
    curses.init_pair(C_READY,   curses.COLOR_CYAN,    -1)
    curses.init_pair(C_PENDING, curses.COLOR_YELLOW,  -1)
    curses.init_pair(C_FAILED,  curses.COLOR_RED,     -1)
    curses.init_pair(C_DLQ,     curses.COLOR_MAGENTA, -1)
    curses.init_pair(C_DONE,    curses.COLOR_GREEN,   -1)
    curses.init_pair(C_ALERT,   curses.COLOR_RED,     -1)
    curses.init_pair(C_DIM,     curses.COLOR_WHITE,   -1)


def _addstr(win: Any, row: int, col: int, text: str, attr: int = 0) -> None:
    max_rows, max_cols = win.getmaxyx()
    if row >= max_rows or col >= max_cols:
        return
    available = max_cols - col - 1
    if available <= 0:
        return
    try:
        win.addstr(row, col, _trunc(text, available), attr)
    except curses.error:
        pass


def _hline(win: Any, row: int, col: int, ch: str, n: int) -> None:
    max_rows, max_cols = win.getmaxyx()
    if row >= max_rows:
        return
    n = min(n, max_cols - col - 1)
    try:
        win.addstr(row, col, ch * n)
    except curses.error:
        pass


def render_curses(stdscr: Any, state: OrchState | None, error: str | None, log_path: Path,
                  workflows: dict[str, dict] | None = None,
                  project_dir: Path | None = None) -> None:
    rows, cols = stdscr.getmaxyx()
    stdscr.erase()

    if rows < MIN_ROWS or cols < MIN_COLS:
        _addstr(stdscr, 0, 0, f"Terminal too small (min {MIN_COLS}×{MIN_ROWS}, current {cols}×{rows})",
                curses.color_pair(C_ALERT) | curses.A_BOLD)
        stdscr.refresh()
        return

    row = 0

    # Resolve active workflow for per-workflow PHASES and TASKS rendering.
    _active = _find_active_workflow(workflows or {})
    active_wf_id, active_wf = _active if _active else (None, None)
    active_phases = _wf_phases(active_wf) if active_wf else {}
    active_tasks  = _wf_tasks(active_wf)  if active_wf else {}

    # ---- Header ----
    if error:
        badge = "● ERROR"
        header = f"SIEGARD MONITOR  [—]  seq=?  {badge}"
    elif state is None:
        badge = "● WAIT"
        header = f"SIEGARD MONITOR  [—]  seq=?  {badge}"
    elif active_wf:
        phase_label = active_wf["current_phase"] or "—"
        badge = "● DONE" if active_wf["status"] == "done" else "● LIVE"
        wf_label = _trunc(active_wf_id or "—", max(10, cols - 50))
        header = f"SIEGARD MONITOR  {wf_label}  [{phase_label}]  seq={active_wf['last_seq']}  {badge}"
    else:
        phase_label = state.current_phase or "—"
        badge = "● DONE" if state.run_status == "completed" else "● LIVE"
        header = f"SIEGARD MONITOR  [{phase_label}]  seq={state.last_seq}  {badge}"

    _addstr(stdscr, row, 0, header, curses.color_pair(C_HEADER) | curses.A_BOLD)
    row += 1

    # ---- Project path ----
    if project_dir is not None:
        orch_found = (project_dir / ".orch" / "log.jsonl").exists()
        path_str = _trunc(str(project_dir), cols - 16)
        if orch_found:
            _addstr(stdscr, row, 0, f"  {path_str}", curses.color_pair(C_DIM) | curses.A_DIM)
        else:
            _addstr(stdscr, row, 0, f"  {path_str}  (orch not found)",
                    curses.color_pair(C_ALERT))
        row += 1

    _hline(stdscr, row, 0, "─", cols - 1)
    row += 1

    if error:
        _addstr(stdscr, row, 2, error, curses.color_pair(C_ALERT))
        stdscr.refresh()
        return

    if state is None:
        _addstr(stdscr, row, 2, "waiting for log…", curses.color_pair(C_PENDING))
        _addstr(stdscr, row + 1, 2, str(log_path), curses.color_pair(C_DIM) | curses.A_DIM)
        stdscr.refresh()
        return

    # ---- Alerts ----
    if state.circuit_breaker:
        cb = state.circuit_breaker
        _addstr(stdscr, row, 0, f"  ⚡ CIRCUIT BREAKER TRIPPED  failures={cb.get('failure_count', '?')}",
                curses.color_pair(C_ALERT) | curses.A_BOLD)
        row += 1

    if state.escalation:
        esc = state.escalation
        code = esc.get("code", "?")
        reason = _trunc(esc.get("reason", ""), cols - 20)
        _addstr(stdscr, row, 0, f"  ⚠  ESCALATION {code}: {reason}",
                curses.color_pair(C_ALERT) | curses.A_BOLD)
        row += 1

    # ---- Phases ----
    _addstr(stdscr, row, 0, "PHASES", curses.A_BOLD)
    row += 1

    phases_src = active_phases or (state.phases if state else {})
    if phases_src:
        for name, p in sorted(phases_src.items(), key=lambda kv: kv[1].order):
            if row >= rows - 2:
                break
            ps_raw = p.status.value if hasattr(p.status, "value") else str(p.status)
            try:
                ps = PhaseStatus(ps_raw)
            except ValueError:
                ps = PhaseStatus.PENDING

            icon = PHASE_ICON.get(ps, "○")
            color = (C_DONE if ps == PhaseStatus.COMPLETED else
                     C_RUNNING if ps == PhaseStatus.ACTIVE else
                     C_PENDING)

            if ps == PhaseStatus.ACTIVE:
                ts = _short_ts(p.entered_at)
                qualifier = f"(active since {ts})"
            elif ps in (PhaseStatus.COMPLETED, PhaseStatus.EXIT_APPROVED):
                ts = _short_ts(p.completed_at or p.approved_at)
                qualifier = f"(completed {ts})"
            elif ps == PhaseStatus.PAUSED:
                qualifier = "(paused)"
            else:
                qualifier = ""

            criteria_str = ""
            if p.criteria_met:
                criteria_str = f"  [{len(p.criteria_met)} criteria met]"

            line = f"  {icon} {name}  {qualifier}{criteria_str}"
            _addstr(stdscr, row, 0, line, curses.color_pair(color))
            row += 1
    else:
        _addstr(stdscr, row, 2, "(no phases declared)", curses.color_pair(C_DIM) | curses.A_DIM)
        row += 1

    row += 1  # spacer
    if row >= rows - 2:
        stdscr.refresh()
        return

    # ---- Agents ----
    if workflows:
        all_running: list[dict] = []
        done_count = 0
        failed_count = 0
        for w in workflows.values():
            all_running.extend(_filter_orchestrators(w["agents_running"], False))
            done_count += len(_filter_orchestrators(w["agents_executed"], False))
            failed_count += len(_filter_orchestrators(w["agents_failed"], False))

        _addstr(stdscr, row, 0, "AGENTS", curses.A_BOLD)
        summary = f"  {len(all_running)} running · {done_count} done · {failed_count} failed"
        _addstr(stdscr, row, 6, summary, curses.color_pair(C_DIM) | curses.A_DIM)
        row += 1

        if not all_running:
            current_phase = (active_wf["current_phase"] if active_wf else None) or (state.current_phase if state else None)
            is_live = (active_wf["status"] == "active") if active_wf else (state and state.run_status != "completed")
            if current_phase and is_live:
                _addstr(stdscr, row, 2, f"⟳ {current_phase}  [orchestrator dispatching…]",
                        curses.color_pair(C_PENDING) | curses.A_DIM)
            else:
                _addstr(stdscr, row, 2, "(no agents running)", curses.color_pair(C_DIM) | curses.A_DIM)
            row += 1
        else:
            _a_col_wt  = 2
            _a_col_tid = 32
            _a_col_ts  = 52
            _a_col_cp  = 59

            for a in all_running:
                if row >= rows - 2:
                    break
                wt      = _trunc(a.get("worker_type") or "—", 28)
                tid     = _trunc(a.get("task_id") or "—", 18)
                claimed = _short_ts(a.get("claimed_at"))
                attempt = a.get("attempt", 1)
                cp      = a.get("last_progress")
                att_str = f"×{attempt} " if attempt > 1 else ""
                cp_str  = f"→ {_trunc(cp, cols - _a_col_cp - len(att_str) - 2)}" if cp else ""

                _addstr(stdscr, row, _a_col_wt,  f"▶ {wt}", curses.color_pair(C_RUNNING))
                _addstr(stdscr, row, _a_col_tid, tid,       curses.color_pair(C_DIM))
                _addstr(stdscr, row, _a_col_ts,  claimed,   curses.color_pair(C_DIM))
                cp_col = _a_col_cp
                if att_str:
                    _addstr(stdscr, row, cp_col, att_str, curses.color_pair(C_PENDING) | curses.A_DIM)
                    cp_col += len(att_str)
                if cp_str:
                    _addstr(stdscr, row, cp_col, cp_str, curses.color_pair(C_RUNNING) | curses.A_DIM)
                row += 1

        row += 1  # spacer
        if row >= rows - 2:
            stdscr.refresh()
            return

    # ---- Tasks ----
    _addstr(stdscr, row, 0, "TASKS", curses.A_BOLD)
    row += 1

    by_status: dict[TaskStatus, list] = {s: [] for s in STATUS_ORDER}
    tasks_src = active_tasks if active_tasks else (state.tasks if state else {})
    for t in tasks_src.values():
        try:
            s = t.status if isinstance(t.status, TaskStatus) else TaskStatus(t.status)
        except ValueError:
            s = TaskStatus.PENDING
        by_status.setdefault(s, []).append(t)

    col_id = 2
    col_status = 20
    col_worker = 36
    col_ts = 62
    col_extra = 70

    for status in STATUS_ORDER:
        if row >= rows - 2:
            break
        tasks = by_status.get(status, [])
        if not tasks:
            continue

        color = curses.color_pair(STATUS_COLOR.get(status, C_DIM))

        if status == TaskStatus.COMPLETED:
            _addstr(stdscr, row, col_id,
                    f"✓ completed ({len(tasks)})",
                    curses.color_pair(C_DONE) | curses.A_DIM)
            row += 1
            continue

        for t in tasks:
            if row >= rows - 2:
                break
            icon = STATUS_ICON.get(status, "?")
            tid = _trunc(t.task_id, 16)
            stat_label = f"[{status.value}]"
            worker = _trunc(t.worker_id or "—", 24)
            ts = _short_ts(t.claimed_at if status == TaskStatus.RUNNING else t.last_event_at)

            extras = []
            if t.attempts > 1:
                extras.append(f"attempt {t.attempts}/{t.max_attempts}")
            if status == TaskStatus.RUNNING:
                cp = _last_checkpoint(t.task_id)
                if cp:
                    extras.append(f"→ {cp}")
            if status == TaskStatus.DLQ and t.last_failure_reason:
                extras.append(_trunc(t.last_failure_reason, 20))
            if status == TaskStatus.SCHEDULED and t.next_retry_at:
                extras.append(f"retry@{_short_ts(t.next_retry_at)}")
            extra_str = "  " + "  ".join(extras) if extras else ""

            _addstr(stdscr, row, col_id,     f"{icon} {tid}", color)
            _addstr(stdscr, row, col_status, stat_label, color)
            _addstr(stdscr, row, col_worker, worker, curses.color_pair(C_DIM))
            _addstr(stdscr, row, col_ts,     ts, curses.color_pair(C_DIM))
            if extra_str:
                _addstr(stdscr, row, col_extra, extra_str, color | curses.A_DIM)
            row += 1

    # ---- Footer ----
    if row < rows - 1:
        _hline(stdscr, rows - 1, 0, "─", cols - 1)
        now = datetime.now().strftime("%H:%M:%S")
        footer = f" q=quit  {now} "
        _addstr(stdscr, rows - 1, 0, footer, curses.color_pair(C_DIM) | curses.A_DIM)

    stdscr.refresh()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Siegard Monitor — live TUI")
    p.add_argument("--project-dir", default=None,
                   help="Path to target project (overrides ORCH_PROJECT_DIR)")
    p.add_argument("--interval", type=float, default=2.0,
                   help="Poll interval in seconds (default: 2)")
    p.add_argument("--once", action="store_true",
                   help="Render one frame to stdout and exit")
    p.add_argument("--workflow", default=None,
                   help="Filter --once output to a single workflow_id")
    p.add_argument("--running-only", action="store_true",
                   help="Hide workflows whose status is 'done' (--once only)")
    p.add_argument("--show-orchestrators", action="store_true",
                   help="Include orchestrator-* agents (default: hidden)")
    p.add_argument("--legacy", action="store_true",
                   help="Use the legacy single-workflow plain renderer (--once only)")
    return p.parse_args()


def run_once(project_dir: Path, args: argparse.Namespace) -> int:
    if args.legacy:
        state, error = _load_state(project_dir)
        render_plain(state, error)
        return 1 if error else 0

    workflows, error = _collect_workflow_index(project_dir)
    render_plain_multi(
        workflows, error,
        workflow_filter=args.workflow,
        running_only=args.running_only,
        show_orchestrators=args.show_orchestrators,
    )
    return 1 if error else 0


def run_live(stdscr: Any, project_dir: Path, interval: float) -> None:
    log_path = project_dir / ".orch" / "log.jsonl"

    curses.cbreak()
    stdscr.keypad(True)
    stdscr.nodelay(True)
    _init_colors()

    last_stat: tuple[float, int] = (-1.0, -1)
    state: OrchState | None = None
    error: str | None = None
    workflows: dict[str, dict] = {}

    tick_ms = 100  # key responsiveness
    ticks_per_poll = max(1, int(interval * 1000 / tick_ms))
    tick_count = ticks_per_poll  # force immediate load on first frame

    while True:
        # Key handling
        try:
            key = stdscr.getch()
        except curses.error:
            key = -1

        if key in (ord("q"), ord("Q"), 27):  # q or ESC
            return

        tick_count += 1
        if tick_count >= ticks_per_poll:
            tick_count = 0
            current_stat = _stat_key(log_path)
            if current_stat != last_stat:
                last_stat = current_stat
                state, error = _load_state(project_dir)
                workflows, _ = _collect_workflow_index(project_dir)
                render_curses(stdscr, state, error, log_path, workflows, project_dir)

        time.sleep(tick_ms / 1000)


def main() -> int:
    import locale
    locale.setlocale(locale.LC_ALL, "")
    args = _parse_args()
    # project_dir was already resolved early (before orch_core import).
    # Re-resolve here only if the user passed --project-dir explicitly.
    project_dir = Path(args.project_dir).resolve() if args.project_dir else _project_dir_early

    if args.once:
        return run_once(project_dir, args)

    try:
        curses.wrapper(run_live, project_dir, args.interval)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        # curses already restored terminal at this point
        print(f"monitor error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
