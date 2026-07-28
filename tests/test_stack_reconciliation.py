"""SGD-002 — the orchestrator recomputes the stack instead of trusting triage.

Triage Step 2.1b narrows the conservative `fullstack` default to `be` when no
front artifact is in scope. That step is prose, and the defect it fixes was
itself a deterministic classifier a prose step failed to reach — so the engine
recomputes the decision from the inputs triage recorded, and the worker's
compliance stops being load-bearing.

Covered here:
  - TestReconcileVerdicts: the narrow transition and every guard around it
  - TestReconcileRewrites: triage.json is patched in place, --dry-run is not
  - TestReconcileIsWired: orchestrator-sdd actually runs it, before project_cost
  - TestCostReflectsReconciliation: the saving is real, in worker count
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST = ROOT / "dist" / ".claude"
RECONCILE = DIST / "scripts" / "reconcile_stack.py"
PROJECT_COST = DIST / "scripts" / "project_cost.py"
SDD = DIST / "agents" / "orchestrator-sdd.md"

# The measured case: domain vocabulary, no term in either signal list.
FSM = "Refatorar a FSM para distinguir os estados terminais e remover answerType e hasThumb"
BACK_SPECS = [
    {"path": "domains/fsm/back/fsm.back.md", "changed_sections": ["schemas"]},
    {"path": "domains/fsm/fsm.spec.md", "changed_sections": ["data_models"]},
]


def _triage(**overrides) -> dict:
    base = {
        "workflow_id": "wf-recon", "trigger": "u-improve", "requirement": FSM,
        "greenfield": False, "stack": "fullstack", "ui_task": True,
        "stack_confidence": "low", "stack_refinement": None,
        "type": "spec_change_required", "mode_hint": "full",
        "affected_specs": BACK_SPECS, "domains": [],
        "estimated_task_contracts": 1,
    }
    base.update(overrides)
    return base


def _run(triage: dict, tmp_path: Path, dry_run: bool = False):
    path = tmp_path / "triage.json"
    path.write_text(json.dumps(triage), encoding="utf-8")
    args = [sys.executable, str(RECONCILE), "--triage", str(path)]
    if dry_run:
        args.append("--dry-run")
    proc = subprocess.run(args, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout), path


class TestReconcileVerdicts:
    def test_evidence_free_fullstack_is_narrowed(self, tmp_path):
        out, _ = _run(_triage(), tmp_path)
        assert out["status"] == "reconciled"
        assert out["from"] == "fullstack" and out["to"] == "be"

    def test_front_artifact_in_scope_stays_fullstack(self, tmp_path):
        specs = BACK_SPECS + [{"path": "front/features/fsm.feature.spec.md"}]
        out, _ = _run(_triage(affected_specs=specs), tmp_path)
        assert out["status"] == "consistent"
        assert out["stack"] == "fullstack"

    def test_ui_signal_in_requirement_stays_fullstack(self, tmp_path):
        out, _ = _run(_triage(requirement="Nova tela de acompanhamento da FSM"), tmp_path)
        assert out["status"] == "consistent"

    def test_human_override_is_never_touched(self, tmp_path):
        """An operator who answered the E99 gate outranks every classifier."""
        out, path = _run(_triage(stack_refinement="human_override"), tmp_path)
        assert out["status"] == "skipped" and out["reason"] == "human_override"
        assert json.loads(path.read_text())["stack"] == "fullstack"

    def test_greenfield_is_skipped(self, tmp_path):
        out, _ = _run(_triage(greenfield=True, affected_specs=[]), tmp_path)
        assert out["status"] == "skipped" and out["reason"] == "greenfield"

    def test_no_affected_specs_is_skipped(self, tmp_path):
        """Absence of evidence must not license a narrowing."""
        out, _ = _run(_triage(affected_specs=[]), tmp_path)
        assert out["status"] == "skipped" and out["reason"] == "no_affected_specs"

    def test_fe_is_never_reconciled(self, tmp_path):
        # `fe` always rests on a real signal — only the default can be a guess.
        out, path = _run(_triage(stack="fe", ui_task=True), tmp_path)
        assert out["status"] == "skipped" and out["reason"] == "stack_not_fullstack"
        assert json.loads(path.read_text())["stack"] == "fe"

    def test_already_be_is_left_alone(self, tmp_path):
        out, _ = _run(_triage(stack="be", ui_task=False), tmp_path)
        assert out["status"] == "skipped"

    def test_copresence_fullstack_survives(self, tmp_path):
        out, _ = _run(_triage(requirement="Checkout page consuming the payment API"),
                      tmp_path)
        assert out["status"] == "consistent"

    def test_running_twice_is_idempotent(self, tmp_path):
        first, path = _run(_triage(), tmp_path)
        assert first["status"] == "reconciled"
        proc = subprocess.run(
            [sys.executable, str(RECONCILE), "--triage", str(path)],
            capture_output=True, text=True)
        assert proc.returncode == 0
        assert json.loads(proc.stdout)["status"] == "skipped"


class TestReconcileRewrites:
    def test_patch_is_written_to_triage_json(self, tmp_path):
        _, path = _run(_triage(), tmp_path)
        t = json.loads(path.read_text(encoding="utf-8"))
        assert t["stack"] == "be"
        assert t["ui_task"] is False
        assert t["stack_refinement"] == "fullstack->be (reconciled)"
        assert t["stack_confidence"] == "high"

    def test_unrelated_fields_survive_the_rewrite(self, tmp_path):
        _, path = _run(_triage(), tmp_path)
        t = json.loads(path.read_text(encoding="utf-8"))
        assert t["mode_hint"] == "full"
        assert t["requirement"] == FSM
        assert len(t["affected_specs"]) == 2

    def test_dry_run_reports_without_writing(self, tmp_path):
        out, path = _run(_triage(), tmp_path, dry_run=True)
        assert out["status"] == "reconciled"
        assert json.loads(path.read_text())["stack"] == "fullstack"

    def test_missing_triage_is_an_error_not_a_confirmation(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, str(RECONCILE), "--triage", str(tmp_path / "nope.json")],
            capture_output=True, text=True)
        assert proc.returncode == 1
        assert json.loads(proc.stderr)["reason"] == "triage_unreadable"

    def test_malformed_triage_is_an_error(self, tmp_path):
        path = tmp_path / "triage.json"
        path.write_text("{not json", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(RECONCILE), "--triage", str(path)],
            capture_output=True, text=True)
        assert proc.returncode == 1


class TestReconcileIsWired:
    def test_orchestrator_runs_it(self):
        text = SDD.read_text(encoding="utf-8")
        assert "reconcile_stack.py" in text

    def test_it_runs_before_the_cost_projection(self):
        """Otherwise the projection counts a front leg that will not be dispatched."""
        text = SDD.read_text(encoding="utf-8")
        assert text.index("reconcile_stack.py") < text.index("project_cost.py")

    def test_a_reconciliation_is_logged(self):
        """Via the canonical mode declaration — not a second, premature one."""
        text = SDD.read_text(encoding="utf-8")
        assert "fullstack->be (reconciled)" in text
        before_step_2b = text[:text.index("--event-type operation_mode_declared")]
        assert "reconcile_stack.py" in before_step_2b, "reconciliation runs first"
        assert before_step_2b.count("--event-type operation_mode_declared") == 0, (
            "effective_mode is not derived yet at reconciliation time"
        )

    def test_corrected_values_are_re_read(self):
        text = SDD.read_text(encoding="utf-8")
        assert "re-read" in text.split("reconcile_stack.py", 1)[1][:800]

    def test_failure_is_not_read_as_confirmation(self):
        text = SDD.read_text(encoding="utf-8")
        assert "never treat it as confirmed" in text

    def test_script_stays_inside_the_copy(self):
        """Self-containment: the classifier is resolved relative to .claude/."""
        src = RECONCILE.read_text(encoding="utf-8")
        assert "dist/" not in src
        assert 'Path(__file__).resolve().parent.parent' in src


class TestCostReflectsReconciliation:
    """The saving must show up where the operator sees it: the worker count."""

    def _project(self, triage: dict, tmp_path: Path) -> dict:
        path = tmp_path / "triage.json"
        path.write_text(json.dumps(triage), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(PROJECT_COST), "--triage", str(path), "--json-only"],
            capture_output=True, text=True, env={**os.environ})
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    def test_front_leg_disappears_from_the_projection(self, tmp_path):
        before = self._project(_triage(), tmp_path)
        _, path = _run(_triage(), tmp_path)
        after = self._project(json.loads(path.read_text()), tmp_path)

        assert before["breakdown"].get("front_leg") == 2
        assert "front_leg" not in after["breakdown"]
        assert after["workers"] == before["workers"] - 2
        assert after["wall_clock_minutes"] < before["wall_clock_minutes"]
