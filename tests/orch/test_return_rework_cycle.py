"""C1, 2026-07-15 post-fix audit — full reject->rework cycle re-validation.

The v2.20.0 return-loop fix reset only `to_phase` to PENDING. The return's
`from_phase` (and any phase between them) kept its COMPLETED status from the
earlier forward pass, so after the rework's own FORWARD hop (dev->review is
forward — no reset) the meta's "lowest order pending" selection skipped
straight past re-review/re-test:

  review->dev return + dev re-completes  -> review stays COMPLETED -> meta
      jumps to test (or terminal) with the rework never re-reviewed; the
      review->test human-approval gate is bypassed because entry happens via
      phase_entered, which has no precondition.
  test->dev return + dev re-completes    -> review AND test stay COMPLETED ->
      M3 derives run_status=completed with the fix never re-tested.

Fixed by resetting EVERY phase from to_phase up to and including from_phase
to PENDING on a return transition (recorded pass cleared), so the standard
"next pending phase" flow re-runs the full validation chain.

These tests drive state purely through appended events and inspect the
derivation exactly where the meta reads it between invocations.
"""
import orch_core
from orch_core import (
    PhaseStatus,
    TaskStatus,
    append_event,
    reduce_all,
)

_WORKFLOW_ID = "wf_rework_cycle"

_PHASES = [
    {"name": "sdd",    "order": 1, "required": True},
    {"name": "dev",    "order": 2, "required": True},
    {"name": "review", "order": 3, "required": True},
    {"name": "test",   "order": 4, "required": True},
]


def _declare_phases():
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": _WORKFLOW_ID, "phases": _PHASES,
    })


def _enter_phase(name, order):
    append_event("orchestrator", "phase_entered",
                 data={"phase": name, "order": order, "workflow_id": _WORKFLOW_ID})


def _create_task(task_id, phase, task_type="impl", spec=None):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": phase, "deps": [], "tier": "standard", "type": task_type,
        "spec": spec or f"spec/{task_id}",
    })


def _run_task(task_id, phase, attempt=1):
    worker = f"worker-{task_id}"
    append_event("orchestrator", "task_claimed", task_id=task_id, attempt=attempt,
                 data={"phase": phase, "worker_type": "impl", "worker_id": worker})
    append_event(worker, "task_completed", task_id=task_id, attempt=attempt,
                 data={"phase": phase, "artifacts": [f"{task_id}.md"],
                       "summary": f"{task_id} complete"})


def _transition(from_phase, to_phase, criteria=("c",)):
    seq = reduce_all().last_seq
    for criterion in criteria:
        append_event(f"orchestrator-{from_phase}", "phase_exit_criterion_met",
                     data={"phase": from_phase, "criterion": criterion})
    append_event(f"orchestrator-{from_phase}", "phase_exit_approved", data={
        "phase": from_phase, "criteria_met": list(criteria), "next_phase": to_phase,
        "workflow_id": _WORKFLOW_ID,
    })
    if from_phase == "review" and to_phase != "dev":
        append_event("human", "human_response", data={
            "escalation_seq": seq, "action": "approve", "operator": "test",
        })
    append_event(f"orchestrator-{from_phase}", "phase_transitioned", data={
        "from_phase": from_phase, "to_phase": to_phase, "evidence_seq": seq,
        "workflow_id": _WORKFLOW_ID,
    })


def _return_transition(from_phase, to_phase):
    seq = reduce_all().last_seq
    append_event(f"orchestrator-{from_phase}", "phase_transitioned", data={
        "from_phase": from_phase, "to_phase": to_phase, "evidence_seq": seq,
        "workflow_id": _WORKFLOW_ID,
    })


def _lowest_order_pending(state):
    """Mirrors orchestrator.md Step 5's exact selection rule."""
    pending = [p for p in state.phases.values() if p.status == PhaseStatus.PENDING]
    if not pending:
        return None
    return min(pending, key=lambda p: p.order).name


def _m3(state):
    phases_payload = [
        {"name": n, "order": p.order, "required": p.required, "status": p.status}
        for n, p in state.phases.items()
    ]
    return orch_core._m3_derive_run_status(
        {"raw_run_status": state.run_status, "phases": phases_payload}
    )


def _advance_to_review():
    """sdd -> dev -> review, with review active and one QA task done."""
    _declare_phases()
    _enter_phase("sdd", 1)
    _transition("sdd", "dev")
    _enter_phase("dev", 2)
    _create_task("dev_tc_001", "dev")
    _run_task("dev_tc_001", "dev")
    _transition("dev", "review")
    _enter_phase("review", 3)
    _create_task("review_tc_001", "review", task_type="qa")
    _run_task("review_tc_001", "review")


# --------------------------------------------------------------- return leg

def test_review_return_resets_review_itself_to_pending(tmp_orch):
    """The from_phase of a return did NOT complete — it rejected. It must be
    re-selectable after the rework, not frozen COMPLETED forever."""
    _advance_to_review()
    _create_task("dev_tc_001_r1", "dev", spec="fix")
    _return_transition("review", "dev")

    state = reduce_all()
    assert state.phases["dev"].status == PhaseStatus.PENDING
    assert state.phases["review"].status == PhaseStatus.PENDING
    assert state.phases["review"].completed_at is None
    assert _lowest_order_pending(state) == "dev"


def test_test_return_resets_intermediate_review_too(tmp_orch):
    """test->dev return invalidates review as well: the rework changes the code
    review approved, so both review and test must re-run."""
    _advance_to_review()
    _transition("review", "test")
    _enter_phase("test", 4)
    _create_task("test_tc_001", "test", task_type="test-run")
    _run_task("test_tc_001", "test")
    _create_task("dev_tc_001_r1", "dev", spec="regression fix")
    _return_transition("test", "dev")

    state = reduce_all()
    assert state.phases["dev"].status == PhaseStatus.PENDING
    assert state.phases["review"].status == PhaseStatus.PENDING
    assert state.phases["test"].status == PhaseStatus.PENDING
    assert state.phases["sdd"].status == PhaseStatus.COMPLETED  # below to_phase: untouched
    assert _lowest_order_pending(state) == "dev"


def test_return_clears_recorded_pass_of_reset_phases(tmp_orch):
    """criteria_met/approved_at from the first pass are stale once the phase is
    re-set to PENDING — they must not survive and masquerade as a fresh pass."""
    _advance_to_review()
    _create_task("dev_tc_001_r1", "dev", spec="fix")
    _return_transition("review", "dev")

    state = reduce_all()
    assert state.phases["dev"].criteria_met == []
    assert state.phases["dev"].approved_at is None


# ------------------------------------------------- rework forward hop (the bug)

def test_rework_forward_hop_requires_re_review(tmp_orch):
    """C1 core: after review->dev return, dev reworks and transitions dev->review
    (FORWARD). Review must be PENDING again — before this fix it stayed COMPLETED
    from the first pass and the meta skipped straight past re-review."""
    _advance_to_review()
    _create_task("dev_tc_001_r1", "dev", spec="fix")
    _return_transition("review", "dev")
    _enter_phase("dev", 2)
    _run_task("dev_tc_001_r1", "dev")
    _transition("dev", "review")

    state = reduce_all()
    assert state.phases["review"].status == PhaseStatus.PENDING
    assert _lowest_order_pending(state) == "review"
    assert _m3(state) == "active"


def test_test_return_full_cycle_does_not_derive_completed(tmp_orch):
    """C1 for test->dev: after the rework's dev->review forward hop, neither
    review nor test may remain COMPLETED — before this fix all four phases were
    COMPLETED and M3 said 'completed' with the fix never re-tested."""
    _advance_to_review()
    _transition("review", "test")
    _enter_phase("test", 4)
    _create_task("test_tc_001", "test", task_type="test-run")
    _run_task("test_tc_001", "test")
    _create_task("dev_tc_001_r1", "dev", spec="regression fix")
    _return_transition("test", "dev")
    _enter_phase("dev", 2)
    _run_task("dev_tc_001_r1", "dev")
    _transition("dev", "review")

    state = reduce_all()
    assert state.phases["review"].status == PhaseStatus.PENDING
    assert state.phases["test"].status == PhaseStatus.PENDING
    assert _lowest_order_pending(state) == "review"
    assert _m3(state) == "active"


def test_second_full_pass_still_completes_normally(tmp_orch):
    """Happy path after a return: the re-run of review and test completes the
    workflow exactly like a first pass — the reset must not wedge anything."""
    _advance_to_review()
    _create_task("dev_tc_001_r1", "dev", spec="fix")
    _return_transition("review", "dev")
    _enter_phase("dev", 2)
    _run_task("dev_tc_001_r1", "dev")
    _transition("dev", "review")
    _enter_phase("review", 3)
    _create_task("review_tc_002", "review", task_type="qa")
    _run_task("review_tc_002", "review")
    _transition("review", "test")
    _enter_phase("test", 4)
    _create_task("test_tc_001", "test", task_type="test-run")
    _run_task("test_tc_001", "test")
    _transition("test", "done")

    state = reduce_all()
    assert _m3(state) == "completed"
    assert _lowest_order_pending(state) is None


def test_forward_transition_never_resets_anything(tmp_orch):
    """Boundary: forward transitions keep the v2.20.0 behavior — from_phase
    COMPLETED, downstream phases untouched."""
    _declare_phases()
    _enter_phase("sdd", 1)
    _transition("sdd", "dev")

    state = reduce_all()
    assert state.phases["sdd"].status == PhaseStatus.COMPLETED
    assert state.phases["dev"].status == PhaseStatus.PENDING
    assert state.phases["review"].status == PhaseStatus.PENDING
