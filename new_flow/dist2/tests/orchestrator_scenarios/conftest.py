"""
Shared fixtures and helpers for orchestrator_scenarios tests (Level B).

Level B tests validate orchestration state-machine behavior by building
event-log fixtures in-process (via orch_core) and asserting on derived
state via reduce_all(). No LLM is spawned.

All tests depend on the parent conftest's `tmp_orch` fixture, which
monkeypatches orch_core paths to a temporary directory so tests are
fully isolated.
"""
import pytest
import orch_core
from orch_core import (
    append_event,
    reduce_all,
    TaskStatus,
    PhaseStatus,
)


WORKFLOW_ID = "wf_scenario_test"

DEFAULT_PHASES = [
    {"name": "sdd",    "order": 1, "required": True},
    {"name": "dev",    "order": 2, "required": True},
    {"name": "review", "order": 3, "required": True},
    {"name": "test",   "order": 4, "required": True},
]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def wf_env(tmp_orch):
    """Workflow environment built on top of tmp_orch.

    Returns tmp_path. All orch_core module-level paths already point to
    tmp_path/.orch via the parent fixture's monkeypatch.
    """
    return tmp_orch


# ---------------------------------------------------------------------------
# Phase builders
# ---------------------------------------------------------------------------

def declare_phases(phases=None, wf_id=WORKFLOW_ID):
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": wf_id,
        "phases": phases or DEFAULT_PHASES,
    })


def enter_phase(name, order):
    append_event("orchestrator", "phase_entered", data={"phase": name, "order": order})


def transition_phase(from_phase, to_phase, criteria):
    """Emit the three events that constitute a completed phase transition."""
    seq = reduce_all().last_seq
    for criterion in criteria:
        append_event(f"orchestrator-{from_phase}", "phase_exit_criterion_met", data={
            "phase": from_phase, "criterion": criterion,
        })
    append_event(f"orchestrator-{from_phase}", "phase_exit_approved", data={
        "phase": from_phase, "criteria_met": criteria, "next_phase": to_phase,
    })
    append_event(f"orchestrator-{from_phase}", "phase_transitioned", data={
        "from_phase": from_phase, "to_phase": to_phase, "evidence_seq": seq,
    })


# ---------------------------------------------------------------------------
# Task lifecycle builders
# ---------------------------------------------------------------------------

def create_task(task_id, phase, task_type="impl", tier="standard", deps=None, spec=None):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": phase,
        "type": task_type,
        "tier": tier,
        "deps": deps or [],
        "spec": spec or f"spec/{task_id}.md",
    })


def claim_task(task_id, phase, worker_id=None, worker_type="impl", attempt=1):
    wid = worker_id or f"w_{task_id}"
    append_event("orchestrator", "task_claimed", task_id=task_id, attempt=attempt, data={
        "phase": phase, "worker_type": worker_type, "worker_id": wid,
    })
    return wid


def complete_task(task_id, phase, worker_id=None, artifacts=None, attempt=1):
    wid = worker_id or f"w_{task_id}"
    append_event(wid, "task_completed", task_id=task_id, attempt=attempt, data={
        "phase": phase,
        "artifacts": artifacts or [f"{task_id}-delivery.md"],
        "summary": f"{task_id} done",
    })


def fail_task(task_id, phase, worker_id=None, retryable=False, attempt=1):
    wid = worker_id or f"w_{task_id}"
    append_event(wid, "task_failed", task_id=task_id, attempt=attempt, data={
        "phase": phase, "reason": "runtime_error", "retryable": retryable,
    })


def dlq_task(task_id, phase, reason="non_retryable"):
    append_event("orchestrator", "task_dlq", task_id=task_id, data={
        "phase": phase, "reason": reason, "last_error": "max attempts reached",
    })


def run_task(task_id, phase, worker_type="impl", artifacts=None):
    """Claim + complete a task in one call."""
    wid = claim_task(task_id, phase, worker_type=worker_type)
    complete_task(task_id, phase, worker_id=wid, artifacts=artifacts)


# ---------------------------------------------------------------------------
# Escalation builders
# ---------------------------------------------------------------------------

def escalate(code, reason, agent="orchestrator", evidence=None):
    append_event(agent, "escalation", data={
        "code": code,
        "severity": "high",
        "reason": reason,
        "evidence": evidence or [],
        "suggested_actions": [],
    })


def human_respond(escalation_seq, action, operator="ops"):
    append_event("human", "human_response", data={
        "escalation_seq": escalation_seq,
        "action": action,
        "operator": operator,
    })


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

def assert_task_status(state, task_id, expected_status):
    assert task_id in state.tasks, f"task {task_id!r} not in state"
    actual = state.tasks[task_id].status
    assert actual == TaskStatus(expected_status), (
        f"task {task_id}: expected {expected_status}, got {actual}"
    )


def assert_escalation_present(state, code=None):
    assert state.escalation is not None, "expected active escalation, found none"
    if code:
        assert state.escalation.get("code") == code, (
            f"expected escalation code {code!r}, got {state.escalation.get('code')!r}"
        )


def assert_no_escalation(state):
    assert state.escalation is None, (
        f"expected no escalation, found: {state.escalation}"
    )


def assert_run_status(state, expected):
    assert state.run_status == expected, (
        f"run_status: expected {expected!r}, got {state.run_status!r}"
    )


def assert_current_phase(state, expected):
    assert state.current_phase == expected, (
        f"current_phase: expected {expected!r}, got {state.current_phase!r}"
    )


def assert_phase_status(state, phase_name, expected_status):
    assert phase_name in state.phases, f"phase {phase_name!r} not in state"
    actual = state.phases[phase_name].status
    assert actual == PhaseStatus(expected_status), (
        f"phase {phase_name}: expected {expected_status!r}, got {actual!r}"
    )
