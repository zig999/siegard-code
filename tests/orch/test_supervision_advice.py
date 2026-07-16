"""Tests for supervision_advice.py — the pure-log recommender that offers a one-time
detach decision (hand remaining phases to /u-supervise) at the FIRST phase transition.

Covers the pure `advise()` decision table and the `compute()` wiring (reduce_all +
phase_transitioned count) over a seeded log.
"""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "dist" / ".claude" / "scripts"

_spec = importlib.util.spec_from_file_location("supervision_advice", SCRIPTS / "supervision_advice.py")
advice = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(advice)


# --------------------------------------------------------------------------- pure core

def test_first_transition_active_is_recommended():
    d = advice.advise("active", 1, "wf-x")
    assert d["recommended"] is True
    assert d["reason"] == "first_transition_pending_phases"
    assert d["message"]  # non-empty human-facing prompt
    assert d["commands"]["attended"] == "/loop 5m /u-supervise wf-x"
    assert d["commands"]["unattended"] == "/schedule /u-supervise wf-x"


def test_second_transition_is_not_nagged():
    d = advice.advise("active", 2, "wf-x")
    assert d["recommended"] is False
    assert d["reason"] == "not_first_transition"
    assert d["message"] == ""


def test_no_transition_yet_not_recommended():
    d = advice.advise("active", 0, "wf-x")
    assert d["recommended"] is False
    assert d["reason"] == "no_transition_yet"


def test_completed_run_not_recommended():
    d = advice.advise("completed", 1, "wf-x")
    assert d["recommended"] is False
    assert d["reason"] == "workflow_completed"


def test_escalated_run_not_recommended():
    d = advice.advise("escalated", 1, "wf-x")
    assert d["recommended"] is False
    assert d["reason"] == "awaiting_human_response"


def test_blocked_run_not_recommended():
    d = advice.advise("blocked", 1, "wf-x")
    assert d["recommended"] is False
    assert d["reason"] == "needs_human_diagnosis"


def test_unknown_run_status_not_recommended():
    d = advice.advise("paused", 1, "wf-x")
    assert d["recommended"] is False
    assert d["reason"] == "run_status_paused"


def test_custom_loop_interval_and_placeholder_workflow():
    d = advice.advise("active", 1, None, loop_interval="10m")
    assert d["commands"]["attended"] == "/loop 10m /u-supervise <workflow_id>"
    assert d["commands"]["unattended"] == "/schedule /u-supervise <workflow_id>"


# --------------------------------------------------------------------------- integration

_WF = "wf-adv"


def _seed_declared(orch_core, phases):
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": _WF, "phases": phases})


def _enter(orch_core, phase, order):
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": phase, "order": order, "workflow_id": _WF})


def _transition(orch_core, from_phase, to_phase):
    """Seed a gate-valid forward transition (satisfies _precond_phase_transitioned)."""
    orch_core.append_event(
        agent=f"orchestrator-{from_phase}", event_type="phase_exit_criterion_met",
        data={"phase": from_phase, "criterion": "check_x"})
    orch_core.append_event(
        agent=f"orchestrator-{from_phase}", event_type="phase_exit_approved",
        data={"phase": from_phase, "criteria_met": ["check_x"],
              "next_phase": to_phase, "workflow_id": _WF})
    evidence_seq = orch_core.reduce_all().last_seq
    orch_core.append_event(
        agent=f"orchestrator-{from_phase}", event_type="phase_transitioned",
        data={"from_phase": from_phase, "to_phase": to_phase,
              "evidence_seq": evidence_seq, "workflow_id": _WF})


def test_compute_recommends_after_first_transition(tmp_orch):
    import orch_core
    _seed_declared(orch_core, [
        {"name": "sdd", "order": 1, "required": True},
        {"name": "dev", "order": 2, "required": True},
        {"name": "review", "order": 3, "required": True},
    ])
    _enter(orch_core, "sdd", 1)
    _transition(orch_core, "sdd", "dev")
    _enter(orch_core, "dev", 2)

    d = advice.compute(workflow_id=_WF)
    assert d["recommended"] is True
    assert d["reason"] == "first_transition_pending_phases"
    assert d["commands"]["attended"] == f"/loop 5m /u-supervise {_WF}"


def test_compute_silent_after_second_transition(tmp_orch):
    import orch_core
    _seed_declared(orch_core, [
        {"name": "sdd", "order": 1, "required": True},
        {"name": "dev", "order": 2, "required": True},
        {"name": "review", "order": 3, "required": True},
    ])
    _enter(orch_core, "sdd", 1)
    _transition(orch_core, "sdd", "dev")
    _enter(orch_core, "dev", 2)
    _transition(orch_core, "dev", "review")
    _enter(orch_core, "review", 3)

    d = advice.compute(workflow_id=_WF)
    assert d["recommended"] is False
    assert d["reason"] == "not_first_transition"


# ------------------------------------------------- multi-workflow scoping (M4)

def _transition_events(orch_core, wf, n):
    for i in range(n):
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="phase_declared",
            data={"workflow_id": wf, "phases": [
                {"name": "sdd", "order": 1, "required": True},
                {"name": "dev", "order": 2, "required": True}]})
        orch_core.append_event(
            agent="orchestrator", event_type="phase_entered",
            data={"phase": "sdd", "order": 1, "workflow_id": wf})
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="phase_exit_approved",
            data={"phase": "sdd", "criteria_met": ["c"], "next_phase": "dev",
                  "workflow_id": wf})
        seq = orch_core.reduce_all().last_seq
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="phase_transitioned",
            data={"from_phase": "sdd", "to_phase": "dev", "evidence_seq": seq,
                  "workflow_id": wf})


def test_prior_workflow_transitions_do_not_suppress_onramp(tmp_orch):
    """M4 (2026-07-15 post-fix audit): with workflow A's transition already in
    the shared log, workflow B's FIRST transition must still be advised as the
    first — a global count reads 2 and the on-ramp never fires again."""
    import orch_core
    _transition_events(orch_core, "wf-old", 1)
    _transition_events(orch_core, "wf-new", 1)

    out = advice.compute(workflow_id="wf-new")
    assert out["recommended"] is True
    assert out["reason"] == "first_transition_pending_phases"


def test_second_transition_of_same_workflow_still_antinag(tmp_orch):
    import orch_core
    _transition_events(orch_core, "wf-new", 2)
    out = advice.compute(workflow_id="wf-new")
    assert out["recommended"] is False
    assert out["reason"] == "not_first_transition"


def test_no_workflow_id_keeps_global_count(tmp_orch):
    """Back-compat: without a workflow_id the count stays global."""
    import orch_core
    _transition_events(orch_core, "wf-old", 1)
    _transition_events(orch_core, "wf-new", 1)
    out = advice.compute()
    assert out["recommended"] is False
    assert out["reason"] == "not_first_transition"
