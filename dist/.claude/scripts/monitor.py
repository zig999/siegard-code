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
    """Parse --project-dir / ORCH_PROJECT_DIR without consuming sys.argv."""
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg in ("--project-dir", "-project-dir") and i < len(sys.argv):
            return Path(sys.argv[i + 1]).resolve()
        if arg.startswith("--project-dir="):
            return Path(arg.split("=", 1)[1]).resolve()
    env = os.environ.get("ORCH_PROJECT_DIR")
    if env:
        return Path(env).resolve()
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
        win.hline(row, col, ch, n)
    except curses.error:
        pass


def render_curses(stdscr: Any, state: OrchState | None, error: str | None, log_path: Path) -> None:
    rows, cols = stdscr.getmaxyx()
    stdscr.erase()

    if rows < MIN_ROWS or cols < MIN_COLS:
        _addstr(stdscr, 0, 0, f"Terminal too small (min {MIN_COLS}×{MIN_ROWS}, current {cols}×{rows})",
                curses.color_pair(C_ALERT) | curses.A_BOLD)
        stdscr.refresh()
        return

    row = 0

    # ---- Header ----
    if error:
        badge = "● ERROR"
        header = f"SIEGARD MONITOR  [—]  seq=?  {badge}"
    elif state is None:
        badge = "● WAIT"
        header = f"SIEGARD MONITOR  [—]  seq=?  {badge}"
    else:
        phase_label = state.current_phase or "—"
        badge = "● DONE" if state.run_status == "completed" else "● LIVE"
        header = f"SIEGARD MONITOR  [{phase_label}]  seq={state.last_seq}  {badge}"

    _addstr(stdscr, row, 0, header, curses.color_pair(C_HEADER) | curses.A_BOLD)
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

    if state.phases:
        for name, p in sorted(state.phases.items(), key=lambda kv: kv[1].order):
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

    # ---- Tasks ----
    _addstr(stdscr, row, 0, "TASKS", curses.A_BOLD)
    row += 1

    by_status: dict[TaskStatus, list] = {s: [] for s in STATUS_ORDER}
    for t in state.tasks.values():
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
    return p.parse_args()


def run_once(project_dir: Path) -> int:
    state, error = _load_state(project_dir)
    render_plain(state, error)
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
                render_curses(stdscr, state, error, log_path)

        time.sleep(tick_ms / 1000)


def main() -> int:
    args = _parse_args()
    # project_dir was already resolved early (before orch_core import).
    # Re-resolve here only if the user passed --project-dir explicitly.
    project_dir = Path(args.project_dir).resolve() if args.project_dir else _project_dir_early

    if args.once:
        return run_once(project_dir)

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
