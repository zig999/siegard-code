"""
E2E tests: 4-phase workflow lifecycle (sdd → dev → review → test).

These tests validate the orchestration engine's behavior across full phase
lifecycles by emitting events directly via append_event (simulating what
phase orchestrators and workers would produce), then asserting on derived
state via reduce_all().

No AI agents are spawned. Tests are deterministic and use only stdlib.

Scenarios:
  E.1  — First-run: phase_declared with 4 default phases
  E.2  — Phase entry: current_phase transitions correctly per phase
  E.3  — Phase routing table: each phase maps to expected orchestrator name
  E.4  — Full 4-phase happy path: sdd → dev → review → test
  E.5  — Review → Dev return: rejected tasks re-enter dev phase
  E.6  — run_status derivation: pending, active, completed, escalated
  E.7  — Escalation blocks on unresolved E99
  E.8  — Phase orchestrator pass-through: log_seq_at_spawn semantics
  E.9  — Hash chain integrity across 4-phase workflow
  E.10 — DLQ cascade across phase boundary (dev task in DLQ cascades to review)
"""
import pytest
import orch_core
from orch_core import (
    append_event,
    read_events,
    read_events_filtered,
    reduce_all,
    verify_chain,
    TaskStatus,
    PhaseStatus,
    EventType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORKFLOW_ID = "wf_e2e_test"

_DEFAULT_PHASES = [
    {"name": "sdd",    "order": 1, "required": True},
    {"name": "dev",    "order": 2, "required": True},
    {"name": "review", "order": 3, "required": True},
    {"name": "test",   "order": 4, "required": True},
]


def _declare_phases(phases=None):
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": _WORKFLOW_ID,
        "phases": phases or _DEFAULT_PHASES,
    })


def _enter_phase(name, order):
    append_event("orchestrator", "phase_entered", data={"phase": name, "order": order, "workflow_id": _WORKFLOW_ID})


def _create_task(task_id, phase, deps=None, task_type="impl", tier="standard", spec=None):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": phase,
        "deps": deps or [],
        "tier": tier,
        "type": task_type,
        "spec": spec or f"spec/{task_id}",
    })


def _run_task(task_id, phase, attempt=1, worker=None, artifacts=None):
    """Claim and complete a task in one call."""
    worker = worker or f"worker-{task_id}"
    append_event("orchestrator", "task_claimed", task_id=task_id, attempt=attempt, data={
        "phase": phase, "worker_type": "impl", "worker_id": worker,
    })
    append_event(worker, "task_completed", task_id=task_id, attempt=attempt, data={
        "phase": phase,
        "artifacts": artifacts or [f"{task_id}-delivery.md"],
        "summary": f"{task_id} complete",
    })


def _transition_phase(from_phase, to_phase, criteria):
    seq = reduce_all().last_seq
    for criterion in criteria:
        append_event(f"orchestrator-{from_phase}", "phase_exit_criterion_met", data={
            "phase": from_phase, "criterion": criterion,
        })
    append_event(f"orchestrator-{from_phase}", "phase_exit_approved", data={
        "phase": from_phase, "criteria_met": criteria, "next_phase": to_phase, "workflow_id": _WORKFLOW_ID,
    })
    # prod-hardening task 01: leaving review forward requires a human approval in the log.
    if from_phase == "review" and to_phase != "dev":
        append_event("human", "human_response", data={
            "escalation_seq": seq, "action": "approve", "operator": "test",
        })
    append_event(f"orchestrator-{from_phase}", "phase_transitioned", data={
        "from_phase": from_phase, "to_phase": to_phase, "evidence_seq": seq, "workflow_id": _WORKFLOW_ID,
    })


def _escalate(agent, code, reason, evidence=None):
    append_event(agent, "escalation", data={
        "code": code,
        "severity": "info",
        "reason": reason,
        "evidence": evidence or [],
        "suggested_actions": [],
    })


# ---------------------------------------------------------------------------
# Routing table — mirrors orchestrator.md §Phase routing table
# ---------------------------------------------------------------------------

_ROUTING_TABLE = {
    None:     "orchestrator-sdd",
    "sdd":    "orchestrator-sdd",
    "dev":    "orchestrator-dev",
    "review": "orchestrator-review",
    "test":   "orchestrator-test",
}


def _route(current_phase):
    return _ROUTING_TABLE.get(current_phase)


# ---------------------------------------------------------------------------
# run_status derivation — mirrors orchestrator.md §Step 2
# ---------------------------------------------------------------------------

def _derive_run_status(state, declared_phases=None):
    """Derives workflow-level run_status from OrchState."""
    phases_list = declared_phases or _DEFAULT_PHASES
    required_names = {p["name"] for p in phases_list if p.get("required")}

    has_unresolved_escalation = (
        state.escalation is not None
        and not any(
            e.event_type == "human_response"
            for e in read_events()
            if e.seq > (state.escalation.get("seq", 0) if isinstance(state.escalation, dict) else 0)
        )
    )
    if has_unresolved_escalation:
        return "escalated"

    all_completed = all(
        state.phases.get(name) is not None
        and state.phases[name].status == PhaseStatus.COMPLETED
        for name in required_names
    )
    if all_completed:
        return "completed"

    if state.current_phase is not None:
        return "active"

    return "pending"


# ---------------------------------------------------------------------------
# E.1 — First-run: phase_declared with 4 phases
# ---------------------------------------------------------------------------

class TestPhaseDeclaration:
    def test_phase_declared_emitted_once(self, tmp_orch):
        """E.1: phase_declared event contains all 4 default phases."""
        _declare_phases()
        events = list(read_events_filtered(event_type=EventType.PHASE_DECLARED))
        assert len(events) == 1
        data = events[0].data
        assert data["workflow_id"] == _WORKFLOW_ID
        names = [p["name"] for p in data["phases"]]
        assert names == ["sdd", "dev", "review", "test"]

    def test_phase_declared_orders_correct(self, tmp_orch):
        """E.1: phases have sequential order values 1–4."""
        _declare_phases()
        events = list(read_events_filtered(event_type=EventType.PHASE_DECLARED))
        orders = [p["order"] for p in events[0].data["phases"]]
        assert orders == [1, 2, 3, 4]

    def test_no_phase_declared_means_no_phase_state(self, tmp_orch):
        """E.1: before phase_declared, state has no phases."""
        state = reduce_all()
        assert state.phases == {}
        assert state.current_phase is None

    def test_phase_declared_without_entry_has_no_current_phase(self, tmp_orch):
        """E.1: phase_declared alone does not activate a phase."""
        _declare_phases()
        state = reduce_all()
        assert state.current_phase is None

    def test_custom_phases_in_declaration(self, tmp_orch):
        """E.1: phase_declared accepts a custom phases array."""
        custom = [{"name": "design", "order": 1, "required": True}]
        _declare_phases(custom)
        events = list(read_events_filtered(event_type=EventType.PHASE_DECLARED))
        assert events[0].data["phases"][0]["name"] == "design"


# ---------------------------------------------------------------------------
# E.2 — Phase entry: current_phase transitions correctly
# ---------------------------------------------------------------------------

class TestPhaseEntry:
    def test_phase_entered_sets_current_phase(self, tmp_orch):
        """E.2: after phase_entered sdd, current_phase is sdd."""
        _declare_phases()
        _enter_phase("sdd", 1)
        state = reduce_all()
        assert state.current_phase == "sdd"
        assert state.phases["sdd"].status == PhaseStatus.ACTIVE

    def test_phase_transitioned_completes_source_phase(self, tmp_orch):
        """E.2: phase_transitioned marks from_phase as COMPLETED."""
        _declare_phases()
        _enter_phase("sdd", 1)
        _transition_phase("sdd", "dev", ["c1"])
        state = reduce_all()
        assert state.phases["sdd"].status == PhaseStatus.COMPLETED

    def test_phase_entered_dev_after_sdd_transition(self, tmp_orch):
        """E.2: entering dev after sdd transition sets current_phase to dev."""
        _declare_phases()
        _enter_phase("sdd", 1)
        _transition_phase("sdd", "dev", ["c1"])
        _enter_phase("dev", 2)
        state = reduce_all()
        assert state.current_phase == "dev"
        assert state.phases["dev"].status == PhaseStatus.ACTIVE

    def test_review_return_to_dev_resets_current_phase(self, tmp_orch):
        """E.2: phase_transitioned {to_phase: dev} from review makes dev active again."""
        _declare_phases()
        _enter_phase("sdd", 1)
        _transition_phase("sdd", "dev", ["c1"])
        _enter_phase("dev", 2)
        _transition_phase("dev", "review", ["c2"])
        _enter_phase("review", 3)
        # Review returns tasks to dev
        append_event("orchestrator-review", "phase_transitioned", data={
            "from_phase": "review", "to_phase": "dev", "evidence_seq": 1, "workflow_id": _WORKFLOW_ID,
        })
        _enter_phase("dev", 2)
        state = reduce_all()
        assert state.current_phase == "dev"
        assert state.phases["dev"].status == PhaseStatus.ACTIVE


# ---------------------------------------------------------------------------
# E.3 — Phase routing table
# ---------------------------------------------------------------------------

class TestPhaseRoutingTable:
    @pytest.mark.parametrize("phase,expected", [
        (None,     "orchestrator-sdd"),
        ("sdd",    "orchestrator-sdd"),
        ("dev",    "orchestrator-dev"),
        ("review", "orchestrator-review"),
        ("test",   "orchestrator-test"),
    ])
    def test_routing_maps_phase_to_orchestrator(self, tmp_orch, phase, expected):
        """E.3: routing table maps each phase to the correct orchestrator."""
        assert _route(phase) == expected

    def test_unknown_phase_returns_none(self, tmp_orch):
        """E.3: routing table returns None for unknown phase."""
        assert _route("unknown_phase") is None

    def test_routing_covers_all_declared_phases(self, tmp_orch):
        """E.3: every declared phase has a routing entry."""
        _declare_phases()
        events = list(read_events_filtered(event_type=EventType.PHASE_DECLARED))
        declared_names = [p["name"] for p in events[0].data["phases"]]
        for name in declared_names:
            assert _route(name) is not None, f"no routing entry for phase: {name}"


# ---------------------------------------------------------------------------
# E.4 — Full 4-phase happy path: sdd → dev → review → test
# ---------------------------------------------------------------------------

class TestFullFourPhaseLifecycle:
    def _run_full_workflow(self):
        """Simulate a complete 4-phase workflow via log events."""
        _declare_phases()

        # SDD phase
        _enter_phase("sdd", 1)
        _create_task("sdd_auth_spec-writer",        "sdd", spec="specs/auth.yaml")
        _create_task("sdd_auth_spec-validator-front","sdd", deps=["sdd_auth_spec-writer"])
        _run_task("sdd_auth_spec-writer",         "sdd", artifacts=["specs/auth.yaml"])
        _run_task("sdd_auth_spec-validator-front","sdd", artifacts=["specs/_validation/auth.yaml"])
        _transition_phase("sdd", "dev", ["handoff_manifest_approved", "all_domains_validated"])

        # DEV phase
        _enter_phase("dev", 2)
        _create_task("dev_planning", "dev", task_type="planning", tier="critical")
        _run_task("dev_planning", "dev", artifacts=["specs/backlog/backlog.md"])
        _create_task("dev_tc_001", "dev", task_type="impl", deps=["dev_planning"])
        _create_task("dev_tc_002", "dev", task_type="impl", deps=["dev_planning"])
        _run_task("dev_tc_001", "dev", artifacts=["delivery/tc-001-delivery.md"])
        _run_task("dev_tc_002", "dev", artifacts=["delivery/tc-002-delivery.md"])
        _transition_phase("dev", "review",
                          ["all_impl_tasks_terminal", "all_deliveries_qa_ready", "no_open_prohibitions"])

        # REVIEW phase
        _enter_phase("review", 3)
        _create_task("review_dev_tc_001", "review", spec="delivery/tc-001-delivery.md")
        _create_task("review_dev_tc_002", "review", spec="delivery/tc-002-delivery.md")
        _run_task("review_dev_tc_001", "review", artifacts=["qa/review_dev_tc_001-qa.md"])
        _run_task("review_dev_tc_002", "review", artifacts=["qa/review_dev_tc_002-qa.md"])
        _transition_phase("review", "test",
                          ["all_qa_verdicts_approved", "no_open_critical_findings",
                           "documentation_verified"])

        # TEST phase
        _enter_phase("test", 4)
        _create_task("test_suite_001", "test", task_type="test-run")
        _run_task("test_suite_001", "test", artifacts=["test-results/run-001.json"])
        _transition_phase("test", "done", ["all_tests_passing"])

    def test_all_four_phases_complete(self, tmp_orch):
        """E.4: after full workflow, sdd/dev/review/test are all COMPLETED."""
        self._run_full_workflow()
        state = reduce_all()
        for phase in ["sdd", "dev", "review", "test"]:
            assert state.phases[phase].status == PhaseStatus.COMPLETED, \
                f"phase {phase} not COMPLETED: {state.phases[phase].status}"

    def test_all_tasks_terminal(self, tmp_orch):
        """E.4: after full workflow, every task is in a terminal status."""
        self._run_full_workflow()
        state = reduce_all()
        terminal = {TaskStatus.COMPLETED, TaskStatus.DLQ}
        for tid, task in state.tasks.items():
            assert task.status in terminal, f"task {tid} not terminal: {task.status}"

    def test_run_status_completed(self, tmp_orch):
        """E.4: run_status is 'completed' after all required phases finish."""
        self._run_full_workflow()
        state = reduce_all()
        assert _derive_run_status(state) == "completed"

    def test_phase_transition_event_count(self, tmp_orch):
        """E.4: exactly 4 phase_transitioned events in log (sdd→dev, dev→review, review→test, test→done)."""
        self._run_full_workflow()
        events = list(read_events_filtered(event_type=EventType.PHASE_TRANSITIONED))
        assert len(events) == 4

    def test_phase_entered_event_count(self, tmp_orch):
        """E.4: exactly 4 phase_entered events — one per phase."""
        self._run_full_workflow()
        events = list(read_events_filtered(event_type=EventType.PHASE_ENTERED))
        entered_phases = [e.data["phase"] for e in events]
        assert entered_phases == ["sdd", "dev", "review", "test"]

    def test_hash_chain_intact_after_full_workflow(self, tmp_orch):
        """E.4: verify_chain passes on the full 4-phase log."""
        self._run_full_workflow()
        result = verify_chain(mode="strict")
        assert result.ok is True

    def test_task_counts_per_phase(self, tmp_orch):
        """E.4: correct number of tasks per phase after full workflow."""
        self._run_full_workflow()
        state = reduce_all()
        sdd_tasks   = [t for t in state.tasks.values() if t.phase == "sdd"]
        dev_tasks   = [t for t in state.tasks.values() if t.phase == "dev"]
        review_tasks= [t for t in state.tasks.values() if t.phase == "review"]
        test_tasks  = [t for t in state.tasks.values() if t.phase == "test"]
        assert len(sdd_tasks)    == 2
        assert len(dev_tasks)    == 3   # planning + tc_001 + tc_002
        assert len(review_tasks) == 2
        assert len(test_tasks)   == 1


# ---------------------------------------------------------------------------
# E.5 — Review → Dev return: rejected tasks re-enter dev phase
# ---------------------------------------------------------------------------

class TestReviewReturnToDev:
    def _setup_review_with_return(self):
        _declare_phases()

        # SDD + DEV (abbreviated)
        _enter_phase("sdd", 1)
        _transition_phase("sdd", "dev", ["c_sdd"])
        _enter_phase("dev", 2)
        _create_task("dev_tc_001", "dev", task_type="impl")
        _create_task("dev_tc_002", "dev", task_type="impl")
        _run_task("dev_tc_001", "dev", artifacts=["delivery/tc-001-delivery.md"])
        _run_task("dev_tc_002", "dev", artifacts=["delivery/tc-002-delivery.md"])
        _transition_phase("dev", "review", ["c_dev"])

        # REVIEW — dispatch QA
        _enter_phase("review", 3)
        _create_task("review_dev_tc_001", "review", spec="delivery/tc-001-delivery.md")
        _create_task("review_dev_tc_002", "review", spec="delivery/tc-002-delivery.md")
        _run_task("review_dev_tc_001", "review", artifacts=["qa/review_dev_tc_001-qa.md"])
        _run_task("review_dev_tc_002", "review", artifacts=["qa/review_dev_tc_002-qa.md"])

        # Human responds: return tc_002 to dev
        _escalate("orchestrator-review", "E99_human_approval_required", "awaiting approval")
        escalation_seq = reduce_all().last_seq
        append_event("human", "human_response", data={
            "escalation_seq": escalation_seq,
            "action": "return_partial",
            "operator": "human",
            "rejected_task_ids": ["dev_tc_002"],
        })

        # Review orchestrator creates revision task in dev phase and transitions back
        _create_task("dev_tc_002_r1", "dev", task_type="impl",
                     spec="specs/backlog/tc-002.md")
        append_event("orchestrator-review", "phase_transitioned", data={
            "from_phase": "review", "to_phase": "dev", "evidence_seq": 1, "workflow_id": _WORKFLOW_ID,
        })

        # Dev phase resumes and completes the revision
        _enter_phase("dev", 2)
        _run_task("dev_tc_002_r1", "dev", artifacts=["delivery/tc-002-r1-delivery.md"])
        _transition_phase("dev", "review", ["c_dev_r2"])

        # Review runs again and approves
        _enter_phase("review", 3)
        _create_task("review_dev_tc_002_r1", "review",
                     spec="delivery/tc-002-r1-delivery.md")
        _run_task("review_dev_tc_002_r1", "review",
                  artifacts=["qa/review_dev_tc_002_r1-qa.md"])
        _transition_phase("review", "test", ["all_qa_verdicts_approved",
                                              "no_open_critical_findings",
                                              "documentation_verified"])

    def test_revision_task_created_in_dev_phase(self, tmp_orch):
        """E.5: after review returns a task, a revision task exists in dev phase."""
        self._setup_review_with_return()
        state = reduce_all()
        assert "dev_tc_002_r1" in state.tasks
        assert state.tasks["dev_tc_002_r1"].phase == "dev"

    def test_revision_task_is_terminal(self, tmp_orch):
        """E.5: revision task completes successfully."""
        self._setup_review_with_return()
        state = reduce_all()
        assert state.tasks["dev_tc_002_r1"].status == TaskStatus.COMPLETED

    def test_review_phase_transitioned_twice(self, tmp_orch):
        """E.5: two phase_transitioned events from review (→dev, →test)."""
        self._setup_review_with_return()
        events = list(read_events_filtered(event_type=EventType.PHASE_TRANSITIONED))
        review_transitions = [
            e for e in events if e.data.get("from_phase") == "review"
        ]
        assert len(review_transitions) == 2
        destinations = {e.data["to_phase"] for e in review_transitions}
        assert destinations == {"dev", "test"}

    def test_dev_phase_entered_twice(self, tmp_orch):
        """E.5: dev phase is entered twice (original + revision cycle)."""
        self._setup_review_with_return()
        events = list(read_events_filtered(event_type=EventType.PHASE_ENTERED))
        dev_entries = [e for e in events if e.data["phase"] == "dev"]
        assert len(dev_entries) == 2

    def test_human_response_recorded_in_log(self, tmp_orch):
        """E.5: human_response event is present and has correct action."""
        self._setup_review_with_return()
        events = list(read_events_filtered(event_type=EventType.HUMAN_RESPONSE))
        # prod-hardening task 01: the round-trip now records two human_responses —
        # the return_partial rejection, then the approve gating the final review->test.
        assert len(events) == 2
        return_partial = [e for e in events if e.data["action"] == "return_partial"]
        assert len(return_partial) == 1
        assert "dev_tc_002" in return_partial[0].data["rejected_task_ids"]
        assert any(e.data["action"] == "approve" for e in events)


class TestReturnTransitionResetsDestinationPhase:
    """Recommendation #2, 2026-07-15 workflow audit (C2 — "return-loop break").

    _handle_phase_transitioned only ever updated from_phase. On a RETURN transition
    (review->dev, test->dev, test->review) to_phase was already COMPLETED from its
    earlier forward pass and stayed COMPLETED forever: the meta's phase selection
    ("lowest order whose status is pending", orchestrator.md Step 5) could never
    re-select it, and M3 derived run_status=completed once every phase had been
    marked COMPLETED at least once — even with the returned rework sitting PENDING,
    unfinished. Fixed by resetting to_phase to PENDING on a _RETURN_TRANSITIONS pair.

    Unlike TestReviewReturnToDev above (which hand-emits phase_entered right after
    the return and so never exercises the selection/derivation bug — see its
    docstring-free `_enter_phase("dev", 2)` at line 427), these tests drive state
    purely through appended events and inspect derivation BEFORE any subsequent
    phase_entered — exactly the window the meta reads between invocations.
    """

    @staticmethod
    def _lowest_order_pending(state):
        """Mirrors orchestrator.md Step 5's exact selection rule."""
        pending = [p for p in state.phases.values() if p.status == PhaseStatus.PENDING]
        if not pending:
            return None
        return min(pending, key=lambda p: p.order).name

    def test_review_to_dev_return_resets_dev_to_pending(self, tmp_orch):
        _declare_phases()
        _enter_phase("sdd", 1)
        _transition_phase("sdd", "dev", ["c_sdd"])
        _enter_phase("dev", 2)
        _create_task("dev_tc_001", "dev")
        _run_task("dev_tc_001", "dev", artifacts=["d.md"])
        _transition_phase("dev", "review", ["c_dev"])
        _enter_phase("review", 3)
        _create_task("dev_tc_002_r1", "dev", spec="fix")
        seq = reduce_all().last_seq
        append_event("orchestrator-review", "phase_transitioned", data={
            "from_phase": "review", "to_phase": "dev",
            "evidence_seq": seq, "workflow_id": _WORKFLOW_ID,
        })

        state = reduce_all()
        assert state.phases["dev"].status == PhaseStatus.PENDING
        assert state.phases["dev"].completed_at is None
        # Before the fix this picked "test" (dev stayed COMPLETED) — skipping rework.
        assert self._lowest_order_pending(state) == "dev"

    def test_test_to_dev_return_does_not_derive_completed(self, tmp_orch):
        _declare_phases()
        _enter_phase("sdd", 1)
        _transition_phase("sdd", "dev", ["c_sdd"])
        _enter_phase("dev", 2)
        _create_task("dev_tc_001", "dev")
        _run_task("dev_tc_001", "dev", artifacts=["d.md"])
        _transition_phase("dev", "review", ["c_dev"])
        _enter_phase("review", 3)
        _create_task("review_tc_001", "review", spec="d.md")
        _run_task("review_tc_001", "review", artifacts=["qa.md"])
        _escalate("orchestrator-review", "E99_human_approval_required", "awaiting approval")
        append_event("human", "human_response", data={
            "escalation_seq": reduce_all().last_seq, "action": "approve", "operator": "human",
        })
        _transition_phase("review", "test", ["all_qa_verdicts_approved"])
        _enter_phase("test", 4)
        _create_task("test_tc_001", "test", spec="d.md")
        _run_task("test_tc_001", "test", artifacts=["report.md"])
        _create_task("dev_tc_001_r1", "dev", spec="regression fix")
        seq = reduce_all().last_seq
        append_event("orchestrator-test", "phase_transitioned", data={
            "from_phase": "test", "to_phase": "dev",
            "evidence_seq": seq, "workflow_id": _WORKFLOW_ID,
        })

        state = reduce_all()
        phases_payload = [
            {"name": n, "order": p.order, "required": p.required, "status": p.status}
            for n, p in state.phases.items()
        ]
        run_status = orch_core._m3_derive_run_status(
            {"raw_run_status": state.run_status, "phases": phases_payload}
        )
        # Before the fix: all four phases COMPLETED -> M3 said "completed" with the
        # rework task (dev_tc_001_r1) still PENDING. Now dev is reset -> "active".
        assert run_status == "active"
        assert state.tasks["dev_tc_001_r1"].status == TaskStatus.PENDING
        assert self._lowest_order_pending(state) == "dev"

    def test_forward_transition_leaves_to_phase_untouched(self, tmp_orch):
        """Boundary: a FORWARD transition (not in _RETURN_TRANSITIONS) must not
        reset to_phase — it should still be PENDING pre-entry as always, and the
        fix must not interfere with the normal happy path."""
        _declare_phases()
        _enter_phase("sdd", 1)
        seq = reduce_all().last_seq
        append_event("orchestrator-sdd", "phase_exit_criterion_met",
                     data={"phase": "sdd", "criterion": "c"})
        append_event("orchestrator-sdd", "phase_exit_approved", data={
            "phase": "sdd", "criteria_met": ["c"], "next_phase": "dev",
            "workflow_id": _WORKFLOW_ID,
        })
        append_event("orchestrator-sdd", "phase_transitioned", data={
            "from_phase": "sdd", "to_phase": "dev", "evidence_seq": seq,
            "workflow_id": _WORKFLOW_ID,
        })
        state = reduce_all()
        assert state.phases["sdd"].status == PhaseStatus.COMPLETED
        assert state.phases["dev"].status == PhaseStatus.PENDING


# ---------------------------------------------------------------------------
# E.6 — run_status derivation
# ---------------------------------------------------------------------------

class TestRunStatusDerivation:
    def test_pending_before_any_phase_entered(self, tmp_orch):
        """E.6: run_status is 'pending' before any phase_entered."""
        _declare_phases()
        state = reduce_all()
        assert _derive_run_status(state) == "pending"

    def test_active_while_phase_in_progress(self, tmp_orch):
        """E.6: run_status is 'active' while a phase is running."""
        _declare_phases()
        _enter_phase("sdd", 1)
        state = reduce_all()
        assert _derive_run_status(state) == "active"

    def test_completed_after_all_phases_done(self, tmp_orch):
        """E.6: run_status is 'completed' when all required phases complete."""
        _declare_phases()
        for name, order, to_next in [
            ("sdd", 1, "dev"), ("dev", 2, "review"),
            ("review", 3, "test"), ("test", 4, "done"),
        ]:
            _enter_phase(name, order)
            _transition_phase(name, to_next, ["c"])
        state = reduce_all()
        assert _derive_run_status(state) == "completed"

    def test_escalated_on_unresolved_escalation(self, tmp_orch):
        """E.6: run_status is 'escalated' when escalation has no human_response."""
        _declare_phases()
        _enter_phase("sdd", 1)
        _escalate("orchestrator-sdd", "E99_human_confirmation_required",
                  "awaiting confirmation")
        state = reduce_all()
        assert _derive_run_status(state) == "escalated"

    def test_active_after_escalation_resolved(self, tmp_orch):
        """E.6: run_status returns to 'active' after human_response is emitted."""
        _declare_phases()
        _enter_phase("sdd", 1)
        _escalate("orchestrator-sdd", "E99_human_confirmation_required",
                  "awaiting confirmation")
        escalation_seq = reduce_all().last_seq
        append_event("human", "human_response", data={
            "escalation_seq": escalation_seq,
            "action": "confirm_proceed",
            "operator": "human",
        })
        state = reduce_all()
        # Escalation is still in state (unresolved escalation check reads events)
        # After human_response, status should no longer be "escalated"
        assert _derive_run_status(state) in ("active", "pending")


# ---------------------------------------------------------------------------
# E.7 — Escalation detection
# ---------------------------------------------------------------------------

class TestEscalationDetection:
    def test_escalation_present_in_state(self, tmp_orch):
        """E.7: escalation event is reflected in state.escalation."""
        _declare_phases()
        _enter_phase("sdd", 1)
        _escalate("orchestrator-sdd", "E99_human_confirmation_required",
                  "confirm to proceed")
        state = reduce_all()
        assert state.escalation is not None

    def test_escalation_code_preserved(self, tmp_orch):
        """E.7: escalation code is correctly stored in state."""
        _declare_phases()
        _enter_phase("dev", 2)
        _escalate("orchestrator-dev", "E07_planning_failed", "planning failed")
        state = reduce_all()
        code = (state.escalation.get("code")
                if isinstance(state.escalation, dict)
                else getattr(state.escalation, "code", None))
        assert code == "E07_planning_failed"

    def test_e99_from_sdd_blocks_workflow(self, tmp_orch):
        """E.7: E99 escalation in sdd phase makes run_status 'escalated'."""
        _declare_phases()
        _enter_phase("sdd", 1)
        _create_task("sdd_auth_spec-writer", "sdd")
        _escalate("orchestrator-sdd", "E99_human_confirmation_required",
                  "sdd requires confirmation before dispatch")
        state = reduce_all()
        assert _derive_run_status(state) == "escalated"

    def test_e99_from_review_approval_gate(self, tmp_orch):
        """E.7: E99_human_approval_required from review phase is detected."""
        _declare_phases()
        _enter_phase("review", 3)
        _escalate("orchestrator-review", "E99_human_approval_required",
                  "QA complete — awaiting approval")
        state = reduce_all()
        assert state.escalation is not None
        assert _derive_run_status(state) == "escalated"


# ---------------------------------------------------------------------------
# E.8 — log_seq_at_spawn semantics
# ---------------------------------------------------------------------------

class TestLogSeqAtSpawn:
    def test_last_seq_increases_monotonically(self, tmp_orch):
        """E.8: last_seq always reflects the highest seq after events are appended."""
        _declare_phases()
        seq0 = reduce_all().last_seq
        _enter_phase("sdd", 1)
        seq1 = reduce_all().last_seq
        _create_task("sdd_t1", "sdd")
        seq2 = reduce_all().last_seq
        assert seq0 < seq1 < seq2



# ---------------------------------------------------------------------------
# E.9 — Hash chain integrity across 4-phase workflow
# ---------------------------------------------------------------------------

# TestHashChainAcrossPhases removed — near-identical to
# TestFullFourPhaseLifecycle::test_hash_chain_intact_after_full_workflow (both build
# a 4-phase log and assert verify_chain(strict).ok). Chain integrity is owned by test_verify.py.



# ---------------------------------------------------------------------------
# E.10 — DLQ cascade does not cross phase boundaries
# ---------------------------------------------------------------------------

class TestDLQPhaseIsolation:
    def test_dlq_task_in_dev_does_not_cascade_to_review_task(self, tmp_orch):
        """E.10: dev task in DLQ does not trigger cascade for review tasks.
        Review tasks have no cross-phase dependency on dev task IDs."""
        _declare_phases()
        _enter_phase("dev", 2)
        _create_task("dev_tc_001", "dev")
        _create_task("dev_tc_002", "dev")
        # tc_001 goes to DLQ
        append_event("orchestrator", "task_claimed", task_id="dev_tc_001",
                     attempt=1, data={"phase": "dev", "worker_type": "impl",
                                      "worker_id": "w1"})
        append_event("w1", "task_failed", task_id="dev_tc_001", attempt=1,
                     data={"phase": "dev", "reason": "internal_error", "retryable": False})
        append_event("orchestrator", "task_dlq", task_id="dev_tc_001",
                     data={"phase": "dev", "reason": "non_retryable",
                           "last_error": "error"})
        # Simulate phase transition to review (despite dev DLQ — review proceeds)
        _transition_phase("dev", "review", ["c_dev"])
        _enter_phase("review", 3)
        # Review task has no dep on dev_tc_001
        _create_task("review_dev_tc_002", "review",
                     spec="delivery/tc-002-delivery.md")

        state = reduce_all()
        # review_dev_tc_002 has no deps on dev tasks — must be READY
        assert state.tasks["review_dev_tc_002"].status == TaskStatus.READY
        # dev_tc_001 is in DLQ
        assert state.tasks["dev_tc_001"].status == TaskStatus.DLQ
        # dev_tc_002 (no deps) is READY in dev context
        assert state.tasks["dev_tc_002"].status == TaskStatus.READY

    def test_dev_dlq_task_blocks_its_own_downstream(self, tmp_orch):
        """E.10: dev DLQ cascades to other dev tasks that depend on it."""
        _declare_phases()
        _enter_phase("dev", 2)
        _create_task("dev_tc_001", "dev")
        _create_task("dev_tc_002", "dev", deps=["dev_tc_001"])
        append_event("orchestrator", "task_claimed", task_id="dev_tc_001",
                     attempt=1, data={"phase": "dev", "worker_type": "impl",
                                      "worker_id": "w1"})
        append_event("w1", "task_failed", task_id="dev_tc_001", attempt=1,
                     data={"phase": "dev", "reason": "internal_error", "retryable": False})
        append_event("orchestrator", "task_dlq", task_id="dev_tc_001",
                     data={"phase": "dev", "reason": "non_retryable",
                           "last_error": "error"})
        # Orchestrator cascades DLQ to dependent task
        append_event("orchestrator", "task_dlq", task_id="dev_tc_002",
                     data={"phase": "dev", "reason": "cascade_from_dep",
                           "last_error": "dep dev_tc_001 is in dlq"})

        state = reduce_all()
        assert state.tasks["dev_tc_001"].status == TaskStatus.DLQ
        assert state.tasks["dev_tc_002"].status == TaskStatus.DLQ
