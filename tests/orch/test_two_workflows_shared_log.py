"""E2E regression (5-a acceptance): two sequential workflows in ONE shared log,
with coinciding LOCAL TC numbers, produce disjoint task sets.

Eternal incident shape (log seqs 155-160 vs 750-756): workflow ingest-screen
completed dev_tc_001 + review_dev_tc_001; workflow error-taxonomy-unify reused
the same TC numbers — the review orchestrator's skip-if-exists found the OLD
completed review tasks and would have suppressed QA silently. With 5-a IDs are
workflow-namespaced, so the second workflow's tasks never collide with the
first's, the first workflow's derived state is never reset, and per-workflow
reduction separates them cleanly.
"""
import pytest
import orch_core
from orch_core import TaskStatus, append_event, reduce_all, reduce_workflow


def _run_workflow(wf: str, phases=("dev",)) -> None:
    """Simulate one workflow: declare, enter dev, run its namespaced TC + review."""
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": wf,
        "phases": [{"name": ph, "order": i + 1, "required": True}
                   for i, ph in enumerate(phases)],
    })
    append_event("orchestrator", "phase_entered",
                 data={"phase": "dev", "order": 1, "workflow_id": wf})
    dev_id = f"dev_{wf}_tc_001"
    append_event("orchestrator-dev", "task_created", task_id=dev_id, data={
        "phase": "dev", "workflow_id": wf, "tier": "standard", "type": "impl",
        "spec": f".orch/sessions/{wf}/backlog/tc-001.md", "deps": [],
    })
    append_event("orchestrator-dev", "task_claimed", task_id=dev_id, data={
        "phase": "dev", "worker_type": "impl", "worker_id": f"u-be-developer-{dev_id}",
    })
    append_event("worker", "task_completed", task_id=dev_id, data={
        "phase": "dev", "artifacts": [f".orch/sessions/{wf}/delivery/tc-001-delivery.md"],
    })
    review_id = f"review_{dev_id}"
    append_event("orchestrator-review", "task_created", task_id=review_id, data={
        "phase": "dev", "workflow_id": wf, "tier": "standard", "type": "qa",
        "spec": f".orch/sessions/{wf}/delivery/tc-001-delivery.md",
        "dev_task_id": dev_id, "deps": [],
    })
    append_event("orchestrator-review", "task_claimed", task_id=review_id, data={
        "phase": "dev", "worker_type": "qa", "worker_id": f"u-be-qa-{review_id}",
    })
    append_event("worker", "task_completed", task_id=review_id, data={
        "phase": "dev", "artifacts": [f".orch/sessions/{wf}/qa/tc-001-verdict.yaml"],
    })
    # close the workflow's phase so the next workflow can enter its own
    append_event("orchestrator", "phase_exit_approved", data={
        "phase": "dev", "criteria_met": ["all_impl_tasks_terminal"],
        "next_phase": "review", "workflow_id": wf,
    })
    append_event("orchestrator", "phase_transitioned", data={
        "from_phase": "dev", "to_phase": "review", "evidence_seq": 1, "workflow_id": wf,
    })


@pytest.fixture
def two_workflows(tmp_orch):
    _run_workflow("ingest-screen")
    _run_workflow("etax-unify")
    return tmp_orch


class TestTwoWorkflowsSharedLog:
    def test_task_sets_are_disjoint(self, two_workflows):
        """Same LOCAL TC number, zero shared task IDs (audit acceptance)."""
        state = reduce_all()
        assert "dev_ingest-screen_tc_001" in state.tasks
        assert "dev_etax-unify_tc_001" in state.tasks
        assert "review_dev_ingest-screen_tc_001" in state.tasks
        assert "review_dev_etax-unify_tc_001" in state.tasks

    def test_first_workflow_state_never_reset(self, two_workflows):
        """Legacy failure mode: wf2 re-creating dev_tc_001 reset wf1's completed
        task to pending. Namespaced IDs make that impossible."""
        state = reduce_all()
        assert state.tasks["dev_ingest-screen_tc_001"].status == TaskStatus.COMPLETED
        assert state.tasks["review_dev_ingest-screen_tc_001"].status == TaskStatus.COMPLETED

    def test_qa_not_suppressed_for_second_workflow(self, two_workflows):
        """The eternal E21 shape: wf2's review task exists AND is its own —
        linked to wf2's session — not a stale hit on wf1's completed review."""
        state = reduce_all()
        wf2_review = state.tasks["review_dev_etax-unify_tc_001"]
        assert wf2_review.status == TaskStatus.COMPLETED
        assert ".orch/sessions/etax-unify/" in wf2_review.spec

    def test_reduce_workflow_separates_cleanly(self, two_workflows):
        s1 = reduce_workflow("ingest-screen")
        s2 = reduce_workflow("etax-unify")
        assert set(s1.tasks) == {"dev_ingest-screen_tc_001", "review_dev_ingest-screen_tc_001"}
        assert set(s2.tasks) == {"dev_etax-unify_tc_001", "review_dev_etax-unify_tc_001"}

    def test_no_anomalies_and_no_illegal_transitions(self, two_workflows):
        """The whole two-workflow log replays strictly with zero absorbed
        duplicates — collisions are prevented, not just tolerated."""
        state = reduce_all()
        assert state.anomalies == []


# ---------------------------------------------------------------------------
# v2.2.1 review fixes — regressions on top of the same two-workflow shape
# ---------------------------------------------------------------------------

import json
import os
import subprocess
import sys
from pathlib import Path as _P

_ROOT = _P(__file__).resolve().parents[2]
_GATE_IMPL_TERMINAL = _ROOT / "dist/.claude/skills/phase-dev-rules/scripts/check_all_impl_tasks_terminal.py"


def _run_gate(script, project_dir, workflow_id=None):
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir)}
    env.pop("ORCH_WORKFLOW_ID", None)
    if workflow_id:
        env["ORCH_WORKFLOW_ID"] = workflow_id
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                       env=env, cwd=str(project_dir))
    return json.loads(r.stdout or r.stderr)


class TestScopedExitGates:
    """Review finding: exit gates read the GLOBAL state — another workflow's
    non-terminal task blocked this workflow's phase exit forever."""

    def test_foreign_nonterminal_task_does_not_block_scoped_gate(self, two_workflows):
        # wf ingest-screen leaves a second impl task non-terminal (ready).
        append_event("orchestrator-dev", "task_created", task_id="dev_ingest-screen_tc_002", data={
            "phase": "dev", "workflow_id": "ingest-screen", "tier": "standard",
            "type": "impl", "spec": ".orch/sessions/ingest-screen/backlog/tc-002.md", "deps": [],
        })
        # Unscoped (legacy behavior): the foreign ready task blocks.
        out_global = _run_gate(_GATE_IMPL_TERMINAL, two_workflows)
        assert out_global["met"] is False
        # Scoped to etax-unify: only its own (terminal) tasks count.
        out_scoped = _run_gate(_GATE_IMPL_TERMINAL, two_workflows, workflow_id="etax-unify")
        assert out_scoped["met"] is True, out_scoped

    def test_scoped_gate_still_sees_own_legacy_tasks(self, two_workflows):
        # A legacy (un-namespaced, no workflow_id data) non-terminal task must
        # still block: a mid-upgrade workflow owns its legacy tasks.
        append_event("orchestrator-dev", "task_created", task_id="dev_tc_099", data={
            "phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": [],
        })
        out_scoped = _run_gate(_GATE_IMPL_TERMINAL, two_workflows, workflow_id="etax-unify")
        assert out_scoped["met"] is False


class TestScopedPhaseTasksHelper:
    def test_field_scoping_with_legacy_included(self, two_workflows, monkeypatch):
        state = reduce_all()
        monkeypatch.setenv("ORCH_WORKFLOW_ID", "etax-unify")
        scoped = orch_core.scoped_phase_tasks(state, "dev")
        ids = {t.task_id for t in scoped}
        assert "dev_etax-unify_tc_001" in ids
        assert "dev_ingest-screen_tc_001" not in ids

    def test_unset_env_is_global(self, two_workflows, monkeypatch):
        monkeypatch.delenv("ORCH_WORKFLOW_ID", raising=False)
        state = reduce_all()
        ids = {t.task_id for t in orch_core.scoped_phase_tasks(state, "dev")}
        assert {"dev_etax-unify_tc_001", "dev_ingest-screen_tc_001"} <= ids


class TestTaskStateWorkflowField:
    def test_task_created_stamps_workflow_id_field(self, two_workflows):
        state = reduce_all()
        assert state.tasks["dev_etax-unify_tc_001"].workflow_id == "etax-unify"
        # dict roundtrip preserves it
        restored = orch_core.OrchState.from_dict(state.to_dict())
        assert restored.tasks["dev_etax-unify_tc_001"].workflow_id == "etax-unify"


class TestLegacyReuseAttribution:
    """Review finding: the task→workflow binding must not let the FIRST
    task_created own a bare id forever — a legacy log where a later workflow
    legitimately reused the id must attribute the re-creation (and everything
    after it) to the later workflow."""

    def test_recreated_bare_id_rebinds_to_later_workflow(self, tmp_orch):
        # wf1: bare dev_tc_001 created + completed (no data.workflow_id anywhere)
        append_event("orchestrator", "phase_declared", data={
            "workflow_id": "wf1",
            "phases": [{"name": "dev", "order": 1, "required": True}],
        })
        append_event("orchestrator", "phase_entered", data={"phase": "dev", "order": 1, "workflow_id": "wf1"})
        append_event("orchestrator-dev", "task_created", task_id="dev_tc_001", data={
            "phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": [],
        })
        append_event("orchestrator-dev", "task_claimed", task_id="dev_tc_001", data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w1",
        })
        append_event("worker", "task_completed", task_id="dev_tc_001", data={
            "phase": "dev", "artifacts": [],
        })
        append_event("orchestrator", "phase_exit_approved", data={
            "phase": "dev", "criteria_met": ["x"], "next_phase": "review", "workflow_id": "wf1",
        })
        append_event("orchestrator", "phase_transitioned", data={
            "from_phase": "dev", "to_phase": "review", "evidence_seq": 1, "workflow_id": "wf1",
        })
        # wf2: legitimately reuses the bare id (pre-5-a collision shape)
        append_event("orchestrator", "phase_declared", data={
            "workflow_id": "wf2",
            "phases": [{"name": "dev", "order": 1, "required": True}],
        })
        append_event("orchestrator", "phase_entered", data={"phase": "dev", "order": 1, "workflow_id": "wf2"})
        append_event("orchestrator-dev", "task_created", task_id="dev_tc_001", data={
            "phase": "dev", "tier": "standard", "type": "impl", "spec": "s2", "deps": [],
        })

        s2 = orch_core.reduce_workflow("wf2")
        assert "dev_tc_001" in s2.tasks, "re-creation must attribute to wf2"
        assert s2.tasks["dev_tc_001"].spec == "s2"
        s1 = orch_core.reduce_workflow("wf1")
        assert s1.tasks["dev_tc_001"].status == TaskStatus.COMPLETED


class TestMonitorAttributionParity:
    def test_straggler_terminal_attributes_to_binding_workflow(self, two_workflows):
        """monitor._collect_workflow_index must agree with reduce_workflow:
        a terminal event landing after another workflow's phase_declared
        belongs to the task's bound workflow, not the positional one."""
        # wf etax-unify creates+claims a task, then a THIRD workflow declares,
        # then the straggler completion arrives.
        append_event("orchestrator-dev", "task_created", task_id="dev_etax-unify_tc_003", data={
            "phase": "dev", "workflow_id": "etax-unify", "tier": "standard",
            "type": "impl", "spec": "s", "deps": [],
        })
        append_event("orchestrator-dev", "task_claimed", task_id="dev_etax-unify_tc_003", data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w3",
        })
        append_event("orchestrator", "phase_declared", data={
            "workflow_id": "wf3",
            "phases": [{"name": "dev", "order": 1, "required": True}],
        })
        append_event("worker", "task_completed", task_id="dev_etax-unify_tc_003", data={
            "phase": "dev", "artifacts": [],
        })

        scripts_dir = _ROOT / "dist" / ".claude" / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        prev = os.environ.get("ORCH_PROJECT_DIR")
        import monitor
        if prev is None:
            os.environ.pop("ORCH_PROJECT_DIR", None)
        else:
            os.environ["ORCH_PROJECT_DIR"] = prev

        workflows, err = monitor._collect_workflow_index(two_workflows)
        assert err is None
        etax_statuses = workflows["etax-unify"]["task_statuses"]
        assert etax_statuses["dev_etax-unify_tc_003"]["status"] == "completed"
        wf3_statuses = workflows.get("wf3", {}).get("task_statuses", {})
        assert "dev_etax-unify_tc_003" not in wf3_statuses


_GATE_IMPROVE = _ROOT / "dist/.claude/skills/phase-sdd-rules/scripts/check_all_improve_reviewers_completed.py"


class TestImproveGateScoping:
    """Review finding: with ORCH_WORKFLOW_ID unset, the legacy fallback matched
    EVERY workflow's namespaced improve reviewers."""

    def _seed_improve_reviewer(self, wf: str) -> None:
        append_event("orchestrator", "phase_declared", data={
            "workflow_id": wf,
            "phases": [{"name": "sdd", "order": 1, "required": True}],
        })
        append_event("orchestrator", "phase_entered", data={"phase": "sdd", "order": 1, "workflow_id": wf})
        tid = f"sdd_{wf}_improve_0_spec-reviewer"
        append_event("orchestrator-sdd", "task_created", task_id=tid, data={
            "phase": "sdd", "workflow_id": wf, "tier": "standard",
            "type": "spec-reviewer", "spec": "specs/x.md", "deps": [],
        })
        append_event("orchestrator-sdd", "task_claimed", task_id=tid, data={
            "phase": "sdd", "worker_type": "spec-reviewer", "worker_id": f"w-{tid}",
        })
        append_event("worker", "task_completed", task_id=tid, data={
            "phase": "sdd", "artifacts": [],
        })

    def test_unset_env_does_not_match_foreign_namespaced_reviewers(self, tmp_orch):
        self._seed_improve_reviewer("wf1")
        out = _run_gate(_GATE_IMPROVE, tmp_orch)  # no ORCH_WORKFLOW_ID
        assert out["status"] == "blocked"
        assert out["evidence"]["reason"] == "no_improve_reviewer_tasks_found"

    def test_scoped_env_matches_own_reviewers_only(self, tmp_orch):
        self._seed_improve_reviewer("wf1")
        assert _run_gate(_GATE_IMPROVE, tmp_orch, workflow_id="wf1")["status"] == "ok"
        out = _run_gate(_GATE_IMPROVE, tmp_orch, workflow_id="wf2")
        assert out["status"] == "blocked"
