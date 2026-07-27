"""R01a/R01c — exit-criteria evaluation and recording move out of the LLM.

Production breach: `orchestrator-test` emitted
`phase_exit_criterion_met {"criterion": "all_tests_passed"}` and transitioned to
`done` while the checker returned `met: false` / exit 1. The checker was already
fail-closed; the orchestrator did not honour it. Prose asking an agent to respect
an exit code is not a gate (P7, P11).

Two mechanisms, tested here:
  R01a  evaluate_exit_criteria.py runs the phase's declared checkers and emits
        the per-criterion events itself — all-or-nothing.
  R01c  `_validate_event_data` rejects `phase_exit_criterion_met` carrying a
        non-zero `checker_exit`, so the breach cannot be written at all.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import orch_core
from orch_core import append_event, EventValidationError

SCRIPT = (Path(__file__).resolve().parents[3]
          / "dist" / ".claude" / "scripts" / "evaluate_exit_criteria.py")

WF = "wf_eec"


def _run(project_dir: Path, *args) -> tuple[int, dict]:
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir), "SPECS_DIR": "specs"}
    env.pop("ORCH_WORKFLOW_ID", None)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env, cwd=str(project_dir), timeout=300,
    )
    out = proc.stdout.strip() or proc.stderr.strip()
    return proc.returncode, json.loads(out)


def _green_test_phase(project_dir: Path, task_id="test_dev_tc_001"):
    """A test phase where every declared criterion genuinely passes."""
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": WF,
        "phases": [{"name": "test", "order": 1, "required": True}],
    })
    append_event("orchestrator", "phase_entered",
                 data={"phase": "test", "order": 1, "workflow_id": WF})
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "test", "tier": "standard", "type": "test-run",
        "spec": f"delivery/{task_id}.md", "deps": [], "workflow_id": WF,
    })
    reports = project_dir / ".orch" / "sessions" / WF / "test-reports"
    reports.mkdir(parents=True, exist_ok=True)
    report = reports / f"{task_id}-report.json"
    report.write_text(json.dumps({"task_id": task_id, "result": "passed"}),
                      encoding="utf-8")
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "test", "worker_type": "test-run", "worker_id": f"w_{task_id}",
    })
    append_event("worker", "task_completed", task_id=task_id, attempt=1, data={
        "phase": "test", "artifacts": [str(report)], "summary": "tests passed",
    })
    return task_id


def _criterion_events(project_dir: Path) -> list[dict]:
    log = project_dir / ".orch" / "log.jsonl"
    if not log.is_file():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e["event_type"] == "phase_exit_criterion_met":
            out.append(e)
    return out


# ---------------------------------------------------------------------------
# R01c — the breach cannot be written
# ---------------------------------------------------------------------------

class TestCheckerExitEvidenceIsBinding:
    def test_nonzero_checker_exit_is_rejected(self, tmp_orch):
        """The exact production event: criterion met, checker blocked."""
        with pytest.raises(EventValidationError, match="cannot be met"):
            append_event("orchestrator-test", "phase_exit_criterion_met", data={
                "phase": "test", "criterion": "all_tests_passed",
                "checker": "scripts/check_all_tests_passed.py", "checker_exit": 1,
            })

    def test_zero_checker_exit_is_accepted(self, tmp_orch):
        ev = append_event("orchestrator-test", "phase_exit_criterion_met", data={
            "phase": "test", "criterion": "all_tests_passed", "checker_exit": 0,
        })
        assert ev.seq > 0

    def test_absent_field_stays_valid_for_history(self, tmp_orch):
        """Logs written before this release carry no checker_exit and must keep
        reducing — history is immutable (P1/P3)."""
        ev = append_event("orchestrator-test", "phase_exit_criterion_met",
                          data={"phase": "test", "criterion": "all_tests_passed"})
        assert ev.seq > 0

    def test_non_integer_checker_exit_is_rejected(self, tmp_orch):
        """`"0"` must not pass as evidence of a clean run."""
        with pytest.raises(EventValidationError, match="must be an integer"):
            append_event("orchestrator-test", "phase_exit_criterion_met", data={
                "phase": "test", "criterion": "all_tests_passed", "checker_exit": "0",
            })


# ---------------------------------------------------------------------------
# R01a — the evaluator owns the decision and the recording
# ---------------------------------------------------------------------------

class TestEvaluatorBlocksWhenUnmet:
    def test_empty_phase_blocks_and_emits_nothing(self, tmp_orch):
        rc, out = _run(tmp_orch, "--phase", "test", "--workflow-id", WF)
        assert rc == 3
        assert out["verdict"] == "blocked"
        assert out["failing"]
        assert out["emitted"] == []
        assert _criterion_events(tmp_orch) == [], (
            "a blocked phase must leave no criterion recorded"
        )

    def test_emission_is_all_or_nothing(self, tmp_orch):
        """One failing criterion must not let the passing ones be recorded.

        A partial set leaves the log asserting progress the phase has not made.
        """
        task_id = _green_test_phase(tmp_orch)
        # Break exactly one criterion: report says failed.
        reports = tmp_orch / ".orch" / "sessions" / WF / "test-reports"
        (reports / f"{task_id}-report.json").write_text(
            json.dumps({"task_id": task_id, "result": "failed"}), encoding="utf-8")

        rc, out = _run(tmp_orch, "--phase", "test", "--workflow-id", WF)
        assert rc == 3
        assert "all_tests_passed" in out["failing"]
        assert out["emitted"] == []
        assert _criterion_events(tmp_orch) == []

    def test_blocked_exit_code_is_three(self, tmp_orch):
        """3 = 'blocked by policy'; 1 stays reserved for 'the script broke'."""
        rc, _ = _run(tmp_orch, "--phase", "test", "--workflow-id", WF)
        assert rc == 3


class TestEvaluatorRecordsWhenMet:
    def test_all_met_emits_every_criterion_with_evidence(self, tmp_orch):
        _green_test_phase(tmp_orch)
        rc, out = _run(tmp_orch, "--phase", "test", "--workflow-id", WF)
        assert rc == 0, f"expected all_met, got {out}"
        assert out["verdict"] == "all_met"
        assert out["failing"] == []

        events = _criterion_events(tmp_orch)
        assert {e["data"]["criterion"] for e in events} == set(out["emitted"])
        for e in events:
            assert e["data"]["checker_exit"] == 0
            assert e["data"]["checker"].endswith(".py")
            assert e["data"]["workflow_id"] == WF

    def test_dry_run_evaluates_without_emitting(self, tmp_orch):
        _green_test_phase(tmp_orch)
        rc, out = _run(tmp_orch, "--phase", "test", "--workflow-id", WF, "--dry-run")
        assert rc == 0 and out["verdict"] == "all_met"
        assert out["emitted"] == []
        assert _criterion_events(tmp_orch) == []

    def test_rerun_is_idempotent_in_the_reducer(self, tmp_orch):
        """Re-invocation after a cut-off must be safe (F-05 resumability)."""
        _green_test_phase(tmp_orch)
        rc1, _ = _run(tmp_orch, "--phase", "test", "--workflow-id", WF)
        rc2, _ = _run(tmp_orch, "--phase", "test", "--workflow-id", WF)
        assert (rc1, rc2) == (0, 0)
        state = orch_core.reduce_all()
        met = state.phases["test"].criteria_met
        assert "all_tests_passed" in met


class TestCriteriaComeFromTheManifest:
    @pytest.mark.parametrize("phase", ["sdd", "dev", "review", "test"])
    def test_every_phase_manifest_loads(self, phase):
        sys.path.insert(0, str(SCRIPT.parent))
        import importlib
        mod = importlib.import_module("evaluate_exit_criteria")
        importlib.reload(mod)
        criteria = mod.load_criteria(phase)
        assert criteria, f"phase-{phase}-rules declares no exit criteria"
        for c in criteria:
            assert "id" in c and "script" in c

    def test_applies_to_modes_is_respected(self):
        sys.path.insert(0, str(SCRIPT.parent))
        import importlib
        mod = importlib.import_module("evaluate_exit_criteria")
        importlib.reload(mod)
        c = {"id": "x", "script": "s.py", "applies_to_modes": ["standard"]}
        assert mod._applies(c, "standard") is True
        assert mod._applies(c, "targeted") is False
        # No mode declared: keep the criterion. Dropping a blocking criterion on
        # missing input would silently weaken the gate.
        assert mod._applies(c, None) is True
        assert mod._applies({"id": "y", "script": "s.py"}, "targeted") is True

    def test_missing_checker_script_counts_as_unmet(self, tmp_orch):
        sys.path.insert(0, str(SCRIPT.parent))
        import importlib
        mod = importlib.import_module("evaluate_exit_criteria")
        importlib.reload(mod)
        r = mod.run_checker("test", {"id": "ghost", "script": "scripts/nope.py"},
                            WF, str(tmp_orch))
        assert r["met"] is False and r["exit_code"] == 1
        assert r["evidence"]["error"] == "checker_script_missing"
