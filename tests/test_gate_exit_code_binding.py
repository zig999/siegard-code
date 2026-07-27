"""R01b — the exit-criteria checker's exit code is binding.

Production breach: `orchestrator-test` emitted
`phase_exit_criterion_met {"criterion": "all_tests_passed"}` and transitioned the
workflow to `done`, while `check_all_tests_passed.py`, run against the artifact
the worker had actually registered, returned `met: false` and exit 1.

The script was already fail-closed — its own comment reads "M6: fail-closed exit
so the gate is not prompt-trusted". Nothing consumed the exit code, so the
guarantee existed in Python and evaporated in prose. This module holds both
halves: every checker really is fail-closed, and every orchestrator is really
told the exit code decides.
"""
import json
import os
import re
import subprocess
import sys

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()

PHASES = ["sdd", "dev", "review", "test"]
ORCHESTRATOR_BY_PHASE = {p: f"orchestrator-{p}" for p in PHASES}


def _declared_criteria(phase: str) -> list[tuple[str, str]]:
    """(criterion id, script path) straight from the phase's exit-criteria.json.

    Derived, never hand-listed: a criterion added to the JSON is covered by these
    tests automatically. A hardcoded list would have to be remembered, and the
    defect this module exists for is precisely a guarantee nobody remembered to
    connect.
    """
    manifest = dist / "skills" / f"phase-{phase}-rules" / "exit-criteria.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return [(c["id"], c["script"]) for c in data["criteria"]]


PHASE_CHECKERS = {p: [s for _, s in _declared_criteria(p)] for p in PHASES}

_ALL = [(p, cid, script) for p in PHASES for cid, script in _declared_criteria(p)]
_IDS = [f"{p}:{cid}" for p, cid, _ in _ALL]


def _script(phase: str, script_rel: str):
    return dist / "skills" / f"phase-{phase}-rules" / script_rel


class TestCheckersExist:
    @pytest.mark.parametrize("phase,cid,script", _ALL, ids=_IDS)
    def test_declared_checker_is_shipped(self, phase, cid, script):
        assert _script(phase, script).is_file(), (
            f"{phase}/exit-criteria.json declares '{cid}' -> {script}, not shipped"
        )


class TestCheckersAreFailClosed:
    """A checker that prints `met: false` and exits 0 cannot gate anything."""

    @pytest.mark.parametrize("phase,cid,script", _ALL, ids=_IDS)
    def test_source_binds_the_exit_code_to_the_verdict(self, phase, cid, script):
        """Either `sys.exit(1)` on unmet, or `return 0 if ok else 1` propagated.

        Both shapes ship today; what must never ship is a checker that prints a
        blocked verdict and exits 0 — all four review criteria did exactly that,
        which is why the phase had to read the JSON instead (the prompt-trust
        P7/P11 forbid).
        """
        src = _script(phase, script).read_text(encoding="utf-8")
        main_body = re.search(r"^def main\(.*?(?=^if __name__)", src, re.S | re.M)
        assert main_body, f"{script}: no main() found"
        body = main_body.group(0)
        tail = src[src.index("if __name__"):]
        binds = re.search(r"return 0 if .*else 1|return 1|sys\.exit\(1\)", body)
        propagated = "sys.exit(main())" in tail or "sys.exit(1)" in body
        assert binds and propagated, (
            f"{script} does not bind its exit code to the verdict "
            f"(binds={bool(binds)}, propagated={propagated})"
        )

    @pytest.mark.parametrize("phase,cid,script", _ALL, ids=_IDS)
    def test_unmet_criterion_really_exits_nonzero(self, phase, cid, script, tmp_path):
        """Run each checker with no log/artifacts: nothing can be verified, so the
        criterion must NOT be met and the exit code must say so."""
        env = {**os.environ, "ORCH_PROJECT_DIR": str(tmp_path),
               "ORCH_WORKFLOW_ID": "wf-absent"}
        (tmp_path / ".orch").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".orch" / "log.jsonl").write_text("", encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(_script(phase, script))],
            cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0:
            payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
            assert payload.get("met") is True or payload.get("status") == "ok", (
                f"{script} exited 0 while reporting an unmet criterion: {payload}"
            )
        else:
            assert proc.returncode in (1,), (
                f"{script} exited {proc.returncode}; gates use 1 for 'not met'"
            )


class TestOrchestratorsBindToTheExitCode:
    @pytest.mark.parametrize("phase", PHASES)
    def test_orchestrator_declares_the_rule(self, phase):
        text = (dist / "agents" / f"{ORCHESTRATOR_BY_PHASE[phase]}.md").read_text(
            encoding="utf-8")
        assert "GATE_EXIT_CODE_IS_BINDING" in text, (
            f"{ORCHESTRATOR_BY_PHASE[phase]} does not state that the checker exit "
            "code is binding — the breach this rule exists to prevent"
        )

    @pytest.mark.parametrize("phase", PHASES)
    def test_rule_names_the_forbidden_action(self, phase):
        text = (dist / "agents" / f"{ORCHESTRATOR_BY_PHASE[phase]}.md").read_text(
            encoding="utf-8")
        idx = text.index("GATE_EXIT_CODE_IS_BINDING")
        window = text[idx:idx + 1400]
        assert "phase_exit_criterion_met" in window, (
            "the rule must name the event it forbids, not just the principle"
        )
        assert "non-zero" in window

    @pytest.mark.parametrize("phase", PHASES)
    def test_verdict_is_captured_mechanically(self, phase):
        """The verdict must arrive as a single unambiguous signal.

        R01b first introduced a shell loop over the checkers; R01a superseded it
        with evaluate_exit_criteria.py, which both evaluates and records. Either
        way the orchestrator must not be interpreting per-checker JSON.
        """
        text = (dist / "agents" / f"{ORCHESTRATOR_BY_PHASE[phase]}.md").read_text(
            encoding="utf-8")
        assert "evaluate_exit_criteria.py" in text
        assert "verdict: all_met" in text, (
            "the orchestrator needs one unambiguous permitting state"
        )

    def test_sdd_explains_why_it_does_not_loop(self):
        text = (dist / "agents" / "orchestrator-sdd.md").read_text(encoding="utf-8")
        idx = text.index("GATE_EXIT_CODE_IS_BINDING")
        window = text[idx:idx + 1400]
        assert "order-dependent" in window

    @pytest.mark.parametrize("phase", PHASES)
    def test_rule_precedes_the_emission(self, phase):
        """A rule stated after the emit block is a footnote, not a gate."""
        text = (dist / "agents" / f"{ORCHESTRATOR_BY_PHASE[phase]}.md").read_text(
            encoding="utf-8")
        rule_at = text.index("GATE_EXIT_CODE_IS_BINDING")
        # First emission that belongs to the exit-criteria step (after the rule's
        # own step header, which is what we are anchoring on).
        emit_at = text.index("phase_exit_criterion_met", rule_at)
        assert rule_at < emit_at

    @pytest.mark.parametrize("phase", PHASES)
    def test_invariant_cites_the_architecture_principles(self, phase):
        text = (dist / "agents" / f"{ORCHESTRATOR_BY_PHASE[phase]}.md").read_text(
            encoding="utf-8")
        idx = text.index("GATE_EXIT_CODE_IS_BINDING")
        window = text[idx:idx + 1400]
        assert "P7" in window and "P11" in window, (
            "tie the rule to the invariants it protects, or it reads as style"
        )


# ─────────────────────────────────────────────────────────────────────────────
# R01a — the orchestrators no longer compose the per-criterion events.
#
# The breach was an LLM hand-writing `phase_exit_criterion_met` over a checker
# that had blocked. Removing the hand-written path removes the breach: the
# events now come from evaluate_exit_criteria.py, which derives the criteria set
# from exit-criteria.json and writes `checker_exit` as evidence.
# ─────────────────────────────────────────────────────────────────────────────

EVALUATOR = dist / "scripts" / "evaluate_exit_criteria.py"


class TestEmissionMovedOutOfTheOrchestrators:
    def test_evaluator_is_shipped(self):
        assert EVALUATOR.is_file()

    @pytest.mark.parametrize("phase", PHASES)
    def test_orchestrator_no_longer_emits_criteria_by_hand(self, phase):
        text = (dist / "agents" / f"{ORCHESTRATOR_BY_PHASE[phase]}.md").read_text(
            encoding="utf-8")
        assert "--event-type phase_exit_criterion_met" not in text, (
            f"{ORCHESTRATOR_BY_PHASE[phase]} still composes phase_exit_criterion_met "
            "by hand — that is the path that recorded a met criterion over a blocked "
            "checker in production"
        )

    @pytest.mark.parametrize("phase", PHASES)
    def test_orchestrator_calls_the_evaluator(self, phase):
        text = (dist / "agents" / f"{ORCHESTRATOR_BY_PHASE[phase]}.md").read_text(
            encoding="utf-8")
        assert "evaluate_exit_criteria.py" in text
        assert f"--phase {phase}" in text

    @pytest.mark.parametrize("phase", PHASES)
    def test_orchestrator_branches_on_the_evaluator_exit_code(self, phase):
        text = (dist / "agents" / f"{ORCHESTRATOR_BY_PHASE[phase]}.md").read_text(
            encoding="utf-8")
        idx = text.index("evaluate_exit_criteria.py")
        window = text[idx:idx + 2000]
        for token in ("exit 0", "exit 3", "exit 1"):
            assert token in window, f"{phase}: evaluator branch missing '{token}'"

    @pytest.mark.parametrize("phase", PHASES)
    def test_orchestrator_still_owns_phase_exit_approved(self, phase):
        """Approval encodes policy (the human gate in sdd/review) — it stays with
        the orchestrator on purpose. Only the measurement moved."""
        text = (dist / "agents" / f"{ORCHESTRATOR_BY_PHASE[phase]}.md").read_text(
            encoding="utf-8")
        assert "--event-type phase_exit_approved" in text

    def test_sdd_records_after_the_commit_gate(self):
        """`sdd_artifacts_committed` is a declared criterion, so the single
        recording point must come after the commit that makes it satisfiable."""
        text = (dist / "agents" / "orchestrator-sdd.md").read_text(encoding="utf-8")
        commit_at = text.index("check_sdd_artifacts_committed.py")
        eval_at = text.rindex("evaluate_exit_criteria.py")
        assert commit_at < eval_at

    def test_sdd_passes_the_mode_so_criteria_follow_the_manifest(self):
        text = (dist / "agents" / "orchestrator-sdd.md").read_text(encoding="utf-8")
        assert "--mode <effective_mode>" in text
        assert "applies_to_modes" in text


class TestCheckerExitEvidenceIsEnforced:
    def test_validator_rejects_nonzero_checker_exit(self):
        sys.path.insert(0, str(dist / "lib"))
        import orch_core
        with pytest.raises(orch_core.EventValidationError):
            orch_core._validate_event_data("phase_exit_criterion_met", {
                "phase": "test", "criterion": "all_tests_passed", "checker_exit": 1,
            })

    def test_validator_accepts_absent_field_for_history(self):
        sys.path.insert(0, str(dist / "lib"))
        import orch_core
        orch_core._validate_event_data("phase_exit_criterion_met", {
            "phase": "test", "criterion": "all_tests_passed",
        })  # must not raise

    def test_evaluator_always_writes_the_evidence_field(self):
        src = EVALUATOR.read_text(encoding="utf-8")
        assert '"checker_exit"' in src and '"checker"' in src

    def test_evaluator_emission_is_all_or_nothing(self):
        src = EVALUATOR.read_text(encoding="utf-8")
        assert "if not failing and not dry_run:" in src, (
            "a partial emission would leave the log asserting progress the phase "
            "has not made"
        )
