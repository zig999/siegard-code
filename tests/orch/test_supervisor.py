"""Tests for supervised auto-resume (E2 / B(b) — supervisor_tick.py).

Covers the pure `decide()` core (detection + budget + cooldown + in-flight TTL + the
total-phase-silence false-positive guard) and the CLI side effects (append
orchestrator_resume_requested / escalation E23). Timing-sensitive cases use a controllable
clock (monkeypatched now_iso) so each event gets a deterministic ts.
"""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "dist" / ".claude" / "scripts"

_spec = importlib.util.spec_from_file_location("supervisor_tick", SCRIPTS / "supervisor_tick.py")
supervisor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(supervisor)


@pytest.fixture
def clock(monkeypatch):
    """A controllable clock: every append_event stamps ts from here; advance between
    appends to place events at known offsets. decide() is called with clock.iso()."""
    import orch_core
    state = {"t": datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)}

    def _now():
        return state["t"].strftime("%Y-%m-%dT%H:%M:%S.000Z")

    monkeypatch.setattr(orch_core, "now_iso", _now)
    return SimpleNamespace(
        iso=_now,
        advance=lambda s: state.__setitem__("t", state["t"] + timedelta(seconds=s)),
    )


def _seed_active_phase(orch_core, phase="dev", wf="wf-sup"):
    """Active phase with one non-terminal (READY) task and no heartbeat → stalled base."""
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": wf, "phases": [{"name": phase, "order": 1, "required": True}]})
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": phase, "order": 1, "workflow_id": wf})
    orch_core.append_event(
        agent="orchestrator-dev", event_type="task_created", task_id="dev_tc_001",
        data={"phase": phase, "deps": [], "tier": "standard", "type": "impl", "spec": "x"})


def _decide(orch_core, clock, policy=None, stale_config=None):
    state = orch_core.reduce_all()
    events = list(orch_core.read_events_filtered(event_type=None))
    return supervisor.decide(state, events, clock.iso(), policy or {}, stale_config=stale_config)


# --------------------------------------------------------------------------- detection

def test_stalled_phase_triggers_resume(tmp_orch, clock):
    import orch_core
    _seed_active_phase(orch_core)
    clock.advance(1000)  # no heartbeat, task silent > 900s
    d = _decide(orch_core, clock)
    assert d["resume"] is True
    assert d["escalate"] is False
    assert d["phase"] == "dev"
    assert d["workflow_id"] == "wf-sup"


def test_fresh_heartbeat_suppresses_resume(tmp_orch, clock):
    import orch_core
    _seed_active_phase(orch_core)
    orch_core.append_event(
        agent="orchestrator-dev", event_type="orchestrator_heartbeat", data={"phase": "dev"})
    d = _decide(orch_core, clock)  # now == heartbeat ts (fresh)
    assert d["resume"] is False
    assert d["reason"] == "orchestrator_live_or_no_pending"


def test_recent_task_activity_blocks_resume(tmp_orch, clock):
    """False-positive guard: orchestrator silent (no heartbeat) but a worker still emits
    task_progress → phase is alive, must NOT spawn a second meta."""
    import orch_core
    _seed_active_phase(orch_core)
    orch_core.append_event(
        agent="orchestrator-dev", event_type="task_claimed", task_id="dev_tc_001",
        data={"phase": "dev", "worker_type": "u-be-developer", "worker_id": "w1"})
    clock.advance(1000)  # orchestrator loop blocked in a long dispatch (no heartbeat)
    orch_core.append_event(
        agent="u-be-developer", event_type="task_progress", task_id="dev_tc_001",
        data={"phase": "dev", "note": "still working"})  # fresh worker activity
    d = _decide(orch_core, clock)
    assert d["resume"] is False
    assert d["reason"] == "phase_tasks_active"


def test_no_active_phase_is_noop(tmp_orch, clock):
    import orch_core
    d = _decide(orch_core, clock)
    assert d["resume"] is False
    assert d["reason"] == "no_active_phase"


# --------------------------------------------------------------------------- budget

def test_budget_exhausted_escalates(tmp_orch, clock):
    import orch_core
    _seed_active_phase(orch_core)
    clock.advance(1000)
    for _ in range(3):  # default max_auto_resumes == 3 resume attempts
        orch_core.append_event(
            agent="supervisor", event_type="orchestrator_resume_requested", data={"phase": "dev"})
    d = _decide(orch_core, clock)
    assert d["resume"] is False
    assert d["escalate"] is True
    assert d["reason"] == "resume_budget_exhausted"
    assert d["budget_remaining"] == 0


def test_resumes_scoped_per_phase(tmp_orch, clock):
    """Budget counts resumes for the CURRENT phase only — resumes attributed to another
    phase must not consume the active phase's budget."""
    import orch_core
    _seed_active_phase(orch_core)  # current phase == dev
    for _ in range(3):  # resume attempts belonging to a different phase
        orch_core.append_event(
            agent="supervisor", event_type="orchestrator_resume_requested", data={"phase": "sdd"})
    clock.advance(1000)
    d = _decide(orch_core, clock)
    assert d["resume"] is True
    assert d["budget_remaining"] == 3  # dev budget untouched by sdd attempts


# --------------------------------------------------------------------------- cooldown

def test_cooldown_blocks_resume(tmp_orch, clock):
    import orch_core
    _seed_active_phase(orch_core)
    clock.advance(1000)
    orch_core.append_event(
        agent="supervisor", event_type="orchestrator_resume_requested", data={"phase": "dev"})
    clock.advance(50)  # < cooldown_seconds (300)
    d = _decide(orch_core, clock)
    assert d["resume"] is False
    assert d["reason"] == "cooldown_active"
    assert d["budget_remaining"] == 2


# --------------------------------------------------------------------------- in-flight TTL

def test_in_flight_request_blocks_resume(tmp_orch, clock):
    import orch_core
    _seed_active_phase(orch_core)
    clock.advance(1000)
    orch_core.append_event(
        agent="supervisor", event_type="orchestrator_resume_requested", data={"phase": "dev"})
    clock.advance(400)  # past cooldown (300), within in_flight_ttl (900)
    d = _decide(orch_core, clock)
    assert d["resume"] is False
    assert d["reason"] == "resume_in_flight"


def test_in_flight_expires_after_ttl(tmp_orch, clock):
    import orch_core
    _seed_active_phase(orch_core)
    clock.advance(1000)
    orch_core.append_event(
        agent="supervisor", event_type="orchestrator_resume_requested", data={"phase": "dev"})
    clock.advance(1000)  # past in_flight_ttl (900) → expired, resume proceeds
    d = _decide(orch_core, clock)
    assert d["resume"] is True


def test_heartbeat_after_request_clears_in_flight(tmp_orch, clock):
    """A resume that landed (orchestrator emits heartbeat again) clears in-flight, but
    that fresh heartbeat also makes the orchestrator non-stale → no new resume."""
    import orch_core
    _seed_active_phase(orch_core)
    clock.advance(1000)
    orch_core.append_event(
        agent="supervisor", event_type="orchestrator_resume_requested", data={"phase": "dev"})
    orch_core.append_event(
        agent="orchestrator-dev", event_type="orchestrator_heartbeat", data={"phase": "dev"})
    d = _decide(orch_core, clock)
    assert d["resume"] is False
    assert d["reason"] == "orchestrator_live_or_no_pending"


# --------------------------------------------------------------------------- escalated run

def test_escalated_run_is_noop(tmp_orch, clock):
    import orch_core
    _seed_active_phase(orch_core)
    orch_core.append_event(
        agent="orchestrator", event_type="escalation",
        data={"code": "E99_human_approval_required", "severity": "info",
              "reason": "gate", "evidence": [1]})
    clock.advance(1000)
    d = _decide(orch_core, clock)
    assert d["resume"] is False
    assert d["reason"] == "run_escalated_awaiting_human"


# --------------------------------------------------------------------------- disabled

def test_disabled_policy_is_noop(tmp_orch, clock):
    import orch_core
    _seed_active_phase(orch_core)
    clock.advance(1000)
    d = _decide(orch_core, clock, policy={"enabled": False})
    assert d["resume"] is False
    assert d["reason"] == "supervisor_disabled"


def test_config_override_max_resumes(tmp_orch, clock):
    import orch_core
    _seed_active_phase(orch_core)
    clock.advance(1000)
    orch_core.append_event(
        agent="supervisor", event_type="orchestrator_resume_requested", data={"phase": "dev"})
    # max_auto_resumes lowered to 1 → the single attempt exhausts the budget
    d = _decide(orch_core, clock, policy={"max_auto_resumes": 1})
    assert d["escalate"] is True
    assert d["budget_remaining"] == 0


# --------------------------------------------------------------------------- per-task threshold
# Recommendation #5, 2026-07-15 workflow audit (A3 — "supervisor threshold incoherence").
#
# The activity guard used to reuse the flat ORCHESTRATOR_STALE_SECONDS (900s) for a
# RUNNING task's silence window, instead of that task's OWN stale_threshold_seconds()
# (task_type override — e.g. impl=1200s, test-run=1800s). A test-run silent for
# 901-1800s is still healthy (well inside its own allowance) but read as "phase
# silent" under the flat bound, spawning a false-positive second meta-orchestrator
# while the first was still mid-dispatch — colliding with it.

def _seed_running_task_type(orch_core, task_type, phase="dev", wf="wf-sup", tier="standard"):
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": wf, "phases": [{"name": phase, "order": 1, "required": True}]})
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": phase, "order": 1, "workflow_id": wf})
    orch_core.append_event(
        agent="orchestrator-dev", event_type="task_created", task_id="tr_001",
        data={"phase": phase, "deps": [], "tier": tier, "type": task_type, "spec": "x"})
    orch_core.append_event(
        agent="orchestrator-dev", event_type="task_claimed", task_id="tr_001",
        data={"phase": phase, "worker_type": "u-be-qa", "worker_id": "w1"})


def test_flat_900s_would_false_positive_on_healthy_test_run(tmp_orch, clock):
    """Contrast case: WITHOUT the real stale_policy config (stale_config={}, falling
    back to the plain Tier default of 300s for standard), a test-run silent 1000s
    reads as phase-silent — proving the guard's threshold source actually matters,
    not that it was always harmless."""
    import orch_core
    _seed_running_task_type(orch_core, "test-run")
    clock.advance(1000)
    d = _decide(orch_core, clock, stale_config={})
    assert d["resume"] is True
    assert d["reason"] == "stalled_no_heartbeat_no_task_activity"


def test_real_config_suppresses_false_positive_for_test_run(tmp_orch, clock):
    """Same task, same 1000s silence, but with the project's real stale_policy
    override (test-run=1800s) passed as stale_config — main() always passes the
    fully loaded config, never {}. 1000s < 1800s: the worker is healthy, still well
    inside its own allowance. Must NOT resume."""
    import orch_core
    _seed_running_task_type(orch_core, "test-run")
    clock.advance(1000)
    real_config = orch_core.default_config()
    d = _decide(orch_core, clock, stale_config=real_config)
    assert d["resume"] is False
    assert d["reason"] == "phase_tasks_active"


def test_real_config_still_resumes_once_test_run_exceeds_its_own_1800s(tmp_orch, clock):
    """The guard isn't just permissive — past the task's OWN threshold it still
    triggers, proving this is a coherent bound swap, not a resume-suppression."""
    import orch_core
    _seed_running_task_type(orch_core, "test-run")
    clock.advance(1801)
    real_config = orch_core.default_config()
    d = _decide(orch_core, clock, stale_config=real_config)
    assert d["resume"] is True


def test_impl_task_type_override_also_respected(tmp_orch, clock):
    """impl=1200s override: 1000s silence must NOT resume (matches the reaper's own
    bound for the exact same task_type, per stale_threshold_seconds' single-source
    -of-truth contract)."""
    import orch_core
    _seed_running_task_type(orch_core, "impl")
    clock.advance(1000)
    real_config = orch_core.default_config()
    d = _decide(orch_core, clock, stale_config=real_config)
    assert d["resume"] is False
    assert d["reason"] == "phase_tasks_active"


def test_no_stale_config_defaults_to_tier_without_io(tmp_orch, clock, monkeypatch):
    """decide() must stay pure: omitting stale_config must NOT trigger a real
    load_config() file read from inside the 'pure, no I/O' function."""
    import orch_core

    def _boom(*a, **kw):
        raise AssertionError("decide() must not call load_config() itself")

    monkeypatch.setattr(supervisor, "load_config", _boom)
    _seed_running_task_type(orch_core, "impl")
    clock.advance(1000)
    d = _decide(orch_core, clock)  # no stale_config passed -> defaults to {}
    assert d["resume"] is True  # falls back to plain Tier default (300s for standard)


# --------------------------------------------------------------------------- audit-only reduce

def test_new_events_are_audit_only(tmp_orch, clock):
    """The two new events must append + reduce without error and NOT mutate task state."""
    import orch_core
    _seed_active_phase(orch_core)
    before = orch_core.reduce_all()
    orch_core.append_event(
        agent="supervisor", event_type="orchestrator_resume_requested", data={"phase": "dev"})
    orch_core.append_event(
        agent="supervisor", event_type="orchestrator_resumed", data={"phase": "dev"})
    after = orch_core.reduce_all()  # must not raise
    assert after.current_phase == before.current_phase == "dev"
    assert set(after.tasks) == set(before.tasks)


# --------------------------------------------------------------------------- CLI side effects

def test_apply_appends_resume_requested(tmp_orch, clock):
    import orch_core
    _seed_active_phase(orch_core)
    clock.advance(1000)
    d = _decide(orch_core, clock)
    events = list(orch_core.read_events_filtered(event_type=None))
    supervisor._apply(d, events[-1].seq)
    kinds = [e.event_type for e in orch_core.read_events_filtered(event_type=None)]
    assert "orchestrator_resume_requested" in kinds


def test_apply_appends_escalation_on_budget_exhausted(tmp_orch, clock):
    import orch_core
    _seed_active_phase(orch_core)
    clock.advance(1000)
    for _ in range(3):
        orch_core.append_event(
            agent="supervisor", event_type="orchestrator_resume_requested", data={"phase": "dev"})
    d = _decide(orch_core, clock)
    events = list(orch_core.read_events_filtered(event_type=None))
    supervisor._apply(d, events[-1].seq)
    escalations = [e for e in orch_core.read_events_filtered(event_type="escalation")]
    assert any(e.data.get("code") == "E23_resume_budget_exhausted" for e in escalations)
    # E23 halts the run — sticky until a human_response (intended "give up" semantics).
    assert orch_core.reduce_all().run_status == "escalated"


# --------------------------------------------------------------------------- parked resume (C2)

def _seed_parked_between_phases(orch_core, wf="wf-sup"):
    """D1, 2026-07-15 post-fix audit: the meta emitted phase_transitioned and
    stopped (phase_advanced, I5) — current_phase=None, next phase PENDING, and
    the v2.19 detach on-ramp hands exactly this state to /u-supervise. Before
    this fix decide() no-op'd on no_active_phase forever and the workflow was
    parked under active supervision."""
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": wf, "phases": [
            {"name": "sdd", "order": 1, "required": True},
            {"name": "dev", "order": 2, "required": True}]})
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": "sdd", "order": 1, "workflow_id": wf})
    orch_core.append_event(
        agent="orchestrator-sdd", event_type="phase_exit_criterion_met",
        data={"phase": "sdd", "criterion": "c"})
    orch_core.append_event(
        agent="orchestrator-sdd", event_type="phase_exit_approved",
        data={"phase": "sdd", "criteria_met": ["c"], "next_phase": "dev",
              "workflow_id": wf})
    seq = orch_core.reduce_all().last_seq
    orch_core.append_event(
        agent="orchestrator-sdd", event_type="phase_transitioned",
        data={"from_phase": "sdd", "to_phase": "dev", "evidence_seq": seq,
              "workflow_id": wf})


def test_parked_between_phases_resumes_after_silence(tmp_orch, clock):
    import orch_core
    _seed_parked_between_phases(orch_core)
    clock.advance(1000)  # parked state persisted past ORCHESTRATOR_STALE_SECONDS
    d = _decide(orch_core, clock)
    assert d["resume"] is True
    assert d["phase"] == "dev"  # the next pending phase, for budget attribution
    assert d["reason"] == "parked_between_phases_pending_next"


def test_parked_recent_activity_suppresses_resume(tmp_orch, clock):
    """A live driver re-invokes within seconds of phase_advanced ('stay' mode
    passes through current_phase=None transiently) — never race it."""
    import orch_core
    _seed_parked_between_phases(orch_core)
    clock.advance(100)
    d = _decide(orch_core, clock)
    assert d["resume"] is False
    assert d["reason"] == "parked_pending_recent_activity"


def test_parked_never_entered_first_phase_resumes(tmp_orch, clock):
    """D2: phases declared, meta died before entering the first phase."""
    import orch_core
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": "wf-sup", "phases": [
            {"name": "sdd", "order": 1, "required": True}]})
    clock.advance(1000)
    d = _decide(orch_core, clock)
    assert d["resume"] is True
    assert d["phase"] == "sdd"


def test_parked_with_no_pending_phase_is_noop(tmp_orch, clock):
    """All phases completed: nothing to drive — genuine no_active_phase."""
    import orch_core
    _seed_parked_between_phases(orch_core)
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": "dev", "order": 2, "workflow_id": "wf-sup"})
    orch_core.append_event(
        agent="orchestrator-dev", event_type="phase_exit_approved",
        data={"phase": "dev", "criteria_met": ["c"], "next_phase": "done",
              "workflow_id": "wf-sup"})
    seq = orch_core.reduce_all().last_seq
    orch_core.append_event(
        agent="orchestrator-dev", event_type="phase_transitioned",
        data={"from_phase": "dev", "to_phase": "done", "evidence_seq": seq,
              "workflow_id": "wf-sup"})
    clock.advance(1000)
    d = _decide(orch_core, clock)
    assert d["resume"] is False
    assert d["reason"] == "no_active_phase"


def test_parked_escalated_run_is_noop(tmp_orch, clock):
    import orch_core
    _seed_parked_between_phases(orch_core)
    orch_core.append_event(
        agent="orchestrator", event_type="escalation",
        data={"code": "E23_resume_budget_exhausted", "severity": "warning",
              "reason": "r", "evidence": [], "suggested_actions": []})
    clock.advance(1000)
    d = _decide(orch_core, clock)
    assert d["resume"] is False
    assert d["reason"] == "run_escalated_awaiting_human"


def test_parked_resume_budget_exhausts_to_escalation(tmp_orch, clock):
    """Parked resumes share the standard budget machinery, attributed to the
    next pending phase — a meta that keeps dying between phases reaches E23
    instead of being re-spawned forever."""
    import orch_core
    _seed_parked_between_phases(orch_core)
    clock.advance(1000)
    for _ in range(3):
        orch_core.append_event(
            agent="supervisor", event_type="orchestrator_resume_requested",
            data={"phase": "dev"})
    clock.advance(1000)  # past both cooldown and the parked-silence threshold
    d = _decide(orch_core, clock)
    assert d["resume"] is False
    assert d["escalate"] is True
    assert d["reason"] == "resume_budget_exhausted"
