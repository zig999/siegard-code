"""
Tests for dev-phase exit criteria scripts (Level A).

Each test builds a log fixture in-process (via orch_core), then runs the
check script as a subprocess using the same ORCH_PROJECT_DIR.

Scripts under test:
  - check_all_impl_tasks_terminal.py
  - check_all_deliveries_qa_ready.py
  - check_no_open_prohibitions.py
"""
import pytest
import orch_core
from orch_core import append_event, TaskStatus

from .conftest import DEV_SCRIPTS, phase_env, run_check  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dev_phase(wf_id="wf_dev_test"):
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": wf_id,
        "phases": [{"name": "dev", "order": 1, "required": True}],
    })
    append_event("orchestrator", "phase_entered", data={"phase": "dev", "order": 1, "workflow_id": "wf-fix"})


def _impl_task(task_id, deps=None):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "dev", "tier": "standard", "type": "impl",
        "spec": f"spec/{task_id}.md", "deps": deps or [],
    })


def _complete_with_delivery(task_id, project_dir, qa_ready=True, has_violations=False):
    """Complete a task and create a delivery.md artifact."""
    delivery_dir = project_dir / ".orch" / "sessions" / "wf_dev_test" / "delivery"
    delivery_dir.mkdir(parents=True, exist_ok=True)
    delivery_path = delivery_dir / f"{task_id}-delivery.md"

    content = f"# Delivery: {task_id}\n\n"
    content += f"qa_ready: {'true' if qa_ready else 'false'}\n"
    if has_violations:
        content += "prohibition_violations:\n  - something forbidden\n"
    else:
        content += "prohibition_violations: []\n"
    delivery_path.write_text(content)

    rel_path = str(delivery_path.relative_to(project_dir))
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "dev", "worker_type": "impl", "worker_id": f"w_{task_id}",
    })
    append_event("worker", "task_completed", task_id=task_id, attempt=1, data={
        "phase": "dev", "artifacts": [rel_path], "summary": "done",
    })
    return rel_path


def _fail_task(task_id, retryable=False):
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "dev", "worker_type": "impl", "worker_id": f"w_{task_id}",
    })
    append_event("worker", "task_failed", task_id=task_id, attempt=1, data={
        "phase": "dev", "reason": "internal_error", "retryable": retryable,
    })
    if not retryable:
        append_event("orchestrator", "task_dlq", task_id=task_id, data={
            "phase": "dev", "reason": "non_retryable", "last_error": "exit 1",
        })


# ---------------------------------------------------------------------------
# check_all_impl_tasks_terminal.py
# ---------------------------------------------------------------------------

class TestAllImplTasksTerminal:
    def test_no_dev_tasks_is_not_met(self, phase_env):
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["criterion"] == "all_impl_tasks_terminal"
        assert result["met"] is False
        assert result["evidence"]["total"] == 0

    def test_running_task_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        append_event("orchestrator", "task_claimed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_001",
        })
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is False
        non_terminal = [t["task_id"] for t in result["evidence"]["non_terminal"]]
        assert "dev_tc_001" in non_terminal

    def test_pending_task_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is False

    def test_all_completed_is_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _impl_task("dev_tc_002")
        _complete_with_delivery("dev_tc_001", phase_env)
        _complete_with_delivery("dev_tc_002", phase_env)
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["total"] == 2
        assert result["evidence"]["terminal"] == 2

    def test_all_dlq_is_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _fail_task("dev_tc_001", retryable=False)
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is True

    def test_mixed_completed_and_dlq_is_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _impl_task("dev_tc_002")
        _complete_with_delivery("dev_tc_001", phase_env)
        _fail_task("dev_tc_002", retryable=False)
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is True

    def test_one_running_one_completed_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _impl_task("dev_tc_002")
        _complete_with_delivery("dev_tc_001", phase_env)
        append_event("orchestrator", "task_claimed", task_id="dev_tc_002", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_002",
        })
        result = run_check(DEV_SCRIPTS["check_terminal"], phase_env)
        assert result["met"] is False
        non_terminal = [t["task_id"] for t in result["evidence"]["non_terminal"]]
        assert "dev_tc_002" in non_terminal


# ---------------------------------------------------------------------------
# check_all_deliveries_qa_ready.py
# ---------------------------------------------------------------------------

class TestAllDeliveriesQaReady:
    def test_no_completed_tasks_is_not_met(self, phase_env):
        _dev_phase()
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["criterion"] == "all_deliveries_qa_ready"
        assert result["met"] is False
        assert result["evidence"]["total"] == 0

    def test_delivery_file_not_found_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        # Complete but artifact path points nowhere
        append_event("worker", "task_claimed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev",
            "artifacts": ["does/not/exist/dev_tc_001-delivery.md"],
            "summary": "done",
        })
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["not_ready"][0]["reason"] == "file_not_found"

    def test_qa_ready_false_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _complete_with_delivery("dev_tc_001", phase_env, qa_ready=False)
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is False
        # M3: an explicit qa_ready: false is reported with the precise reason
        # "qa_ready_false" (was the generic "qa_ready_not_true") and blocks even if a
        # stray `qa_ready: true` appears elsewhere in the artifact.
        assert any(n["reason"] == "qa_ready_false" for n in result["evidence"]["not_ready"])

    def test_stray_true_does_not_override_explicit_false(self, phase_env):
        """M3 regression: a delivery with a stray `qa_ready: true` (e.g. in an example)
        AND a real `qa_ready: false` must block — false wins over first-match."""
        _dev_phase()
        _impl_task("dev_tc_001")
        delivery_dir = phase_env / ".orch" / "sessions" / "wf_dev_test" / "delivery"
        delivery_dir.mkdir(parents=True, exist_ok=True)
        dpath = delivery_dir / "dev_tc_001-delivery.md"
        dpath.write_text(
            "# Delivery\n\n"
            "Example from the template: `qa_ready: true`\n\n"  # stray, appears first
            "qa_ready: false\n"                                 # the real gate value
        )
        append_event("worker", "task_claimed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_001"})
        append_event("worker", "task_completed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "artifacts": [str(dpath.relative_to(phase_env))], "summary": "done"})
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is False
        assert any(n["reason"] == "qa_ready_false" for n in result["evidence"]["not_ready"])

    def test_qa_ready_true_is_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _complete_with_delivery("dev_tc_001", phase_env, qa_ready=True)
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["ready"] == 1

    def test_all_tasks_qa_ready_is_met(self, phase_env):
        _dev_phase()
        for i in range(1, 4):
            _impl_task(f"dev_tc_{i:03d}")
            _complete_with_delivery(f"dev_tc_{i:03d}", phase_env, qa_ready=True)
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["ready"] == 3

    def test_mixed_ready_and_not_ready_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _impl_task("dev_tc_002")
        _complete_with_delivery("dev_tc_001", phase_env, qa_ready=True)
        _complete_with_delivery("dev_tc_002", phase_env, qa_ready=False)
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["ready"] == 1
        assert len(result["evidence"]["not_ready"]) == 1

    def test_only_delivery_artifacts_are_checked(self, phase_env):
        """Non-delivery artifacts in task_completed are ignored."""
        _dev_phase()
        _impl_task("dev_tc_001")
        append_event("worker", "task_claimed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev",
            "artifacts": ["some/other/artifact.md"],  # no "delivery" in name
            "summary": "done",
        })
        result = run_check(DEV_SCRIPTS["check_qa_ready"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["total"] == 0


# ---------------------------------------------------------------------------
# check_no_open_prohibitions.py
# ---------------------------------------------------------------------------

class TestNoOpenProhibitions:
    def test_no_completed_tasks_is_met(self, phase_env):
        _dev_phase()
        result = run_check(DEV_SCRIPTS["check_prohibitions"], phase_env)
        assert result["criterion"] == "no_open_prohibitions"
        assert result["met"] is True
        assert result["evidence"]["total"] == 0

    def test_delivery_with_no_violations_is_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _complete_with_delivery("dev_tc_001", phase_env, has_violations=False)
        result = run_check(DEV_SCRIPTS["check_prohibitions"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["clean"] == 1

    def test_delivery_with_violations_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _complete_with_delivery("dev_tc_001", phase_env, has_violations=True)
        result = run_check(DEV_SCRIPTS["check_prohibitions"], phase_env)
        assert result["met"] is False
        assert any(
            v["reason"] == "prohibition_violations_present"
            for v in result["evidence"]["violations"]
        )

    def test_one_violation_one_clean_is_not_met(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        _impl_task("dev_tc_002")
        _complete_with_delivery("dev_tc_001", phase_env, has_violations=False)
        _complete_with_delivery("dev_tc_002", phase_env, has_violations=True)
        result = run_check(DEV_SCRIPTS["check_prohibitions"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["clean"] == 1
        assert len(result["evidence"]["violations"]) == 1

    def test_commented_line_does_not_hide_violation(self, phase_env):
        """M1 regression: a comment line between `prohibition_violations:` and the first
        `- ` item must NOT make a real violation read as clean (the prior `(?:\\s*\\n)*`
        tolerated only blank lines → fail-open)."""
        _dev_phase()
        _impl_task("dev_tc_001")
        delivery_dir = phase_env / ".orch" / "sessions" / "wf_dev_test" / "delivery"
        delivery_dir.mkdir(parents=True, exist_ok=True)
        dpath = delivery_dir / "dev_tc_001-delivery.md"
        dpath.write_text(
            "# Delivery\n\nqa_ready: true\n"
            "prohibition_violations:\n"
            "  # reviewer note inserted between key and list\n"
            "  - touched a forbidden module\n"
        )
        append_event("worker", "task_claimed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_001"})
        append_event("worker", "task_completed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "artifacts": [str(dpath.relative_to(phase_env))], "summary": "done"})
        result = run_check(DEV_SCRIPTS["check_prohibitions"], phase_env)
        assert result["met"] is False
        assert any(v["reason"] == "prohibition_violations_present"
                   for v in result["evidence"]["violations"])

    def test_file_not_found_counts_as_violation(self, phase_env):
        _dev_phase()
        _impl_task("dev_tc_001")
        append_event("worker", "task_claimed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev", "worker_type": "impl", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="dev_tc_001", attempt=1, data={
            "phase": "dev",
            "artifacts": ["missing/dev_tc_001-delivery.md"],
            "summary": "done",
        })
        result = run_check(DEV_SCRIPTS["check_prohibitions"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["violations"][0]["reason"] == "file_not_found"


# ---------------------------------------------------------------------------
# check_spec_requirements_covered.py  (Rec A — spec→TC coverage gate)
# ---------------------------------------------------------------------------

import json as _json


class TestSpecRequirementsCovered:
    WF = "wf_dev_test"

    def _spec(self, project_dir, rel, content):
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return rel

    def _tc(self, tc_id, origin, spec_path, bdd_ref=None, objective=""):
        return {
            "task_contract": {
                "id": tc_id, "epic": "EPIC-01", "origin": origin, "type": "feature",
                "priority": "P0", "scope": "backend", "estimate": "S",
                "dependencies": [], "persona_coverage": ["user"], "bdd_ref": bdd_ref,
            },
            "execution_contract": {
                "exec_type": "implementation",
                "objective": objective,
                "input": {"references": [{"path": spec_path, "version": "1.0.0"}]},
            },
        }

    def _backlog(self, project_dir, tcs, triage=None):
        session = project_dir / ".orch" / "sessions" / self.WF
        bdir = session / "backlog"
        bdir.mkdir(parents=True, exist_ok=True)
        bpath = bdir / "backlog.json"
        bpath.write_text(_json.dumps(tcs, indent=2), encoding="utf-8")
        if triage is not None:
            (session / "triage.json").write_text(_json.dumps(triage), encoding="utf-8")
        rel = str(bpath.relative_to(project_dir))
        append_event("orchestrator", "task_created", task_id="dev_planning", data={
            "phase": "dev", "tier": "standard", "type": "planning", "spec": "manifest", "deps": [],
        })
        append_event("worker", "task_claimed", task_id="dev_planning", attempt=1, data={
            "phase": "dev", "worker_type": "planning", "worker_id": "w_plan",
        })
        append_event("worker", "task_completed", task_id="dev_planning", attempt=1, data={
            "phase": "dev", "artifacts": [rel], "summary": "backlog done",
        })
        return rel

    def test_no_backlog_is_met(self, phase_env):
        _dev_phase()
        result = run_check(DEV_SCRIPTS["check_spec_coverage"], phase_env)
        assert result["criterion"] == "spec_requirements_covered"
        assert result["met"] is True
        assert result["evidence"]["reason"] == "no_backlog_found"

    def test_synthesized_backlog_is_met(self, phase_env):
        _dev_phase()
        # improve/synthesized shape: simple task dicts, no execution_contract/origin
        self._backlog(phase_env, [
            {"task_id": "dev_tc_001", "spec": "specs/x.spec.md", "deps": [], "type": "impl"},
        ])
        result = run_check(DEV_SCRIPTS["check_spec_coverage"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["reason"] == "synthesized_backlog_no_contract"

    def test_improve_trigger_is_met(self, phase_env):
        _dev_phase()
        self._spec(phase_env, "specs/d.spec.md", "## UC-01\n## UC-02\n")
        self._backlog(phase_env,
                      [self._tc("TC-01", "UC-01", "specs/d.spec.md")],
                      triage={"trigger": "improve", "planner_required": True})
        result = run_check(DEV_SCRIPTS["check_spec_coverage"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["reason"] == "improve_flow_scoped"

    def test_all_uc_covered_is_met(self, phase_env):
        _dev_phase()
        self._spec(phase_env, "specs/d.spec.md", "## UC-01: login\n## UC-02: logout\n")
        self._backlog(phase_env, [
            self._tc("TC-01", "UC-01", "specs/d.spec.md"),
            self._tc("TC-02", "UC-02", "specs/d.spec.md"),
        ])
        result = run_check(DEV_SCRIPTS["check_spec_coverage"], phase_env)
        assert result["met"] is True
        assert set(result["evidence"]["required_uc"]) == {"UC-01", "UC-02"}
        assert result["evidence"]["uncovered_uc"] == []

    def test_uncovered_uc_blocks(self, phase_env):
        _dev_phase()
        self._spec(phase_env, "specs/d.spec.md", "## UC-01\n## UC-02\n## UC-03\n")
        self._backlog(phase_env, [
            self._tc("TC-01", "UC-01", "specs/d.spec.md"),
            self._tc("TC-02", "UC-02", "specs/d.spec.md"),
        ])
        result = run_check(DEV_SCRIPTS["check_spec_coverage"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["uncovered_uc"] == ["UC-03"]

    def test_uc_covered_via_objective_not_origin(self, phase_env):
        # Lenient coverage: UC-02 folded into another TC's objective, not its origin.
        _dev_phase()
        self._spec(phase_env, "specs/d.spec.md", "## UC-01\n## UC-02\n")
        self._backlog(phase_env, [
            self._tc("TC-01", "UC-01", "specs/d.spec.md",
                     objective="Implement UC-01 and also handle UC-02 in the same flow"),
        ])
        result = run_check(DEV_SCRIPTS["check_spec_coverage"], phase_env)
        assert result["met"] is True

    def test_uncovered_feat_blocks(self, phase_env):
        _dev_phase()
        self._spec(phase_env, "specs/f.feature.spec.md", "# FEAT-01: curation page\n")
        self._backlog(phase_env, [
            self._tc("TC-01", "UC-01", "specs/f.feature.spec.md", bdd_ref=None),
        ])
        result = run_check(DEV_SCRIPTS["check_spec_coverage"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["uncovered_feat"] == ["FEAT-01"]

    def test_feat_covered_via_bdd_ref(self, phase_env):
        _dev_phase()
        self._spec(phase_env, "specs/f.feature.spec.md", "# FEAT-01: curation page\n")
        self._backlog(phase_env, [
            self._tc("TC-01", "UC-01", "specs/f.feature.spec.md", bdd_ref="FEAT-01 §9"),
        ])
        result = run_check(DEV_SCRIPTS["check_spec_coverage"], phase_env)
        assert result["met"] is True

    def test_br_not_referenced_is_informational_not_blocking(self, phase_env):
        _dev_phase()
        self._spec(phase_env, "specs/d.spec.md", "## UC-01\n")
        self._spec(phase_env, "specs/d.back.md", "## BR-01\n## BR-09\n")
        # backlog references both specs and covers UC-01, mentions BR-01 only.
        tc = self._tc("TC-01", "UC-01", "specs/d.spec.md", objective="enforce BR-01")
        tc["execution_contract"]["input"]["references"].append(
            {"path": "specs/d.back.md", "version": "1.0.0"})
        self._backlog(phase_env, [tc])
        result = run_check(DEV_SCRIPTS["check_spec_coverage"], phase_env)
        assert result["met"] is True  # BR gap never blocks
        assert result["evidence"]["br_not_referenced"] == ["BR-09"]
