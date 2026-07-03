"""Layer Hard Task Namespacing (5-a) — workflow-namespaced task IDs.

The orchestration log is shared across workflows. Un-namespaced task IDs
(sdd_triage, dev_tc_001, review_dev_tc_001, test_dev_tc_001) collide across
workflows: skip-if-exists checks silently suppress work (eternal E21) and a
re-emitted task_created resets the previous workflow's derived task state.
5-a namespaces every orchestrator-created task ID with the workflow slug and
stamps workflow_id into task_created data (explicit attribution — never parse
the ID).
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
AGENTS = ROOT / "dist/.claude/agents"

ORCHESTRATORS = [
    "orchestrator-sdd.md",
    "orchestrator-dev.md",
    "orchestrator-review.md",
    "orchestrator-test.md",
]


def _src(name: str) -> str:
    return (AGENTS / name).read_text(encoding="utf-8")


class TestTaskCreatedCarriesWorkflowId:
    def test_every_task_created_payload_has_workflow_id(self):
        """Pillar A: explicit attribution. Every task_created --data payload in
        every phase orchestrator must stamp workflow_id."""
        for name in ORCHESTRATORS:
            lines = _src(name).splitlines()
            pending, missing = False, []
            for i, line in enumerate(lines, 1):
                if "--event-type task_created" in line:
                    pending = True
                    continue
                if pending and "--data" in line:
                    if '"workflow_id"' not in line:
                        missing.append(i)
                    pending = False
            assert not missing, f"{name}: task_created without workflow_id at lines {missing}"


class TestNamespacedIdConventions:
    def test_sdd_ids_are_namespaced(self):
        src = _src("orchestrator-sdd.md")
        assert "sdd_<workflow_id>_triage" in src
        assert "sdd_{workflow_id}_{domain}_spec-writer" in src
        assert "sdd_{workflow_id}_front" in src
        assert "sdd_{workflow_id}_compliance" in src
        # No un-namespaced emission survives: every `--task-id sdd_...` carries the workflow.
        for line in src.splitlines():
            if "--task-id sdd_" in line:
                assert "workflow_id" in line, f"un-namespaced sdd task-id: {line.strip()}"

    def test_dev_ids_are_namespaced(self):
        src = _src("orchestrator-dev.md")
        assert "dev_<workflow_id>_planning" in src
        assert "dev_<workflow_id>_tc_{n}" in src
        for line in src.splitlines():
            if "--task-id dev_" in line:
                assert "workflow_id" in line, f"un-namespaced dev task-id: {line.strip()}"

    def test_review_and_test_inherit_dev_namespace(self):
        for name, example in [
            ("orchestrator-review.md", "review_dev_etax-unify_tc_001"),
            ("orchestrator-test.md", "test_dev_etax-unify_tc_001"),
        ]:
            src = _src(name)
            assert example in src, f"{name}: convention example not namespaced"
            assert "never parse it from the task ID" in src, name

    def test_backlog_ids_stay_local(self):
        """The planner contract keeps local dev_tc_{n}; the orchestrator applies
        the namespace at task_created (single transformation point)."""
        src = _src("orchestrator-dev.md")
        assert "Backlog IDs are local" in src
        for planner in ("dev/u-be-planner.md", "dev/u-fe-planner.md"):
            psrc = _src(planner)
            assert "do NOT include the workflow in backlog IDs" in psrc, planner


class TestCrossWorkflowScoping:
    def test_sdd_triage_skip_is_workflow_scoped(self):
        src = _src("orchestrator-sdd.md")
        assert "a completed triage from an EARLIER workflow" in src

    def test_repair_cycle_count_scoped_to_workflow(self):
        """R1 regression: repairs from an earlier workflow in the shared log must
        not inflate the current workflow's 2-cycle cap (premature E08)."""
        src = _src("orchestrator-sdd.md")
        assert re.search(r"re\.escape\(wf\)", src), "R1 must scope the repair regex to the workflow"
        assert "must not inflate the cycle count" in src

    def test_improve_gate_invoked_with_workflow_scope(self):
        src = _src("orchestrator-sdd.md")
        assert "ORCH_WORKFLOW_ID=<workflow_id> python3 .claude/skills/phase-sdd-rules/scripts/check_all_improve_reviewers_completed.py" in src

    def test_impl_tasks_filtered_by_fields_not_bare_prefix(self):
        src = _src("orchestrator-dev.md")
        assert 'starts with `dev_tc_`' not in src
        assert 'task.task_type == "impl"' in src

    def test_test_phase_has_session_linkage_guard(self):
        """The test phase had the same silent-suppression hole as review (E21
        shape) with no guard — 5-a adds it."""
        src = _src("orchestrator-test.md")
        assert "Session-linkage guard" in src
        assert "do NOT skip on existence alone" in src
        assert '"dev_task_id":"<dev_task_id>"' in src

    def test_test_return_to_dev_uses_explicit_field(self):
        src = _src("orchestrator-test.md")
        assert "`dev_task_id` field in the test task's `task_created` data" in src
