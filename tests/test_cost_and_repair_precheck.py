"""R08 + R11 — repair on the current condition, and price the run before paying it.

R08. The repair loop dispatched on the *recorded state* of a validation artifact,
never on the *current condition* of the source. Measured: a `spec-back-repair-1`
ran 6.4 minutes and changed zero files — its two blocking issues had already been
resolved on disk by an earlier session that never rewrote the validation artifact.
The resulting commit touched only `_validation/**` and the manifest, nothing under
`domains/**`, which was the entire point of the dispatch.

Re-running each individual issue check is not deterministic (an LLM validator
produced them). Staleness is, and staleness is exactly the case that burned the
time: when the specs are newer than the verdict, the verdict describes a state
that no longer exists, so the answer is one validator run — not a repair pipeline
built on findings nobody re-checked.

R11. The operator only ever learned the price after paying it. The E99 gate did
show `estimated_task_contracts`, but `bypass_e99` is set for every `/u-improve`,
and `/u-improve` is the only usable entry point on a populated repository — so no
estimate was ever surfaced. Measured: 56 min of sdd across 10 workers for a change
of three type-level items.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
IDENTIFY = dist / "skills" / "phase-sdd-rules" / "scripts" / "identify_invalid_domains.py"
PROJECT_COST = dist / "scripts" / "project_cost.py"
SDD = dist / "agents" / "orchestrator-sdd.md"


def _run(script: Path, cwd: Path, *args, specs="specs") -> tuple[int, dict]:
    env = {**os.environ, "ORCH_PROJECT_DIR": str(cwd), "SPECS_DIR": specs}
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )
    out = proc.stdout.strip() or proc.stderr.strip()
    return proc.returncode, json.loads(out)


def _invalid_domain(root: Path, domain: str, verdict_ts: str,
                    specs_newer: bool) -> None:
    """An INVALID domain whose specs are written before or after its verdict."""
    val = root / "specs" / "_validation"
    dom = root / "specs" / "domains" / domain / "back"
    val.mkdir(parents=True, exist_ok=True)
    dom.mkdir(parents=True, exist_ok=True)

    if not specs_newer:
        (dom.parent / f"{domain}.spec.md").write_text("x\n", encoding="utf-8")
        (dom / f"{domain}.back.md").write_text("y\n", encoding="utf-8")

    (val / f"{domain}-validation.md").write_text(
        f"# {domain}\nstatus: INVALID\n", encoding="utf-8")
    (val / f"{domain}-validation-result.yaml").write_text(
        "validation:\n"
        f"  domain: {domain}\n"
        f'  timestamp: "{verdict_ts}"\n'
        "status: INVALID\n"
        "blocking_issues:\n"
        "  - id: ISSUE-001\n"
        "    responsible: u-spec-back\n",
        encoding="utf-8")

    if specs_newer:
        time.sleep(0.02)
        (dom.parent / f"{domain}.spec.md").write_text("x\n", encoding="utf-8")
        (dom / f"{domain}.back.md").write_text("y\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# R08 — stale verdicts revalidate instead of repairing
# ---------------------------------------------------------------------------

class TestStaleVerdictDetection:
    def test_verdict_older_than_its_specs_is_stale(self, tmp_path):
        """The measured case: findings already fixed on disk, artifact not rewritten."""
        _invalid_domain(tmp_path, "alpha", "2026-07-01T10:00:00Z", specs_newer=True)
        rc, out = _run(IDENTIFY, tmp_path)
        assert rc == 0
        assert "alpha" in out["invalid_domains"]
        assert "alpha" in out["stale_verdicts"]
        changed = out["stale_verdicts"]["alpha"]["specs_changed_since"]
        assert "alpha.spec.md" in changed and "alpha.back.md" in changed

    def test_verdict_newer_than_its_specs_is_current(self, tmp_path):
        _invalid_domain(tmp_path, "beta", "2099-01-01T10:00:00Z", specs_newer=False)
        rc, out = _run(IDENTIFY, tmp_path)
        assert "beta" in out["invalid_domains"]
        assert "beta" not in out["stale_verdicts"], (
            "a current verdict must be repaired, not revalidated"
        )

    def test_missing_timestamp_is_never_guessed_stale(self, tmp_path):
        """Without evidence of staleness, behave as before — do not invent it."""
        val = tmp_path / "specs" / "_validation"
        val.mkdir(parents=True)
        (val / "gamma-validation.md").write_text("status: INVALID\n", encoding="utf-8")
        (val / "gamma-validation-result.yaml").write_text(
            "validation:\n  domain: gamma\nstatus: INVALID\n", encoding="utf-8")
        rc, out = _run(IDENTIFY, tmp_path)
        assert "gamma" in out["invalid_domains"]
        assert out["stale_verdicts"] == {}

    def test_valid_domains_are_not_reported(self, tmp_path):
        val = tmp_path / "specs" / "_validation"
        val.mkdir(parents=True)
        (val / "delta-validation.md").write_text("status: VALID\n", encoding="utf-8")
        rc, out = _run(IDENTIFY, tmp_path)
        assert out["invalid_domains"] == []
        assert out["stale_verdicts"] == {}

    def test_existing_output_keys_are_preserved(self, tmp_path):
        """R08 adds a key; it must not change the contract R2 already reads."""
        _invalid_domain(tmp_path, "alpha", "2026-07-01T10:00:00Z", specs_newer=True)
        _, out = _run(IDENTIFY, tmp_path)
        for key in ("invalid_domains", "defect_origins", "out_of_scope_invalid",
                    "scoped"):
            assert key in out

    def test_defect_origin_still_derived_for_stale_domains(self, tmp_path):
        _invalid_domain(tmp_path, "alpha", "2026-07-01T10:00:00Z", specs_newer=True)
        _, out = _run(IDENTIFY, tmp_path)
        assert out["defect_origins"]["alpha"] == "back"


class TestOrchestratorRevalidatesStaleVerdicts:
    def test_step_r2_1_exists(self):
        text = SDD.read_text(encoding="utf-8")
        assert "stale_verdicts" in text
        assert "spec-validator-revalidate-" in text, (
            "a stale verdict must produce a validator task, not a repair pipeline"
        )

    def test_stale_domains_are_removed_from_the_repair_set(self):
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("spec-validator-revalidate-")
        window = text[idx:idx + 900]
        assert "Remove those domains from `invalid_domains`" in window

    def test_revalidation_precedes_repair_dispatch(self):
        text = SDD.read_text(encoding="utf-8")
        assert text.index("Step R2.1") < text.index("Step R3")

    def test_measured_cost_is_recorded_as_rationale(self):
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("Step R2.1")
        window = text[idx:idx + 2200]
        assert "6.4 minutes" in window and "zero" in window


# ---------------------------------------------------------------------------
# R11 — the projection
# ---------------------------------------------------------------------------

def _triage(**over) -> dict:
    base = {
        "workflow_id": "wf", "trigger": "u-improve", "type": "spec_change_required",
        "mode_hint": "full", "stack": "be", "greenfield": False,
        "domains": [], "affected_specs": [],
    }
    base.update(over)
    return base


def _project(tmp_path: Path, triage: dict) -> dict:
    p = tmp_path / "triage.json"
    p.write_text(json.dumps(triage), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(PROJECT_COST), "--triage", str(p), "--json-only"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


class TestProjectionMatchesMeasuredWorkflows:
    """Calibration against the three workflows the model was derived from."""

    def test_workflow_a_full_two_domains(self, tmp_path):
        """Actual: 10 workers, 56.0 min."""
        out = _project(tmp_path, _triage(
            mode_hint="full", stack="be",
            affected_specs=[{"path": "domains/mwo-catalog/back/x.back.md"},
                            {"path": "domains/fsm/back/y.back.md"}],
            domains=["mwo-catalog", "fsm"]))
        assert out["mode"] == "standard"
        assert out["workers"] == 10
        assert abs(out["wall_clock_minutes"] - 56) <= 8

    def test_workflow_c_targeted_three_specs_one_domain(self, tmp_path):
        """Actual: 7 workers, 48.3 min. Fan-out is per affected_specs ENTRY."""
        out = _project(tmp_path, _triage(
            mode_hint="fast-track:minor",
            affected_specs=[{"path": "domains/te/back/te.back.md"},
                            {"path": "domains/te/te.spec.md"},
                            {"path": "domains/te/openapi.yaml"}]))
        assert out["mode"] == "targeted"
        assert out["workers"] == 7
        assert abs(out["wall_clock_minutes"] - 48) <= 8

    def test_concurrency_does_not_divide_the_total(self, tmp_path):
        """Dividing made the estimate 46% low: a batch is turn-synchronous, so a
        stage costs its slowest member and the faster domain simply waits."""
        out = _project(tmp_path, _triage(
            domains=["a", "b"], affected_specs=[{"path": "domains/a/x.md"},
                                                {"path": "domains/b/y.md"}]))
        assert out["wall_clock_minutes"] == out["workers"] * 6
        assert out["concurrency"] == 2
        assert "does not divide" in out["basis"]


class TestProjectionShape:
    def test_implementation_only_projects_the_skip(self, tmp_path):
        out = _project(tmp_path, _triage(type="implementation_only"))
        assert out["mode"] == "skip" and out["workers"] == 1

    def test_fullstack_adds_the_front_leg(self, tmp_path):
        be = _project(tmp_path, _triage(stack="be", domains=["a"]))
        fs = _project(tmp_path, _triage(stack="fullstack", domains=["a"]))
        assert fs["workers"] == be["workers"] + 2
        assert "front_leg" in fs["breakdown"]

    def test_targeted_is_capped_at_one_concurrent(self, tmp_path):
        out = _project(tmp_path, _triage(mode_hint="fast-track:patch",
                                         affected_specs=[{"path": "domains/a/x.md"}]))
        assert out["concurrency"] == 1
        assert "trades parallelism" in out["basis"]

    def test_breakdown_sums_to_the_worker_count(self, tmp_path):
        out = _project(tmp_path, _triage(domains=["a", "b", "c"]))
        assert sum(out["breakdown"].values()) == out["workers"]

    def test_missing_triage_is_an_error_not_a_guess(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, str(PROJECT_COST), "--triage",
             str(tmp_path / "nope.json")],
            capture_output=True, text=True, timeout=30)
        assert proc.returncode == 1
        assert json.loads(proc.stderr)["reason"] == "triage_not_found"


class TestCostIsRecordedUnconditionally:
    def test_orchestrator_emits_cost_projected(self):
        text = SDD.read_text(encoding="utf-8")
        assert "cost_projected" in text
        assert "project_cost.py" in text

    def test_projection_precedes_the_confirmation_gate(self):
        text = SDD.read_text(encoding="utf-8")
        assert text.index("project_cost.py") < text.index(
            "### Step 3 — Human confirmation gate")

    def test_emission_is_not_conditional_on_bypass_e99(self):
        """bypass_e99 suppressing the estimate is the whole defect."""
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("project_cost.py")
        window = text[idx:idx + 1800]
        assert "Unconditional on purpose" in window
        assert "bypass_e99" in window

    def test_event_type_is_declared_in_the_engine(self):
        sys.path.insert(0, str(dist / "lib"))
        import orch_core
        assert orch_core.EventType.COST_PROJECTED.value == "cost_projected"

    def test_event_is_audit_only(self):
        """No reducer handler: emitting a projection must never affect task state."""
        sys.path.insert(0, str(dist / "lib"))
        import orch_core
        assert orch_core.EventType.COST_PROJECTED not in orch_core._HANDLERS

    def test_large_fanout_asks_for_confirmation_even_on_improve(self):
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("### Step 3 — Human confirmation gate")
        window = text[idx:idx + 2400]
        assert "Cost threshold" in window
        assert "workers >= 8" in window
        assert "E99_human_confirmation_required" in window


class TestSpecCodeRatioMetric:
    def test_metric_is_computed_in_on_stop(self):
        src = (dist / "hooks" / "on_stop.py").read_text(encoding="utf-8")
        assert "spec_code_ratio" in src
        assert "_spec_code_ratio" in src

    def test_projection_is_recorded_alongside_the_outcome(self):
        """Estimate and actual must land in the same file or neither calibrates."""
        src = (dist / "hooks" / "on_stop.py").read_text(encoding="utf-8")
        assert "cost_projection" in src
        assert "_last_cost_projection" in src

    def test_ratio_is_best_effort_not_blocking(self):
        src = (dist / "hooks" / "on_stop.py").read_text(encoding="utf-8")
        idx = src.index("def _spec_code_ratio")
        window = src[idx:idx + 2200]
        assert "not a git repository" in window, (
            "a project without git must yield nulls, never break session close"
        )

    def test_ratio_runs_against_a_real_repository(self):
        """Exercise the actual git invocation — a malformed --format silently
        yielded nulls in the first cut of this helper."""
        sys.path.insert(0, str(dist / "lib"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "on_stop_ratio", dist / "hooks" / "on_stop.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out = mod._spec_code_ratio()
        assert out["basis"] != "not a git repository", (
            "the lab repo IS a git repository — a null here means the git "
            "invocation is malformed"
        )
        assert out["commits_counted"] > 0
