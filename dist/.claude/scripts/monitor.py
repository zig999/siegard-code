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
try:
    import curses
except ImportError:  # M9: curses is absent from the Windows stdlib; --once (plain) still works
    curses = None  # type: ignore[assignment]
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
_prev_orch_env = os.environ.get("ORCH_PROJECT_DIR")
os.environ["ORCH_PROJECT_DIR"] = str(_project_dir_early)

# ---------------------------------------------------------------------------
# Bootstrap: resolve lib relative to this script
# ---------------------------------------------------------------------------
_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (  # noqa: E402
    ORCHESTRATOR_STALE_SECONDS,
    CorruptedLogError,
    IllegalTransition,
    OrchState,
    PhaseStatus,
    TaskStatus,
    Tier,
    reduce_all,
    reduce_all_tolerant,
    read_events_filtered,
    is_blob_ref,
    load_blob_data,
)

# The env mutation above exists only so orch_core (just imported) computes its
# paths from the resolved project dir when monitor runs as a CLI. Restore the
# previous value so importing monitor AS A LIBRARY (tests, tooling) does not
# leak the CLI bootstrap into the host process — every monitor function takes
# project_dir explicitly and re-points orch_core per call.
if _prev_orch_env is None:
    os.environ.pop("ORCH_PROJECT_DIR", None)
else:
    os.environ["ORCH_PROJECT_DIR"] = _prev_orch_env

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "1.1.0"
MIN_COLS = 80
MIN_ROWS = 24

STATUS_ORDER = [
    TaskStatus.RUNNING,
    TaskStatus.READY,
    TaskStatus.PENDING,
    TaskStatus.SCHEDULED,
    TaskStatus.FAILED,
    TaskStatus.DLQ,
    TaskStatus.SKIPPED,
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
    TaskStatus.SKIPPED:   "⊘",
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
    TaskStatus.SKIPPED:   C_DIM,
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


@dataclass
class LoadError:
    """Structured reducer failure.

    `kind` drives rendering: "waiting" is a benign no-log sentinel; the others
    are real failures. `source` attributes blame: "log" means the log itself is
    inconsistent (an upstream emitter defect — NOT a monitor bug), "monitor"
    means the monitor failed internally. The locus fields (`seq`, `task_id`,
    `event_type`, `workflow_id`, `phase`) come from the offending event so the
    operator can pinpoint it without re-scanning the log. `__str__` yields the
    one-line message so legacy string consumers keep working.
    """

    kind: str                      # "waiting" | "illegal_transition" | "corrupted_log" | "internal"
    message: str
    seq: int | None = None
    task_id: str | None = None
    event_type: str | None = None
    workflow_id: str | None = None
    phase: str | None = None
    source: str = "monitor"        # "log" = upstream emitter fault, "monitor" = internal
    violations: list = field(default_factory=list)  # all illegal transitions (diagnostics)

    def __str__(self) -> str:
        return self.message


def _load_state(project_dir: Path) -> tuple[OrchState | None, LoadError | None]:
    """Return (state, error). error is None on success."""
    import orch_core as _oc
    # Re-resolve paths in case project_dir changed (supports dynamic reload).
    orch_dir = project_dir / ".orch"
    log = orch_dir / "log.jsonl"
    if not log.exists():
        return None, LoadError(kind="waiting", message="waiting for log…")
    # Point orch_core to the right directory before calling reduce_all.
    _oc.ORCH_DIR = orch_dir
    _oc.LOG_PATH = log
    try:
        state = reduce_all()
        return state, None
    except CorruptedLogError as exc:
        return None, LoadError(kind="corrupted_log", message=f"CORRUPTED LOG: {exc}", source="log")
    except IllegalTransition as exc:
        # Re-reduce tolerantly to enumerate EVERY violation, not just the first.
        try:
            _, violations = reduce_all_tolerant()
        except Exception:  # noqa: BLE001
            violations = []
        return None, LoadError(
            kind="illegal_transition",
            message=f"ILLEGAL TRANSITION: {exc}",
            seq=exc.seq,
            task_id=exc.task_id,
            event_type=exc.event_type,
            workflow_id=exc.workflow_id,
            phase=exc.phase,
            source="log",
            violations=violations,
        )
    except Exception as exc:  # noqa: BLE001
        return None, LoadError(kind="internal", message=f"ERROR: {exc}", source="monitor")


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
        "agents_failed": [],     # last terminal event = task_failed (true failures only)
        "agents_dlq": [],        # last terminal event = task_dlq
        "agents_skipped": [],    # last terminal event = task_skipped (expected non-execution)
        "phase_details": {},   # phase_name → {status, order, entered_at, completed_at, approved_at, criteria_met}
        "task_statuses": {},   # task_id → current task state dict
        "heartbeats": {},      # phase_name → ts of the last orchestrator_heartbeat
    }


def _collect_workflow_index(project_dir: Path) -> tuple[dict[str, dict], str | None]:
    """
    Re-scan the log and group events by workflow_id.

    Attribution mirrors orch_core.reduce_workflow (parity is load-bearing —
    the monitor must agree with the engine's derived state):
    1. explicit `data.workflow_id` on the event;
    2. task→workflow binding from the task's `task_created` (5-a: orchestrators
       stamp workflow_id there) — task_created itself attributes explicit→
       positional and REBINDS the id (legacy reuse);
    3. positional: every event between one phase_declared and the next belongs
       to that workflow. Events before any phase_declared land in UNKNOWN_WORKFLOW.

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
    # 5-a parity with reduce_workflow: task_id → workflow binding from task_created.
    task_wf: dict[str, str] = {}

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

        # Attribution parity with orch_core.reduce_workflow (see docstring).
        if et == "task_created":
            wf = data.get("workflow_id") or current_wf or UNKNOWN_WORKFLOW
            if event.task_id and wf != UNKNOWN_WORKFLOW:
                task_wf[event.task_id] = wf
        else:
            wf = (
                data.get("workflow_id")
                or (task_wf.get(event.task_id) if event.task_id else None)
                or current_wf
                or UNKNOWN_WORKFLOW
            )
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
        elif et == "orchestrator_heartbeat":
            pname = data.get("phase")
            if pname:
                w["heartbeats"][pname] = event.ts

        # --- task_statuses: per-task_id current state (for TASKS section) ---
        if et in _TASK_EVENT_TYPES and event.task_id:
            tid = event.task_id
            ts_map = w["task_statuses"]
            ts = ts_map.setdefault(tid, {
                "task_id": tid,
                "status": "pending",
                "worker_id": None,
                "worker_type": None,
                "attempts": 0,
                "max_attempts": data.get("max_attempts", 3),
                "claimed_at": None,
                "created_at": None,
                "last_event_at": None,
                "last_failure_reason": None,
                "last_error": None,
                "next_retry_at": None,
                # Eixo A — rich fields previously discarded (now carried for the UI):
                "phase": data.get("phase"),
                "task_type": None,
                "tier": None,
                "stack": None,
                "deps": [],
                "spec": None,
                "artifacts": [],
                "last_progress": None,
            })
            ts["last_event_at"] = event.ts
            if data.get("phase"):
                ts["phase"] = data.get("phase")
            if et == "task_created":
                ts["status"] = "pending"
                ts["created_at"] = event.ts
                ts["max_attempts"] = data.get("max_attempts", ts["max_attempts"])
                ts["task_type"] = data.get("type", ts["task_type"])
                ts["tier"] = data.get("tier", ts["tier"])
                ts["stack"] = data.get("stack", ts["stack"])
                ts["spec"] = data.get("spec", ts["spec"])
                deps = data.get("deps")
                if isinstance(deps, list):
                    ts["deps"] = list(deps)
            elif et == "task_claimed":
                ts["status"] = "running"
                ts["worker_id"] = data.get("worker_id")
                ts["worker_type"] = data.get("worker_type", ts["worker_type"])
                ts["claimed_at"] = event.ts
                ts["attempts"] += 1
            elif et == "task_progress":
                cp = data.get("checkpoint") or data.get("note")
                if cp:
                    ts["last_progress"] = cp
            elif et == "task_completed":
                ts["status"] = "completed"
                arts = data.get("artifacts")
                if isinstance(arts, list):
                    ts["artifacts"] = [a for a in arts if isinstance(a, str)]
            elif et == "task_failed":
                ts["status"] = "failed"
                ts["last_failure_reason"] = data.get("reason")
                ts["last_error"] = data.get("error") or ts["last_error"]
            elif et == "task_scheduled_retry":
                ts["status"] = "scheduled"
                ts["next_retry_at"] = data.get("next_retry_at")
            elif et == "task_retried":
                ts["status"] = "running"
            elif et == "task_dlq":
                ts["status"] = "dlq"
                ts["last_failure_reason"] = data.get("reason")
                ts["last_error"] = data.get("last_error") or ts["last_error"]
            elif et == "task_skipped":
                ts["status"] = "skipped"
                ts["last_failure_reason"] = data.get("reason") or ts["last_failure_reason"]

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
            elif et in ("task_failed", "task_dlq", "task_skipped"):
                te["reason"] = data.get("reason")

    # Materialize per-workflow agent lists from task_state.
    # Each terminal kind has its own bucket so the UI can show the real exit
    # state instead of lumping skipped/dlq tasks under "failed".
    for wf_id, te_map in task_state.items():
        w = workflows.setdefault(wf_id, _new_workflow_record())
        for te in te_map.values():
            kind = te.get("last_event_type")
            if kind == "task_completed":
                w["agents_executed"].append(te)
            elif kind == "task_failed":
                w["agents_failed"].append(te)
            elif kind == "task_dlq":
                w["agents_dlq"].append(te)
            elif kind == "task_skipped":
                w["agents_skipped"].append(te)
            elif kind in ("task_claimed", "task_progress", "task_retried"):
                w["agents_running"].append(te)
            # task_created / task_scheduled_retry alone → not yet in flight; skip

        w["agents_running"].sort(key=lambda x: x.get("claimed_at") or "")
        for bucket in ("agents_executed", "agents_failed", "agents_dlq", "agents_skipped"):
            w[bucket].sort(key=lambda x: x.get("last_event_at") or "")

    return workflows, None


def _find_active_workflow(workflows: dict[str, dict]) -> tuple[str, dict] | None:
    """Return (workflow_id, record) for the most recently active workflow, or None."""
    active = [(wf_id, w) for wf_id, w in workflows.items() if w["status"] == "active"]
    if not active:
        return None
    return max(active, key=lambda item: item[1]["last_seq"] or 0)


def _open_workflows(workflows: dict[str, dict], *, show_all: bool = False) -> list[tuple[str, dict]]:
    """Selectable workflows, most-recent first.

    "Open" = real workflow (not the orphan bucket) that is not done. With
    show_all=True the orphan bucket and completed workflows are included too.
    """
    items = []
    for wf_id, w in workflows.items():
        if not show_all:
            if wf_id == UNKNOWN_WORKFLOW or w.get("status") == "done":
                continue
        items.append((wf_id, w))
    items.sort(key=lambda kv: -(kv[1]["last_seq"] or 0))
    return items


def _focused_workflow(workflows: dict[str, dict], ui: "UIState | None") -> tuple[str | None, dict | None]:
    """Resolve the workflow in focus for single-workflow rendering.

    Explicit selection wins when still present; otherwise fall back to the
    most-recent open workflow (or the most-recent of any, last resort). Pure:
    never mutates `ui` — reopening the picker is decided in the live loop.
    """
    if ui is not None and ui.selected_wf and ui.selected_wf in workflows:
        return ui.selected_wf, workflows[ui.selected_wf]
    open_wfs = _open_workflows(workflows)
    if open_wfs:
        return open_wfs[0]
    if workflows:
        return max(workflows.items(), key=lambda kv: kv[1]["last_seq"] or 0)
    return None, None


def _reresolve_focus(workflows: dict[str, dict], ui: "UIState") -> None:
    """After a poll, repair the focus if the selected workflow vanished.

    One open workflow left → auto-focus it. Several → drop the selection and
    reopen the picker. None → leave it (the waiting screen takes over).
    """
    if ui.selected_wf and ui.selected_wf not in workflows:
        open_wfs = _open_workflows(workflows)
        if len(open_wfs) == 1:
            ui.selected_wf = open_wfs[0][0]
        elif open_wfs:
            ui.selected_wf = None
            ui.picker = True


def _init_focus(workflows: dict[str, dict], ui: "UIState") -> None:
    """First-frame focus decision (after the initial index load).

    --workflow seed (already on ui.selected_wf) is honored. Otherwise: exactly
    one open workflow auto-focuses; two or more open the picker; none leaves the
    waiting screen.
    """
    if ui.selected_wf and ui.selected_wf in workflows:
        return
    open_wfs = _open_workflows(workflows)
    if len(open_wfs) == 1:
        ui.selected_wf = open_wfs[0][0]
    elif len(open_wfs) >= 2:
        ui.picker = True


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
            worker_type=ts.get("worker_type"),
            attempts=ts.get("attempts", 1),
            max_attempts=ts.get("max_attempts", 3),
            claimed_at=ts.get("claimed_at"),
            created_at=ts.get("created_at"),
            last_event_at=ts.get("last_event_at"),
            last_failure_reason=ts.get("last_failure_reason"),
            last_error=ts.get("last_error"),
            next_retry_at=ts.get("next_retry_at"),
            # Eixo A — rich fields:
            phase=ts.get("phase"),
            task_type=ts.get("task_type"),
            tier=ts.get("tier"),
            stack=ts.get("stack"),
            deps=ts.get("deps", []),
            spec=ts.get("spec"),
            artifacts=ts.get("artifacts", []),
            last_progress=ts.get("last_progress"),
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
# Eixo B — responsive layout + scroll + detail panel
# ---------------------------------------------------------------------------

class UIState:
    """Mutable interaction state held across frames in the live loop."""
    def __init__(self) -> None:
        self.sel = 0          # selected task index (into the task entries of the row model)
        self.scroll = 0       # first visible display row (TASKS viewport top)
        self.detail = False   # detail panel open for the selected task
        self.events = False   # recent-events feed open
        self.dispatch = False # dispatch-decisions panel open (Spec A)
        # Single-workflow focus model (default live view).
        self.selected_wf: str | None = None   # workflow in focus (None = not chosen yet)
        self.picker = False                    # workflow-selector screen open
        self.picker_show_all = False           # include done/orphan workflows in the picker
        self.wf_sel = 0                        # cursor index within the picker list


def _alloc_widths(avail: int, spec: list[tuple[str, int, int]]) -> dict[str, int]:
    """Distribute `avail` columns across `spec` entries (name, min_width, weight).

    Every column gets at least its min_width; leftover space is shared by weight.
    The last column absorbs the rounding remainder so the row fills `avail` exactly.
    """
    total_min = sum(m for _, m, _ in spec)
    total_weight = sum(w for _, _, w in spec) or 1
    leftover = max(0, avail - total_min)
    widths: dict[str, int] = {}
    assigned = 0
    for idx, (name, m, w) in enumerate(spec):
        if idx == len(spec) - 1:
            extra = leftover - assigned
        else:
            extra = (leftover * w) // total_weight
            assigned += extra
        widths[name] = max(m, m + extra)
    return widths


def _wrap(text: str, width: int) -> list[str]:
    """Word-wrap `text` to `width`; hard-splits tokens longer than the line."""
    if width <= 0:
        return [text]
    out: list[str] = []
    for raw_line in str(text).splitlines() or [""]:
        line = ""
        for word in raw_line.split(" "):
            while len(word) > width:
                if line:
                    out.append(line)
                    line = ""
                out.append(word[:width])
                word = word[width:]
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= width:
                line += " " + word
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def _task_detail_lines(t: Any) -> list[tuple[str, str]]:
    """Build (label, value) rows for the detail panel — nothing truncated here."""
    def _fmt(v: Any) -> str:
        if v is None or v == "":
            return "—"
        if isinstance(v, (list, tuple)):
            return ", ".join(str(x) for x in v) if v else "—"
        return str(v)

    status = t.status.value if isinstance(t.status, TaskStatus) else str(t.status)
    return [
        ("task_id",   _fmt(t.task_id)),
        ("status",    _fmt(status)),
        ("phase",     _fmt(getattr(t, "phase", None))),
        ("type",      _fmt(getattr(t, "task_type", None))),
        ("tier",      _fmt(getattr(t, "tier", None))),
        ("stack",     _fmt(getattr(t, "stack", None))),
        ("worker",    _fmt(getattr(t, "worker_id", None) or getattr(t, "worker_type", None))),
        ("attempts",  f"{getattr(t, 'attempts', 1)}/{getattr(t, 'max_attempts', 3)}"),
        ("deps",      _fmt(getattr(t, "deps", []))),
        ("spec",      _fmt(getattr(t, "spec", None))),
        ("artifacts", _fmt(getattr(t, "artifacts", []))),
        ("progress",  _fmt(getattr(t, "last_progress", None))),
        ("failure",   _fmt(getattr(t, "last_failure_reason", None))),
        ("error",     _fmt(getattr(t, "last_error", None))),
        ("next_retry", _fmt(getattr(t, "next_retry_at", None))),
        ("created",   _fmt(getattr(t, "created_at", None))),
        ("claimed",   _fmt(getattr(t, "claimed_at", None))),
        ("last_event", _fmt(getattr(t, "last_event_at", None))),
    ]


# ---------------------------------------------------------------------------
# Eixo C/D — phase grouping, progress, dependency state, durations
# ---------------------------------------------------------------------------

_DONE_STATUSES = {TaskStatus.COMPLETED, TaskStatus.SKIPPED}
_spec_title_cache: dict[str, tuple[float, str | None]] = {}


def _elapsed_s(iso: str | None) -> float | None:
    """Seconds elapsed since `iso` (UTC), or None if unparseable. Clamped to >= 0."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None
    now = datetime.now(timezone.utc)
    return max(0.0, (now - dt).total_seconds())


def _fmt_dur(seconds: float | None) -> str:
    """Human-friendly duration: 12s / 3m20s / 1h04m."""
    if seconds is None:
        return "—"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


# Single source of truth: orch_core.ORCHESTRATOR_STALE_SECONDS. The live TUI, the
# session-end hook (on_stop.py), and the Step 5.0 check (check_stale.py) all agree
# on what "stalled" means by deriving from the same constant.
ORCH_HEARTBEAT_STALE_S = ORCHESTRATOR_STALE_SECONDS


def _orchestrator_stall(wf: dict | None, threshold: int = ORCH_HEARTBEAT_STALE_S) -> dict | None:
    """Detect a stalled-but-alive orchestrator for the live TUI.

    Alert condition: the focused workflow's current phase is active, it has
    open (non-terminal) tasks, NONE of them is running (a running worker means
    the orchestrator is legitimately blocked waiting on the Agent tool), and
    the last orchestrator_heartbeat for that phase — or the phase entry, when
    no heartbeat was ever emitted — is older than `threshold` seconds.

    Returns {"phase", "age", "last_heartbeat", "open_tasks"} or None.
    """
    if not wf or wf.get("status") != "active":
        return None
    phase = wf.get("current_phase")
    if not phase:
        return None
    pd = (wf.get("phase_details") or {}).get(phase) or {}
    if pd.get("status") != "active":
        return None  # paused/pending phases are waiting by design, not stalled
    open_statuses = [
        ts.get("status") for ts in (wf.get("task_statuses") or {}).values()
        if ts.get("phase") == phase
        and ts.get("status") not in ("completed", "dlq", "skipped", "cancelled")
    ]
    if not open_statuses:
        return None
    if any(s == "running" for s in open_statuses):
        return None
    hb_ts = (wf.get("heartbeats") or {}).get(phase)
    age = _elapsed_s(hb_ts or pd.get("entered_at"))
    if age is None or age < threshold:
        return None
    return {
        "phase": phase,
        "age": age,
        "last_heartbeat": hb_ts,
        "open_tasks": len(open_statuses),
    }


def _stale_threshold(tier: str | None) -> int:
    """Stale threshold (seconds) for a tier, from orch_core. Falls back to standard."""
    try:
        return int(Tier(tier).default_stale_seconds)
    except Exception:
        try:
            return int(Tier.STANDARD.default_stale_seconds)
        except Exception:
            return 300


def _stale_level(elapsed: float | None, tier: str | None) -> int:
    """0 = fresh, 1 = stale (> threshold), 2 = very stale (> 2× threshold)."""
    if elapsed is None:
        return 0
    thr = _stale_threshold(tier)
    if elapsed > 2 * thr:
        return 2
    if elapsed > thr:
        return 1
    return 0


def _checkpoints(task_id: str, n: int = 8) -> list[tuple[str, str]]:
    """Return up to `n` recent (ts, label) progress checkpoints for a task."""
    try:
        events = read_events_filtered(task_id=task_id, event_type="task_progress", tail=n)
    except Exception:
        return []
    out: list[tuple[str, str]] = []
    for ev in events:
        data = ev.data
        if is_blob_ref(data):
            try:
                data = load_blob_data(ev)
            except Exception:
                data = {}
        label = data.get("checkpoint") or data.get("note")
        if label:
            out.append((ev.ts, str(label)))
    return out


def _spec_title(spec: str | None, project_dir: Path | None) -> str | None:
    """Read a human title from the task's spec file frontmatter (cached by mtime)."""
    if not spec or project_dir is None:
        return None
    path = (project_dir / spec)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _spec_title_cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    title: str | None = None
    try:
        with path.open("r", encoding="utf-8") as fh:
            for _ in range(40):  # scan only the head of the file
                line = fh.readline()
                if not line:
                    break
                m = line.strip()
                low = m.lower()
                if low.startswith("title:") or low.startswith("objective:"):
                    title = m.split(":", 1)[1].strip().strip('"').strip("'") or None
                    break
                if m.startswith("# "):
                    title = m[2:].strip()
                    break
    except OSError:
        title = None
    _spec_title_cache[str(path)] = (mtime, title)
    return title


def _phase_counts(tasks_src: dict) -> dict[str, dict[TaskStatus, int]]:
    """Group tasks by phase → {status: count}."""
    counts: dict[str, dict[TaskStatus, int]] = {}
    for t in tasks_src.values():
        ph = getattr(t, "phase", None) or "(no phase)"
        try:
            s = t.status if isinstance(t.status, TaskStatus) else TaskStatus(t.status)
        except ValueError:
            s = TaskStatus.PENDING
        bucket = counts.setdefault(ph, {})
        bucket[s] = bucket.get(s, 0) + 1
    return counts


def _dep_state(task: Any, status_map: dict[str, TaskStatus]) -> tuple[str, list[str]]:
    """For a pending task, classify as ('ready', []) or ('blocked', [unmet deps])."""
    unmet: list[str] = []
    for dep in getattr(task, "deps", []) or []:
        st = status_map.get(dep)
        if st not in _DONE_STATUSES:
            unmet.append(dep)
    return ("blocked", unmet) if unmet else ("ready", [])


def _progress_bar(done: int, total: int, width: int) -> str:
    """Unicode progress bar of `width` cells."""
    width = max(1, width)
    if total <= 0:
        return "░" * width
    filled = round(done / total * width)
    filled = max(0, min(width, filled))
    return "▓" * filled + "░" * (width - filled)


def _build_rows(tasks_src: dict, phase_order: list[str],
                status_map: dict[str, TaskStatus]) -> list[dict]:
    """Build the unified TASKS row model: phase headers + tasks.

    Returns a list of {"kind": "header"|"task", ...}. Tasks are grouped by phase
    (in `phase_order`, unknown phases last) and within a phase by STATUS_ORDER.
    Each task entry carries its dependency classification for pending tasks.
    """
    by_phase: dict[str, list] = {}
    for t in tasks_src.values():
        ph = getattr(t, "phase", None) or "(no phase)"
        by_phase.setdefault(ph, []).append(t)

    ordered_phases = [p for p in phase_order if p in by_phase]
    ordered_phases += [p for p in by_phase if p not in phase_order]

    status_rank = {s: i for i, s in enumerate(STATUS_ORDER)}
    rows: list[dict] = []
    for ph in ordered_phases:
        group = by_phase[ph]

        def _rank(t: Any) -> tuple[int, str]:
            try:
                s = t.status if isinstance(t.status, TaskStatus) else TaskStatus(t.status)
            except ValueError:
                s = TaskStatus.PENDING
            return (status_rank.get(s, 99), t.task_id)

        group.sort(key=_rank)
        done = sum(1 for t in group
                   if (t.status if isinstance(t.status, TaskStatus) else TaskStatus(t.status)) in _DONE_STATUSES)
        rows.append({"kind": "header", "phase": ph, "done": done, "total": len(group)})
        for t in group:
            try:
                s = t.status if isinstance(t.status, TaskStatus) else TaskStatus(t.status)
            except ValueError:
                s = TaskStatus.PENDING
            dep = _dep_state(t, status_map) if s in (TaskStatus.PENDING, TaskStatus.READY) else ("", [])
            rows.append({"kind": "task", "task": t, "status": s, "dep": dep})
    return rows


def _build_rows_multi(workflows: dict, *, show_orchestrators: bool = True) -> list[dict]:
    """Build the unified TASKS row model across ALL workflows.

    Three row kinds: "workflow" → "header" (phase) → "task". Workflows are
    ordered by last_seq descending (most recent first). Within each workflow,
    phase grouping and task ordering are delegated to _build_rows, so the
    single-workflow and multi-workflow views share one source of truth.

    A workflow header is ALWAYS emitted — even for a single workflow or a
    workflow with no tasks yet (only phase_declared) — so the hierarchy is
    uniform and deterministic.

    Dependency classification is computed per-workflow: deps reference task_ids
    within the same workflow, so a cross-workflow status_map would misclassify.
    """
    rows: list[dict] = []
    items = sorted(workflows.items(), key=lambda kv: -(kv[1]["last_seq"] or 0))
    for wf_id, w in items:
        tasks_src = _wf_tasks(w)
        if not show_orchestrators:
            tasks_src = {
                tid: t for tid, t in tasks_src.items()
                if not _is_orchestrator_agent(getattr(t, "worker_type", None))
            }
        wf_phases = _wf_phases(w)
        phase_order = [n for n, _ in sorted(wf_phases.items(), key=lambda kv: kv[1].order)]
        status_map: dict[str, TaskStatus] = {}
        for tid, t in tasks_src.items():
            try:
                status_map[tid] = t.status if isinstance(t.status, TaskStatus) else TaskStatus(t.status)
            except ValueError:
                status_map[tid] = TaskStatus.PENDING
        done = sum(1 for s in status_map.values() if s in _DONE_STATUSES)
        rows.append({
            "kind": "workflow",
            "workflow_id": wf_id,
            "status": w.get("status", "unknown"),
            "current_phase": w.get("current_phase"),
            "last_seq": w.get("last_seq", 0),
            "done": done,
            "total": len(tasks_src),
        })
        rows.extend(_build_rows(tasks_src, phase_order, status_map))
    return rows


# ---------------------------------------------------------------------------
# Plain-text renderer (--once mode)
# ---------------------------------------------------------------------------

def render_plain(state: OrchState | None, error: LoadError | None) -> None:
    if error:
        print(f"  {error}")
        if len(error.violations) > 1:
            print(f"  all violations ({len(error.violations)}):")
            for v in error.violations:
                seq_s = v.seq if v.seq is not None else "?"
                print(f"    seq={seq_s}  {v.event_type or ''}  task={v.task_id or '—'}  {v.message}")
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

        # Per-workflow tasks grouped phase → task (shared grouping with the live TUI).
        tasks_src = _wf_tasks(w)
        if not show_orchestrators:
            tasks_src = {
                tid: t for tid, t in tasks_src.items()
                if not _is_orchestrator_agent(getattr(t, "worker_type", None))
            }
        status_map: dict[str, TaskStatus] = {}
        for tid, t in tasks_src.items():
            try:
                status_map[tid] = t.status if isinstance(t.status, TaskStatus) else TaskStatus(t.status)
            except ValueError:
                status_map[tid] = TaskStatus.PENDING
        done = sum(1 for s in status_map.values() if s in _DONE_STATUSES)
        print(f"▼ {wf_label}  [{phase}]  {done}/{len(tasks_src)}  seq={w['last_seq']}  {badge}")

        wf_phases = _wf_phases(w)
        phase_order = [n for n, _ in sorted(wf_phases.items(), key=lambda kv: kv[1].order)]
        prows = _build_rows(tasks_src, phase_order, status_map)

        if not prows:
            if status == "active":
                print(f"   ⟳ {phase}  [orchestrator dispatching…]")
            else:
                hint = "" if show_orchestrators else " (run with --show-orchestrators to include meta agents)"
                print(f"   (no task activity recorded{hint})")
            print()
            continue

        for e in prows:
            if e["kind"] == "header":
                print(f"   ── {e['phase']} ──  {e['done']}/{e['total']}")
                continue
            t = e["task"]
            s = e["status"]
            icon = STATUS_ICON.get(s, "?")
            worker = getattr(t, "worker_id", None) or getattr(t, "worker_type", None) or "—"
            ts = _short_ts(t.claimed_at if s == TaskStatus.RUNNING else t.last_event_at)
            detail = ""
            if s == TaskStatus.RUNNING:
                detail = getattr(t, "last_progress", None) or ""
            elif s == TaskStatus.SCHEDULED and getattr(t, "next_retry_at", None):
                detail = f"retry@{_short_ts(t.next_retry_at)}"
            elif s in (TaskStatus.FAILED, TaskStatus.DLQ):
                detail = getattr(t, "last_failure_reason", None) or ""
                err = getattr(t, "last_error", None)
                if err:
                    detail = f"{detail} — {err}" if detail else str(err)
            elif s in (TaskStatus.PENDING, TaskStatus.READY):
                dstate, unmet = e["dep"]
                detail = "waiting: " + ", ".join(unmet) if dstate == "blocked" else "ready"
            if getattr(t, "attempts", 1) > 1 and s != TaskStatus.RUNNING:
                detail = f"×{t.attempts}/{t.max_attempts}  {detail}".rstrip()
            detail = detail[:80]
            print(f"     {icon} {t.task_id[:18]:<18} [{s.value:<10}] {worker[:22]:<22} {ts}  {detail}".rstrip())
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


def render_detail(stdscr: Any, task: Any, rows: int, cols: int,
                  project_dir: Path | None = None) -> None:
    """Full-screen detail view for a single task — values are wrapped, never cut."""
    stdscr.erase()
    title = f"TASK DETAIL — {task.task_id}"
    _addstr(stdscr, 0, 0, _trunc(title, cols - 1), curses.color_pair(C_HEADER) | curses.A_BOLD)
    _hline(stdscr, 1, 0, "─", cols - 1)

    label_w = 11
    val_x = label_w + 3
    val_w = max(10, cols - val_x - 1)
    row = 2

    # C5 — human title from the task's spec file (best-effort, cached).
    lines = list(_task_detail_lines(task))
    spec_title = _spec_title(getattr(task, "spec", None), project_dir)
    if spec_title:
        lines.insert(1, ("title", spec_title))

    for label, value in lines:
        if row >= rows - 1:
            break
        wrapped = _wrap(value, val_w) or ["—"]
        _addstr(stdscr, row, 1, f"{label:<{label_w}}", curses.color_pair(C_DIM) | curses.A_BOLD)
        _addstr(stdscr, row, val_x, wrapped[0])
        row += 1
        for cont in wrapped[1:]:
            if row >= rows - 1:
                break
            _addstr(stdscr, row, val_x, cont)
            row += 1

    # D4 — progress history (recent checkpoints).
    history = _checkpoints(task.task_id, n=12)
    if history and row < rows - 2:
        row += 1
        _addstr(stdscr, row, 1, "progress history", curses.color_pair(C_HEADER) | curses.A_BOLD)
        row += 1
        for ts, label in history:
            if row >= rows - 1:
                break
            _addstr(stdscr, row, 2, _short_ts(ts), curses.color_pair(C_DIM) | curses.A_DIM)
            _addstr(stdscr, row, 9, _trunc(f"→ {label}", cols - 11), curses.color_pair(C_RUNNING))
            row += 1

    _hline(stdscr, rows - 1, 0, "─", cols - 1)
    _addstr(stdscr, rows - 1, 0, " Enter/Esc: back   q: quit ",
            curses.color_pair(C_DIM) | curses.A_DIM)
    stdscr.refresh()


def _collect_dispatch_decisions(project_dir: Path | None, n: int = 8) -> list[dict]:
    """Most-recent-first dispatch_decision records for the dispatch panel.

    Each record: {seq, ts, phase, batch: list, rationale: str, constraints: dict}.
    Blob-externalized payloads are resolved; malformed entries degrade to
    empty fields rather than raising.
    """
    try:
        import orch_core as _oc
        if project_dir is not None:
            _oc.ORCH_DIR = project_dir / ".orch"
            _oc.LOG_PATH = _oc.ORCH_DIR / "log.jsonl"
        events = list(read_events_filtered(event_type="dispatch_decision", tail=n))
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    for ev in events:
        data = ev.data
        if is_blob_ref(data):
            try:
                data = load_blob_data(ev)
            except Exception:  # noqa: BLE001
                data = {}
        batch = data.get("batch")
        constraints = data.get("constraints")
        out.append({
            "seq": ev.seq,
            "ts": ev.ts,
            "phase": data.get("phase"),
            "batch": batch if isinstance(batch, list) else [],
            "rationale": str(data.get("rationale") or ""),
            "constraints": constraints if isinstance(constraints, dict) else {},
        })
    out.reverse()  # most recent first
    return out


def render_dispatch(stdscr: Any, project_dir: Path | None, rows: int, cols: int) -> None:
    """Full-screen dispatch-decisions panel (toggle 'd') — Spec A.

    Answers "why is this task in the batch?": batch composition, the
    orchestrator's rationale, and the applied constraints (batch ceiling,
    context-budget mitigations) straight from dispatch_decision events.
    """
    stdscr.erase()
    _addstr(stdscr, 0, 0, "DISPATCH DECISIONS", curses.color_pair(C_HEADER) | curses.A_BOLD)
    _hline(stdscr, 1, 0, "─", cols - 1)

    decisions = _collect_dispatch_decisions(project_dir, n=8)
    row = 2
    if not decisions:
        _addstr(stdscr, row, 2, "(no dispatch_decision events yet)",
                curses.color_pair(C_DIM) | curses.A_DIM)
    else:
        for d in decisions:
            if row >= rows - 2:
                break
            head = f"seq={d['seq']}  {_short_ts(d['ts'])}  phase={d['phase'] or '—'}  batch={len(d['batch'])}"
            _addstr(stdscr, row, 1, _trunc(head, cols - 2),
                    curses.color_pair(C_RUNNING) | curses.A_BOLD)
            row += 1
            if d["rationale"] and row < rows - 2:
                _addstr(stdscr, row, 3, _trunc(f"rationale: {d['rationale']}", cols - 4),
                        curses.color_pair(C_DIM))
                row += 1
            for i, b in enumerate(d["batch"]):
                if row >= rows - 2:
                    break
                if not isinstance(b, dict):
                    b = {}
                branch = "└─" if i == len(d["batch"]) - 1 else "├─"
                meta = "·".join(p for p in (b.get("tier"), b.get("stack")) if p)
                line = f"{branch} {b.get('task_id') or '—'}  {b.get('worker_type') or '—'}"
                if meta:
                    line += f"  {meta}"
                _addstr(stdscr, row, 3, _trunc(line, cols - 4), curses.color_pair(C_DIM))
                row += 1
            cons = d["constraints"]
            bits = []
            if cons.get("max_batch") is not None:
                bits.append(f"max_batch={cons['max_batch']}")
            ce = cons.get("context_estimate")
            over = [c for c in (ce if isinstance(ce, list) else [])
                    if isinstance(c, dict) and c.get("over_threshold")]
            if over:
                migs = ", ".join(
                    f"{c.get('task_id', '?')}→{c.get('mitigation') or 'none'}" for c in over
                )
                bits.append(f"context: {len(over)} over threshold ({migs})")
            if bits and row < rows - 2:
                _addstr(stdscr, row, 3, _trunc("constraints: " + " · ".join(bits), cols - 4),
                        curses.color_pair(C_DIM) | curses.A_DIM)
                row += 1
            row += 1  # spacer between decisions

    _hline(stdscr, rows - 1, 0, "─", cols - 1)
    _addstr(stdscr, rows - 1, 0, " d/Esc: back   q: quit ",
            curses.color_pair(C_DIM) | curses.A_DIM)
    stdscr.refresh()


def render_events(stdscr: Any, project_dir: Path | None, rows: int, cols: int) -> None:
    """Full-screen recent-events feed (toggle 'e')."""
    stdscr.erase()
    _addstr(stdscr, 0, 0, "RECENT EVENTS", curses.color_pair(C_HEADER) | curses.A_BOLD)
    _hline(stdscr, 1, 0, "─", cols - 1)

    events: list = []
    err: str | None = None
    try:
        import orch_core as _oc
        if project_dir is not None:
            _oc.ORCH_DIR = project_dir / ".orch"
            _oc.LOG_PATH = _oc.ORCH_DIR / "log.jsonl"
        events = list(read_events_filtered(tail=max(1, rows - 4)))
    except Exception as exc:  # noqa: BLE001
        err = f"cannot read events: {exc}"

    if err:
        _addstr(stdscr, 2, 2, err, curses.color_pair(C_ALERT))
    elif not events:
        _addstr(stdscr, 2, 2, "(no events)", curses.color_pair(C_DIM) | curses.A_DIM)
    else:
        w = _alloc_widths(cols - 4, [
            ("seq", 6, 0), ("ts", 5, 0), ("type", 18, 1), ("task", 14, 1), ("info", 10, 3),
        ])
        x_seq = 2
        x_ts = x_seq + w["seq"] + 1
        x_type = x_ts + w["ts"] + 1
        x_task = x_type + w["type"] + 1
        x_info = x_task + w["task"] + 1
        row = 2
        for ev in events[-(rows - 3):]:
            if row >= rows - 1:
                break
            data = ev.data if not is_blob_ref(ev.data) else {}
            info = data.get("checkpoint") or data.get("note") or data.get("reason") \
                or data.get("phase") or data.get("code") or ""
            color = C_DIM
            et = ev.event_type
            if et in ("task_failed", "task_dlq", "escalation"):
                color = C_FAILED
            elif et == "task_completed":
                color = C_DONE
            elif et in ("task_claimed", "task_progress"):
                color = C_RUNNING
            _addstr(stdscr, row, x_seq, str(ev.seq), curses.color_pair(C_DIM) | curses.A_DIM)
            _addstr(stdscr, row, x_ts, _short_ts(ev.ts), curses.color_pair(C_DIM) | curses.A_DIM)
            _addstr(stdscr, row, x_type, _trunc(et, w["type"]), curses.color_pair(color))
            _addstr(stdscr, row, x_task, _trunc(ev.task_id or "—", w["task"]), curses.color_pair(C_DIM))
            if info:
                _addstr(stdscr, row, x_info, _trunc(str(info), max(1, cols - x_info - 1)),
                        curses.color_pair(C_DIM) | curses.A_DIM)
            row += 1

    _hline(stdscr, rows - 1, 0, "─", cols - 1)
    _addstr(stdscr, rows - 1, 0, " e/Esc: back   q: quit ",
            curses.color_pair(C_DIM) | curses.A_DIM)
    stdscr.refresh()


def _wf_counts(w: dict) -> tuple[int, int, int, int, int]:
    """(done, total, running, pending, failed) from a workflow's task_statuses."""
    done = total = running = pending = failed = 0
    for ts in w["task_statuses"].values():
        total += 1
        s = ts.get("status")
        if s in ("completed", "skipped"):
            done += 1
        elif s == "running":
            running += 1
        elif s in ("pending", "ready", "scheduled"):
            pending += 1
        elif s in ("failed", "dlq"):
            failed += 1
    return done, total, running, pending, failed


def _wf_last_ts(w: dict) -> str | None:
    """Most recent activity timestamp across the workflow's tasks."""
    stamps = [ts.get("last_event_at") for ts in w["task_statuses"].values() if ts.get("last_event_at")]
    return max(stamps) if stamps else None


def render_picker(stdscr: Any, workflows: dict[str, dict], ui: UIState,
                  rows: int, cols: int) -> list[str]:
    """Full-screen workflow selector. Returns the displayed workflow ids in
    order so the caller can map ui.wf_sel → id on Enter."""
    stdscr.erase()
    open_wfs = _open_workflows(workflows, show_all=ui.picker_show_all)
    ids = [wf_id for wf_id, _ in open_wfs]
    if ids:
        ui.wf_sel = max(0, min(ui.wf_sel, len(ids) - 1))
    else:
        ui.wf_sel = 0

    title = f"SIEGARD MONITOR — select a workflow"
    suffix = f"{len(ids)} open · a: all" if not ui.picker_show_all else f"{len(ids)} total"
    _addstr(stdscr, 0, 0, title, curses.color_pair(C_HEADER) | curses.A_BOLD)
    _addstr(stdscr, 0, max(0, cols - len(suffix) - 1), suffix,
            curses.color_pair(C_DIM) | curses.A_DIM)
    _hline(stdscr, 1, 0, "─", cols - 1)

    if not ids:
        _addstr(stdscr, 3, 2, "(no open workflows — press 'a' to include done/orphan, or 'q' to quit)",
                curses.color_pair(C_DIM) | curses.A_DIM)
    else:
        row = 3
        for i, (wf_id, w) in enumerate(open_wfs):
            if row >= rows - 2:
                break
            selected = (i == ui.wf_sel)
            cursor = "▶" if selected else " "
            status = w.get("status", "unknown")
            badge = "● DONE" if status == "done" else ("● LIVE" if status == "active" else "● ?")
            phase = w.get("current_phase") or "—"
            done, total, running, pending, failed = _wf_counts(w)
            bd = []
            if running:
                bd.append(f"▶{running}")
            if pending:
                bd.append(f"·{pending}")
            if failed:
                bd.append(f"✗{failed}")
            last = _short_ts(_wf_last_ts(w))
            line = (f"{cursor} {_trunc(wf_id, 24):<24}  {_trunc('[' + phase + ']', 12):<12}  "
                    f"{badge:<7} {done}/{total:<3} {' '.join(bd):<12} last {last}")
            attr = curses.color_pair(C_RUNNING) | curses.A_BOLD if selected else curses.color_pair(C_DIM)
            _addstr(stdscr, row, 1, _trunc(line, cols - 2), attr)
            row += 1

    _hline(stdscr, rows - 1, 0, "─", cols - 1)
    _addstr(stdscr, rows - 1, 0, " ↑/↓ move   Enter: follow   a: show done/orphan   q: quit ",
            curses.color_pair(C_DIM) | curses.A_DIM)
    stdscr.refresh()
    return ids


def render_curses(stdscr: Any, state: OrchState | None, error: LoadError | None, log_path: Path,
                  workflows: dict[str, dict] | None = None,
                  project_dir: Path | None = None,
                  ui: UIState | None = None,
                  multi: bool = False) -> None:
    rows, cols = stdscr.getmaxyx()
    stdscr.erase()

    if rows < MIN_ROWS or cols < MIN_COLS:
        _addstr(stdscr, 0, 0, f"Terminal too small (min {MIN_COLS}×{MIN_ROWS}, current {cols}×{rows})",
                curses.color_pair(C_ALERT) | curses.A_BOLD)
        stdscr.refresh()
        return

    row = 0

    # Workflow selector — full-screen, single-workflow mode only.
    if ui is not None and ui.picker and not multi:
        render_picker(stdscr, workflows or {}, ui, rows, cols)
        return

    # Resolve the focused workflow. multi → most-recent active (legacy aggregate
    # header/PHASES); single → explicit selection with fallback.
    if multi:
        _active = _find_active_workflow(workflows or {})
        active_wf_id, active_wf = _active if _active else (None, None)
    else:
        active_wf_id, active_wf = _focused_workflow(workflows or {}, ui)
    active_phases = _wf_phases(active_wf) if active_wf else {}
    active_tasks  = _wf_tasks(active_wf)  if active_wf else {}

    # Build the TASKS row model once. The task entries — in order — back both
    # selection/scroll and the detail panel.
    tasks_src = active_tasks if active_tasks else (state.tasks if state else {})
    if active_phases:
        phase_order = [n for n, _ in sorted(active_phases.items(), key=lambda kv: kv[1].order)]
    elif state:
        phase_order = [n for n, _ in sorted(state.phases.items(), key=lambda kv: kv[1].order)]
    else:
        phase_order = []
    status_map: dict[str, TaskStatus] = {}
    for tid, t in tasks_src.items():
        try:
            status_map[tid] = t.status if isinstance(t.status, TaskStatus) else TaskStatus(t.status)
        except ValueError:
            status_map[tid] = TaskStatus.PENDING
    # multi → all workflows nested (workflow → phase → task); single → just the
    # focused workflow's phases and tasks.
    rows_model = (_build_rows_multi(workflows) if (multi and workflows)
                  else _build_rows(tasks_src, phase_order, status_map))
    flat_tasks = [e["task"] for e in rows_model if e["kind"] == "task"]
    if ui is not None and flat_tasks:
        ui.sel = max(0, min(ui.sel, len(flat_tasks) - 1))

    # Full-screen panels (mutually exclusive with the main view).
    if ui is not None and ui.events:
        render_events(stdscr, project_dir, rows, cols)
        return
    if ui is not None and ui.dispatch:
        render_dispatch(stdscr, project_dir, rows, cols)
        return
    if ui is not None and ui.detail and flat_tasks:
        render_detail(stdscr, flat_tasks[ui.sel], rows, cols, project_dir)
        return

    # ---- Header ----
    if error and error.kind == "waiting":
        badge = "● WAIT"
        header = f"SIEGARD MONITOR  [—]  seq=?  {badge}"
    elif error:
        # Real failure. Show the offending event's seq (not "?") and attribute
        # blame in the badge: a log fault is upstream, not a monitor bug.
        seq_str = str(error.seq) if error.seq is not None else "?"
        badge = "● LOG ERROR" if error.source == "log" else "● MONITOR ERROR"
        phase_label = error.phase or (active_wf["current_phase"] if active_wf else None) or "—"
        wf_id = error.workflow_id or active_wf_id
        if wf_id:
            wf_label = _trunc(wf_id, max(10, cols - 50))
            header = f"SIEGARD MONITOR  {wf_label}  [{phase_label}]  seq={seq_str}  {badge}"
        else:
            header = f"SIEGARD MONITOR  [{phase_label}]  seq={seq_str}  {badge}"
    elif state is None:
        badge = "● WAIT"
        header = f"SIEGARD MONITOR  [—]  seq=?  {badge}"
    elif active_wf:
        phase_label = active_wf["current_phase"] or "—"
        badge = "● DONE" if active_wf["status"] == "done" else "● LIVE"
        wf_label = _trunc(active_wf_id or "—", max(10, cols - 50))
        header = f"SIEGARD MONITOR  {wf_label}  [{phase_label}]  seq={active_wf['last_seq']}  {badge}"
        # Hint that other workflows exist and can be switched to (single mode).
        n_open = len(_open_workflows(workflows or {}))
        if not multi and n_open > 1:
            header = f"{header}   ({n_open} wf · w: switch)"
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

    if error and error.kind == "waiting":
        _addstr(stdscr, row, 2, "waiting for log…", curses.color_pair(C_PENDING))
        _addstr(stdscr, row + 1, 2, str(log_path), curses.color_pair(C_DIM) | curses.A_DIM)
        stdscr.refresh()
        return

    if error:
        # Degrade gracefully: surface the violation(s) as a warning, attribute
        # the fault, then keep rendering whatever the tolerant index holds.
        n_viol = len(error.violations)
        headline = str(error)
        if n_viol > 1:
            headline = f"{headline}   (+{n_viol - 1} more violation(s))"
        _addstr(stdscr, row, 2, _trunc(headline, cols - 4),
                curses.color_pair(C_ALERT) | curses.A_BOLD)
        row += 1
        locus = "  ".join(s for s in (
            error.event_type or "",
            f"task={error.task_id}" if error.task_id else "",
            f"wf={error.workflow_id}" if error.workflow_id else "",
            f"phase={error.phase}" if error.phase else "",
        ) if s)
        if locus:
            _addstr(stdscr, row, 4, _trunc(locus, cols - 6), curses.color_pair(C_ALERT))
            row += 1
        # Attribution: who is to blame, by failure class.
        if error.kind == "corrupted_log":
            attribution = "log integrity broken (hash chain / JSON) — not a monitor bug"
        elif error.source == "log":
            attribution = "log inconsistency (out-of-order/missing event) — upstream emitter defect, not a monitor bug"
        else:
            attribution = "internal monitor error"
        _addstr(stdscr, row, 4, _trunc(attribution, cols - 6),
                curses.color_pair(C_DIM) | curses.A_DIM)
        row += 1
        # List ALL violations (not just the first), capped to the space available.
        if n_viol > 1 and row < rows - 4:
            _addstr(stdscr, row, 2, f"all violations ({n_viol}):",
                    curses.color_pair(C_ALERT) | curses.A_BOLD)
            row += 1
            max_list = max(0, (rows - 4) - row)
            for v in error.violations[:max_list]:
                seq_s = v.seq if v.seq is not None else "?"
                bits = "  ".join(s for s in (
                    v.event_type or "",
                    f"task={v.task_id}" if v.task_id else "",
                    f"phase={v.phase}" if v.phase else "",
                ) if s)
                _addstr(stdscr, row, 4, _trunc(f"seq={seq_s}  {bits}", cols - 6),
                        curses.color_pair(C_FAILED))
                row += 1
            if n_viol > max_list:
                _addstr(stdscr, row, 4, f"… {n_viol - max_list} more (see 'e' events feed)",
                        curses.color_pair(C_DIM) | curses.A_DIM)
                row += 1
        if not workflows:
            stdscr.refresh()
            return
        _addstr(stdscr, row, 2,
                "partial state below (tolerant index; violations ignored):",
                curses.color_pair(C_DIM) | curses.A_DIM)
        row += 1
        _hline(stdscr, row, 0, "─", cols - 1)
        row += 1
        # fall through: phases/agents/tasks below are driven by the workflow index

    if state is None and not error:
        _addstr(stdscr, row, 2, "waiting for log…", curses.color_pair(C_PENDING))
        _addstr(stdscr, row + 1, 2, str(log_path), curses.color_pair(C_DIM) | curses.A_DIM)
        stdscr.refresh()
        return

    # ---- Alerts ----
    if state and state.circuit_breaker:
        cb = state.circuit_breaker
        _addstr(stdscr, row, 0, f"  ⚡ CIRCUIT BREAKER TRIPPED  failures={cb.get('failure_count', '?')}",
                curses.color_pair(C_ALERT) | curses.A_BOLD)
        row += 1

    if state and state.escalation:
        esc = state.escalation
        code = esc.get("code", "?")
        reason = _trunc(esc.get("reason", ""), cols - 20)
        _addstr(stdscr, row, 0, f"  ⚠  ESCALATION {code}: {reason}",
                curses.color_pair(C_ALERT) | curses.A_BOLD)
        row += 1

    # Spec C — stalled-but-alive orchestrator (open tasks, no worker running,
    # no heartbeat within the threshold). Recomputed every frame so the alert
    # appears/disappears on the time-based redraw, not only on log changes.
    stall = _orchestrator_stall(active_wf)
    if stall:
        if stall["last_heartbeat"]:
            hb_lbl = f"last heartbeat {_fmt_dur(stall['age'])} ago"
        else:
            hb_lbl = f"no heartbeat for {_fmt_dur(stall['age'])} (since phase entry)"
        msg = (f"  ⚠  ORCHESTRATOR STALLED [{stall['phase']}]: {hb_lbl}"
               f" · {stall['open_tasks']} open task(s) — re-invoke /u-orchestrator")
        _addstr(stdscr, row, 0, _trunc(msg, cols - 1),
                curses.color_pair(C_ALERT) | curses.A_BOLD)
        row += 1

    # ---- Phases ----
    _addstr(stdscr, row, 0, "PHASES", curses.A_BOLD)
    row += 1

    phases_src = active_phases or (state.phases if state else {})
    pcounts = _phase_counts(tasks_src)
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
                qualifier = f"since {_short_ts(p.entered_at)}"
            elif ps in (PhaseStatus.COMPLETED, PhaseStatus.EXIT_APPROVED):
                qualifier = f"done {_short_ts(p.completed_at or p.approved_at)}"
            elif ps == PhaseStatus.PAUSED:
                qualifier = "paused"
            else:
                qualifier = ""

            # C2 — progress bar + per-status breakdown from the task counts.
            c = pcounts.get(name, {})
            total = sum(c.values())
            done = c.get(TaskStatus.COMPLETED, 0) + c.get(TaskStatus.SKIPPED, 0)
            running = c.get(TaskStatus.RUNNING, 0)
            pending = c.get(TaskStatus.PENDING, 0) + c.get(TaskStatus.READY, 0)
            failed = c.get(TaskStatus.FAILED, 0) + c.get(TaskStatus.DLQ, 0)

            _addstr(stdscr, row, 2, f"{icon} {name:<7}", curses.color_pair(color) | curses.A_BOLD)
            x = 2 + 2 + 7 + 1
            if total:
                bar = _progress_bar(done, total, 12)
                _addstr(stdscr, row, x, bar, curses.color_pair(C_DONE if done == total else color))
                x += len(bar) + 1
                _addstr(stdscr, row, x, f"{done}/{total}", curses.color_pair(C_DIM))
                x += len(f"{done}/{total}") + 2
                bd = []
                if running:
                    bd.append(f"▶{running}")
                if pending:
                    bd.append(f"·{pending}")
                if failed:
                    bd.append(f"✗{failed}")
                bd.append(f"✓{done}")
                _addstr(stdscr, row, x, " ".join(bd), curses.color_pair(C_DIM) | curses.A_DIM)
                x += len(" ".join(bd)) + 2
            crit = f"[{len(p.criteria_met)} crit]" if p.criteria_met else ""
            tail = "  ".join(s for s in (qualifier, crit) if s)
            if tail:
                _addstr(stdscr, row, x, _trunc(tail, max(1, cols - x - 1)),
                        curses.color_pair(C_DIM) | curses.A_DIM)
            row += 1
    else:
        _addstr(stdscr, row, 2, "(no phases declared)", curses.color_pair(C_DIM) | curses.A_DIM)
        row += 1

    row += 1  # spacer
    if row >= rows - 2:
        stdscr.refresh()
        return

    # ---- Agents ----
    # multi → aggregate across all workflows; single → just the focused one.
    agent_wfs = list(workflows.values()) if multi else ([active_wf] if active_wf else [])
    if agent_wfs:
        all_running: list[dict] = []
        done_count = 0
        failed_count = 0
        dlq_count = 0
        skipped_count = 0
        tier_map: dict[str, str | None] = {}
        for w in agent_wfs:
            all_running.extend(_filter_orchestrators(w["agents_running"], False))
            done_count += len(_filter_orchestrators(w["agents_executed"], False))
            failed_count += len(_filter_orchestrators(w["agents_failed"], False))
            dlq_count += len(_filter_orchestrators(w["agents_dlq"], False))
            skipped_count += len(_filter_orchestrators(w["agents_skipped"], False))
            for tid, ts in w["task_statuses"].items():
                tier_map[tid] = ts.get("tier")

        # D3 — count running agents past their tier's stale threshold.
        stale_count = sum(
            1 for a in all_running
            if _stale_level(_elapsed_s(a.get("claimed_at")), tier_map.get(a.get("task_id"))) > 0
        )

        _addstr(stdscr, row, 0, "AGENTS", curses.A_BOLD)
        parts = [f"{len(all_running)} running", f"{done_count} done"]
        if failed_count:
            parts.append(f"{failed_count} failed")
        if dlq_count:
            parts.append(f"{dlq_count} dlq")
        if skipped_count:
            parts.append(f"{skipped_count} skipped")
        if stale_count:
            parts.append(f"⚠ {stale_count} stale")
        summary = "  " + " · ".join(parts)
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
            # Cap the running list so it never starves the TASKS section below.
            agents_cap = 8
            shown_agents = all_running[:agents_cap]

            # Responsive columns scaled to terminal width.
            w = _alloc_widths(cols - 4, [
                ("wt",  18, 2),   # worker_type
                ("tid", 14, 2),   # task_id
                ("dur",  8, 0),   # elapsed since claim (+ stale mark)
                ("cp",  10, 4),   # last checkpoint / progress
            ])
            x_wt = 2
            x_tid = x_wt + w["wt"] + 1
            x_dur = x_tid + w["tid"] + 1
            x_cp = x_dur + w["dur"] + 1

            for a in shown_agents:
                if row >= rows - 2:
                    break
                wt      = _trunc(a.get("worker_type") or "—", w["wt"] - 2)
                tid     = _trunc(a.get("task_id") or "—", w["tid"])
                attempt = a.get("attempt", 1)
                cp      = a.get("last_progress")
                att_str = f"×{attempt} " if attempt > 1 else ""

                # D2/D3 — elapsed + stale.
                el = _elapsed_s(a.get("claimed_at"))
                lvl = _stale_level(el, tier_map.get(a.get("task_id")))
                dur_color = C_ALERT if lvl == 2 else (C_PENDING if lvl == 1 else C_DIM)
                dur_str = (_fmt_dur(el) + (" ⚠" if lvl else ""))

                _addstr(stdscr, row, x_wt,  f"▶ {wt}", curses.color_pair(C_RUNNING))
                _addstr(stdscr, row, x_tid, tid,       curses.color_pair(C_DIM))
                _addstr(stdscr, row, x_dur, _trunc(dur_str, w["dur"]), curses.color_pair(dur_color))
                cp_col = x_cp
                if att_str:
                    _addstr(stdscr, row, cp_col, att_str, curses.color_pair(C_PENDING) | curses.A_DIM)
                    cp_col += len(att_str)
                if cp:
                    cp_str = f"→ {_trunc(cp, max(1, cols - cp_col - len(att_str) - 2))}"
                    _addstr(stdscr, row, cp_col, cp_str, curses.color_pair(C_RUNNING) | curses.A_DIM)
                row += 1

            if len(all_running) > agents_cap and row < rows - 2:
                _addstr(stdscr, row, 2, f"  … +{len(all_running) - agents_cap} more running",
                        curses.color_pair(C_DIM) | curses.A_DIM)
                row += 1

        row += 1  # spacer
        if row >= rows - 2:
            stdscr.refresh()
            return

    # ---- Tasks (grouped by phase) ----
    ntasks = len(flat_tasks)
    _addstr(stdscr, row, 0, "TASKS", curses.A_BOLD)
    _addstr(stdscr, row, 6, f"  ({ntasks})", curses.color_pair(C_DIM) | curses.A_DIM)
    row += 1
    tasks_top = row

    # Responsive columns scaled to the real terminal width (no fixed offsets).
    w = _alloc_widths(cols - 4, [
        ("id",     16, 3),   # task_id (icon rendered in the 2-col left gutter)
        ("status", 11, 0),   # [running] / [scheduled] / …
        ("meta",    8, 1),   # type·tier
        ("worker", 12, 2),   # worker_id / worker_type
        ("ts",      5, 0),   # HH:MM
        ("detail", 10, 4),   # progress / reason / retry / deps — elastic
    ])
    x_id     = 2
    x_status = x_id + 2 + w["id"] + 1
    x_meta   = x_status + w["status"] + 1
    x_worker = x_meta + w["meta"] + 1
    x_ts     = x_worker + w["worker"] + 1
    x_detail = x_ts + w["ts"] + 1

    # Display model includes phase headers; selection maps to task entries only.
    disp = rows_model
    total_disp = len(disp)
    task_disp_idx = [i for i, e in enumerate(disp) if e["kind"] == "task"]
    sel_disp = task_disp_idx[ui.sel] if (ui and task_disp_idx and ui.sel < len(task_disp_idx)) else -1

    body_avail = max(1, rows - 1 - tasks_top)
    if ui:
        # Scroll-follow on the selected task's display row (reserve 1 indicator line).
        view = max(1, body_avail - 1)
        if sel_disp >= 0:
            if sel_disp < ui.scroll:
                ui.scroll = sel_disp
            elif sel_disp >= ui.scroll + view:
                ui.scroll = sel_disp - view + 1
        ui.scroll = max(0, min(ui.scroll, max(0, total_disp - 1)))
    start = ui.scroll if ui else 0
    top_ind = 1 if start > 0 else 0
    win = max(1, body_avail - top_ind)
    end = min(total_disp, start + win)
    bot_ind = 1 if end < total_disp else 0
    if bot_ind:
        win = max(1, win - 1)
        end = min(total_disp, start + win)

    if top_ind and row < rows - 1:
        _addstr(stdscr, row, 2, f"▲ +{start} more", curses.color_pair(C_DIM) | curses.A_DIM)
        row += 1

    for i in range(start, end):
        if row >= rows - 1:
            break
        e = disp[i]

        if e["kind"] == "workflow":
            badge = ("● DONE" if e["status"] == "done"
                     else "● LIVE" if e["status"] == "active" else "● ?")
            wf_label = e["workflow_id"] if e["workflow_id"] != UNKNOWN_WORKFLOW else "(orphan events)"
            phase = e["current_phase"] or "—"
            label = f"▼ {wf_label}  [{phase}]  {e['done']}/{e['total']}  {badge}"
            _addstr(stdscr, row, 0, _trunc(label, cols - 1), curses.color_pair(C_HEADER) | curses.A_BOLD)
            row += 1
            continue

        if e["kind"] == "header":
            label = f"── {e['phase']} ──  {e['done']}/{e['total']}"
            _addstr(stdscr, row, 1, _trunc(label, cols - 2), curses.color_pair(C_HEADER) | curses.A_BOLD)
            row += 1
            continue

        t = e["task"]
        status = e["status"]
        sel = curses.A_REVERSE if i == sel_disp else 0
        icon = STATUS_ICON.get(status, "?")
        base = STATUS_COLOR.get(status, C_DIM)
        detail = ""
        detail_color = base

        if status == TaskStatus.RUNNING:
            el = _elapsed_s(t.claimed_at)
            lvl = _stale_level(el, getattr(t, "tier", None))
            prog = getattr(t, "last_progress", None)
            detail = _fmt_dur(el) + (f"  → {prog}" if prog else "")
            if lvl:
                detail = "⚠ " + detail
                detail_color = C_ALERT if lvl == 2 else C_PENDING
        elif status == TaskStatus.SCHEDULED and t.next_retry_at:
            detail = f"retry@{_short_ts(t.next_retry_at)}"
        elif status in (TaskStatus.FAILED, TaskStatus.DLQ) and t.last_failure_reason:
            detail = t.last_failure_reason
            err = getattr(t, "last_error", None)
            if err:
                detail = f"{detail} — {err}"
        elif status in (TaskStatus.PENDING, TaskStatus.READY):
            dstate, unmet = e["dep"]
            if dstate == "blocked":
                icon = "⛓"
                detail = "waiting: " + ", ".join(unmet)
                detail_color = C_PENDING
            else:
                detail = "ready"
        if t.attempts > 1 and status != TaskStatus.RUNNING:
            detail = f"×{t.attempts}/{t.max_attempts}  {detail}".rstrip()

        color = curses.color_pair(base) | sel
        dim = curses.color_pair(C_DIM) | sel
        meta = "·".join(p for p in (getattr(t, "task_type", None), getattr(t, "tier", None)) if p)
        worker = getattr(t, "worker_id", None) or getattr(t, "worker_type", None) or "—"
        ts = _short_ts(t.claimed_at if status == TaskStatus.RUNNING else t.last_event_at)

        _addstr(stdscr, row, x_id,     f"{icon} {_trunc(t.task_id, w['id'])}", color)
        _addstr(stdscr, row, x_status, _trunc(f"[{status.value}]", w["status"]), color)
        _addstr(stdscr, row, x_meta,   _trunc(meta or "—", w["meta"]), dim)
        _addstr(stdscr, row, x_worker, _trunc(worker, w["worker"]), dim)
        _addstr(stdscr, row, x_ts,     _trunc(ts, w["ts"]), dim)
        if detail:
            _addstr(stdscr, row, x_detail, _trunc(detail, max(1, cols - x_detail - 1)),
                    curses.color_pair(detail_color) | sel | curses.A_DIM)
        row += 1

    if bot_ind and row < rows - 1:
        _addstr(stdscr, row, 2, f"▼ +{total_disp - end} more", curses.color_pair(C_DIM) | curses.A_DIM)
        row += 1

    # ---- Footer ----
    _hline(stdscr, rows - 1, 0, "─", cols - 1)
    now = datetime.now().strftime("%H:%M:%S")
    pos = f"{ui.sel + 1}/{ntasks}" if (ui and ntasks) else f"{ntasks}"
    footer = f" ↑↓ select · Enter detail · e events · d dispatch · q quit    {pos}    {now} "
    _addstr(stdscr, rows - 1, 0, _trunc(footer, cols - 1), curses.color_pair(C_DIM) | curses.A_DIM)

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
                   help="Focus a single workflow_id (live: skip the selector; --once: filter)")
    p.add_argument("--multi", action="store_true",
                   help="Live: show all workflows aggregated (legacy view; default focuses one)")
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


def run_live(stdscr: Any, project_dir: Path, interval: float,
             multi: bool = False, initial_wf: str | None = None) -> None:
    log_path = project_dir / ".orch" / "log.jsonl"

    curses.cbreak()
    stdscr.keypad(True)
    stdscr.nodelay(True)
    _init_colors()

    last_stat: tuple[float, int] = (-1.0, -1)
    state: OrchState | None = None
    error: LoadError | None = None
    workflows: dict[str, dict] = {}
    ui = UIState()
    ui.selected_wf = initial_wf       # --workflow seed (single mode); skips the picker
    focus_initialized = False

    tick_ms = 100  # key responsiveness
    ticks_per_poll = max(1, int(interval * 1000 / tick_ms))
    redraw_ticks = max(1, int(1000 / tick_ms))  # time-based redraw (~1s) for live durations
    tick_count = ticks_per_poll  # force immediate load on first frame
    redraw_count = 0
    dirty = True                 # render needed (data or UI changed)

    while True:
        # --- Key handling ---
        try:
            key = stdscr.getch()
        except curses.error:
            key = -1

        if ui.picker and not multi:
            # --- Picker key handling (single-workflow selector) ---
            if key in (ord("q"), ord("Q")):
                return
            elif key == 27:  # ESC: back to focus if one is chosen, else quit
                if ui.selected_wf and ui.selected_wf in workflows:
                    ui.picker = False
                    dirty = True
                else:
                    return
            elif key in (curses.KEY_DOWN, ord("j")):
                ui.wf_sel += 1
                dirty = True
            elif key in (curses.KEY_UP, ord("k")):
                ui.wf_sel = max(0, ui.wf_sel - 1)
                dirty = True
            elif key in (ord("a"), ord("A")):  # toggle done/orphan in the list
                ui.picker_show_all = not ui.picker_show_all
                dirty = True
            elif key in (10, 13, curses.KEY_ENTER):  # select the highlighted workflow
                open_ids = [wid for wid, _ in _open_workflows(workflows, show_all=ui.picker_show_all)]
                if open_ids:
                    ui.wf_sel = max(0, min(ui.wf_sel, len(open_ids) - 1))
                    ui.selected_wf = open_ids[ui.wf_sel]
                    ui.picker = False
                    ui.sel = 0
                    dirty = True
            elif key == curses.KEY_RESIZE:
                dirty = True
        elif key in (ord("q"), ord("Q")):
            return
        elif key == 27:  # ESC: close an open panel, else quit
            if ui.detail or ui.events or ui.dispatch:
                ui.detail = False
                ui.events = False
                ui.dispatch = False
                dirty = True
            else:
                return
        elif key in (ord("w"), ord("W")) and not multi:  # open the workflow selector
            ui.picker = True
            ui.detail = False
            ui.events = False
            ui.dispatch = False
            dirty = True
        elif key in (ord("e"), ord("E")):  # toggle recent-events feed
            ui.events = not ui.events
            ui.detail = False
            ui.dispatch = False
            dirty = True
        elif key in (ord("d"), ord("D")):  # toggle dispatch-decisions panel
            ui.dispatch = not ui.dispatch
            ui.detail = False
            ui.events = False
            dirty = True
        elif key in (curses.KEY_DOWN, ord("j")):
            ui.sel += 1
            dirty = True
        elif key in (curses.KEY_UP, ord("k")):
            ui.sel = max(0, ui.sel - 1)
            dirty = True
        elif key == curses.KEY_NPAGE:  # PgDn
            ui.sel += 10
            dirty = True
        elif key == curses.KEY_PPAGE:  # PgUp
            ui.sel = max(0, ui.sel - 10)
            dirty = True
        elif key in (curses.KEY_HOME, ord("g")):
            ui.sel = 0
            dirty = True
        elif key in (curses.KEY_END, ord("G")):
            ui.sel = 1 << 30  # clamped to last by the renderer
            dirty = True
        elif key in (10, 13, curses.KEY_ENTER):  # Enter: toggle detail
            ui.detail = not ui.detail
            ui.events = False
            dirty = True
        elif key == curses.KEY_RESIZE:
            dirty = True

        # --- Polling: reload state when the log changes ---
        tick_count += 1
        if tick_count >= ticks_per_poll:
            tick_count = 0
            current_stat = _stat_key(log_path)
            if current_stat != last_stat:
                last_stat = current_stat
                state, error = _load_state(project_dir)
                workflows, _ = _collect_workflow_index(project_dir)
                if not multi:
                    if not focus_initialized:
                        _init_focus(workflows, ui)
                        focus_initialized = True
                    else:
                        _reresolve_focus(workflows, ui)
                dirty = True

        # --- Time-based redraw: keep elapsed/stale and the clock advancing ---
        redraw_count += 1
        if redraw_count >= redraw_ticks:
            redraw_count = 0
            dirty = True

        if dirty:
            render_curses(stdscr, state, error, log_path, workflows, project_dir, ui, multi)
            dirty = False

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

    if curses is None:
        print("monitor: live mode requires the 'curses' module, which is unavailable on "
              "this platform (e.g. Windows). Use --once for the plain renderer.",
              file=sys.stderr)
        return 1

    try:
        curses.wrapper(run_live, project_dir, args.interval, args.multi, args.workflow)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        # curses already restored terminal at this point
        print(f"monitor error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
