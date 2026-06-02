"""
Monitor grouping tests — workflow → phase → task hierarchy.

Covers the pure row-model builder (_build_rows_multi) and the --once plain
renderer (render_plain_multi), which share one grouping source of truth.
"""
import os
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "dist" / ".claude" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# monitor.py sets os.environ["ORCH_PROJECT_DIR"] at import time (CLI bootstrap).
# Snapshot and restore it around the import so this side effect does not leak
# into other tests — notably subprocess-based suites that inherit the env.
_prev_orch_env = os.environ.get("ORCH_PROJECT_DIR")
import monitor  # noqa: E402
if _prev_orch_env is None:
    os.environ.pop("ORCH_PROJECT_DIR", None)
else:
    os.environ["ORCH_PROJECT_DIR"] = _prev_orch_env


# ---------------------------------------------------------------------------
# Fixtures: build workflow records in the shape _collect_workflow_index emits.
# ---------------------------------------------------------------------------

def _task(task_id, status, *, phase, worker_type=None, deps=None):
    return {
        "task_id": task_id,
        "status": status,
        "worker_id": worker_type,
        "worker_type": worker_type,
        "attempts": 1,
        "max_attempts": 3,
        "claimed_at": None,
        "created_at": "2026-06-01T10:00:00Z",
        "last_event_at": "2026-06-01T10:01:00Z",
        "last_failure_reason": None,
        "next_retry_at": None,
        "phase": phase,
        "task_type": "impl",
        "tier": "standard",
        "stack": None,
        "deps": list(deps or []),
        "spec": None,
        "artifacts": [],
        "last_progress": None,
    }


def _phase(order, status="active"):
    return {
        "status": status, "order": order,
        "entered_at": "2026-06-01T10:00:00Z", "completed_at": None,
        "approved_at": None, "criteria_met": [],
    }


def _wf(*, last_seq, status, current_phase, phases, tasks):
    rec = monitor._new_workflow_record()
    rec["last_seq"] = last_seq
    rec["status"] = status
    rec["current_phase"] = current_phase
    rec["phases"] = list(phases.keys())
    rec["phase_details"] = phases
    rec["task_statuses"] = {t["task_id"]: t for t in tasks}
    return rec


@pytest.fixture
def two_workflows():
    return {
        "wf-old": _wf(
            last_seq=10, status="done", current_phase="dev",
            phases={"dev": _phase(0, "completed")},
            tasks=[_task("T1", "completed", phase="dev")],
        ),
        "wf-new": _wf(
            last_seq=42, status="active", current_phase="sdd",
            phases={"sdd": _phase(0, "active"), "dev": _phase(1, "pending")},
            tasks=[
                _task("T1", "running", phase="sdd"),               # same id as wf-old
                _task("T2", "pending", phase="dev", deps=["T1"]),  # blocked by T1
            ],
        ),
    }


# ---------------------------------------------------------------------------
# _build_rows_multi
# ---------------------------------------------------------------------------

def test_workflow_order_is_last_seq_desc(two_workflows):
    rows = monitor._build_rows_multi(two_workflows)
    wf_ids = [r["workflow_id"] for r in rows if r["kind"] == "workflow"]
    assert wf_ids == ["wf-new", "wf-old"]  # most recent first


def test_tasks_do_not_leak_across_workflows(two_workflows):
    rows = monitor._build_rows_multi(two_workflows)
    # Partition rows by their owning workflow header.
    owner, buckets = None, {}
    for r in rows:
        if r["kind"] == "workflow":
            owner = r["workflow_id"]
            buckets[owner] = []
        elif r["kind"] == "task":
            buckets[owner].append(r["task"].task_id)
    assert buckets["wf-old"] == ["T1"]
    assert sorted(buckets["wf-new"]) == ["T1", "T2"]


def test_dep_classification_is_per_workflow(two_workflows):
    # wf-new T2 depends on wf-new T1 (running, not done) → blocked, not satisfied
    # by the completed T1 in wf-old.
    rows = monitor._build_rows_multi(two_workflows)
    t2 = next(r for r in rows if r["kind"] == "task" and r["task"].task_id == "T2")
    dstate, unmet = t2["dep"]
    assert dstate == "blocked"
    assert unmet == ["T1"]


def test_single_workflow_still_emits_header():
    wf = {"only": _wf(last_seq=1, status="active", current_phase="dev",
                      phases={"dev": _phase(0)}, tasks=[_task("T1", "running", phase="dev")])}
    rows = monitor._build_rows_multi(wf)
    assert [r["kind"] for r in rows][:1] == ["workflow"]
    assert sum(1 for r in rows if r["kind"] == "workflow") == 1


def test_workflow_with_no_tasks_emits_lone_header():
    wf = {"empty": _wf(last_seq=1, status="active", current_phase="sdd",
                       phases={"sdd": _phase(0)}, tasks=[])}
    rows = monitor._build_rows_multi(wf)
    assert len(rows) == 1 and rows[0]["kind"] == "workflow"
    assert rows[0]["total"] == 0


def test_show_orchestrators_filters_meta_agents():
    wf = {"w": _wf(last_seq=1, status="active", current_phase="dev",
                   phases={"dev": _phase(0)}, tasks=[
                       _task("T1", "running", phase="dev", worker_type="orchestrator-dev"),
                       _task("T2", "running", phase="dev", worker_type="u-dev"),
                   ])}
    hidden = monitor._build_rows_multi(wf, show_orchestrators=False)
    shown = monitor._build_rows_multi(wf, show_orchestrators=True)
    hidden_ids = [r["task"].task_id for r in hidden if r["kind"] == "task"]
    shown_ids = [r["task"].task_id for r in shown if r["kind"] == "task"]
    assert hidden_ids == ["T2"]
    assert sorted(shown_ids) == ["T1", "T2"]


# ---------------------------------------------------------------------------
# render_plain_multi (--once)
# ---------------------------------------------------------------------------

def test_plain_multi_three_level_structure(two_workflows, capsys):
    monitor.render_plain_multi(two_workflows, None)
    out = capsys.readouterr().out
    # Level 1: workflow headers (newest first).
    assert "▼ wf-new" in out and "▼ wf-old" in out
    assert out.index("▼ wf-new") < out.index("▼ wf-old")
    # Level 2: phase headers.
    assert "── sdd ──" in out and "── dev ──" in out
    # Level 3: task lines.
    assert "T1" in out and "T2" in out


def test_plain_multi_running_only_hides_done(two_workflows, capsys):
    monitor.render_plain_multi(two_workflows, None, running_only=True)
    out = capsys.readouterr().out
    assert "▼ wf-new" in out
    assert "▼ wf-old" not in out


def test_plain_multi_workflow_filter(two_workflows, capsys):
    monitor.render_plain_multi(two_workflows, None, workflow_filter="wf-old")
    out = capsys.readouterr().out
    assert "▼ wf-old" in out
    assert "▼ wf-new" not in out


# ---------------------------------------------------------------------------
# _load_state → LoadError mapping (diagnostics P0)
# ---------------------------------------------------------------------------

def test_load_state_waiting_when_no_log(tmp_path):
    err = monitor._load_state(tmp_path)[1]
    assert err is not None and err.kind == "waiting"
    assert err.source == "monitor"


def test_load_state_illegal_transition_carries_locus(tmp_path, monkeypatch):
    """An illegal transition must surface as a structured LoadError attributing
    the fault to the log (upstream emitter), with the offending event's locus."""
    # Use the class object bound inside monitor so the except clause matches
    # even if orch_core is loaded under multiple module paths across the suite.
    IllegalTransition = monitor.IllegalTransition

    (tmp_path / ".orch").mkdir()
    (tmp_path / ".orch" / "log.jsonl").write_text("", encoding="utf-8")

    def _boom():
        exc = IllegalTransition("task_claimed: task 'dev_tc_001' is "
                                "<TaskStatus.PENDING: 'pending'>, expected ready")
        exc.seq = 42
        exc.task_id = "dev_tc_001"
        exc.event_type = "task_claimed"
        exc.workflow_id = "wf-xyz"
        exc.phase = "dev"
        raise exc

    monkeypatch.setattr(monitor, "reduce_all", _boom)
    err = monitor._load_state(tmp_path)[1]
    assert err is not None
    assert err.kind == "illegal_transition"
    assert err.source == "log"
    assert err.seq == 42
    assert err.task_id == "dev_tc_001"
    assert err.event_type == "task_claimed"
    assert err.workflow_id == "wf-xyz"
    assert err.phase == "dev"
    assert "expected ready" in str(err)


def test_load_state_internal_error_attributed_to_monitor(tmp_path, monkeypatch):
    (tmp_path / ".orch").mkdir()
    (tmp_path / ".orch" / "log.jsonl").write_text("", encoding="utf-8")

    def _boom():
        raise RuntimeError("unexpected")

    monkeypatch.setattr(monitor, "reduce_all", _boom)
    err = monitor._load_state(tmp_path)[1]
    assert err is not None and err.kind == "internal"
    assert err.source == "monitor"


# ---------------------------------------------------------------------------
# Single-workflow focus model (live default)
# ---------------------------------------------------------------------------

@pytest.fixture
def three_workflows():
    return {
        "wf-active-new": _wf(last_seq=50, status="active", current_phase="dev",
                             phases={"dev": _phase(0, "active")},
                             tasks=[_task("A", "running", phase="dev")]),
        "wf-active-old": _wf(last_seq=20, status="active", current_phase="sdd",
                             phases={"sdd": _phase(0, "active")},
                             tasks=[_task("B", "pending", phase="sdd")]),
        "wf-done": _wf(last_seq=40, status="done", current_phase="dev",
                       phases={"dev": _phase(0, "completed")},
                       tasks=[_task("C", "completed", phase="dev")]),
        monitor.UNKNOWN_WORKFLOW: _wf(last_seq=5, status="unknown", current_phase=None,
                                      phases={}, tasks=[_task("D", "pending", phase="x")]),
    }


def test_open_workflows_excludes_done_and_orphan(three_workflows):
    ids = [wid for wid, _ in monitor._open_workflows(three_workflows)]
    assert ids == ["wf-active-new", "wf-active-old"]  # done + orphan dropped, last_seq desc


def test_open_workflows_show_all_includes_everything(three_workflows):
    ids = [wid for wid, _ in monitor._open_workflows(three_workflows, show_all=True)]
    assert ids == ["wf-active-new", "wf-done", "wf-active-old", monitor.UNKNOWN_WORKFLOW]


def test_focused_workflow_honors_explicit_selection(three_workflows):
    ui = monitor.UIState()
    ui.selected_wf = "wf-active-old"
    wid, _ = monitor._focused_workflow(three_workflows, ui)
    assert wid == "wf-active-old"


def test_focused_workflow_falls_back_to_most_recent_open(three_workflows):
    ui = monitor.UIState()
    ui.selected_wf = "ghost"  # not present
    wid, _ = monitor._focused_workflow(three_workflows, ui)
    assert wid == "wf-active-new"
    assert ui.selected_wf == "ghost"  # pure: no mutation


def test_focused_workflow_empty():
    assert monitor._focused_workflow({}, monitor.UIState()) == (None, None)


def test_init_focus_autoselects_single():
    ui = monitor.UIState()
    monitor._init_focus({"only": _wf(last_seq=1, status="active", current_phase="dev",
                                     phases={}, tasks=[])}, ui)
    assert ui.selected_wf == "only" and ui.picker is False


def test_init_focus_opens_picker_when_many(three_workflows):
    ui = monitor.UIState()
    monitor._init_focus(three_workflows, ui)
    assert ui.picker is True and ui.selected_wf is None


def test_init_focus_respects_seed(three_workflows):
    ui = monitor.UIState()
    ui.selected_wf = "wf-active-old"
    monitor._init_focus(three_workflows, ui)
    assert ui.selected_wf == "wf-active-old" and ui.picker is False


def test_reresolve_autofocus_when_one_left():
    ui = monitor.UIState()
    ui.selected_wf = "gone"
    monitor._reresolve_focus({"only": _wf(last_seq=1, status="active", current_phase="d",
                                          phases={}, tasks=[])}, ui)
    assert ui.selected_wf == "only" and ui.picker is False


def test_reresolve_reopens_picker_when_many(three_workflows):
    ui = monitor.UIState()
    ui.selected_wf = "gone"
    monitor._reresolve_focus(three_workflows, ui)
    assert ui.selected_wf is None and ui.picker is True


def test_reresolve_noop_when_selection_present(three_workflows):
    ui = monitor.UIState()
    ui.selected_wf = "wf-active-new"
    monitor._reresolve_focus(three_workflows, ui)
    assert ui.selected_wf == "wf-active-new" and ui.picker is False
