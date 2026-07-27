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

    @pytest.mark.parametrize("phase", ["dev", "review", "test"])
    def test_verdict_is_captured_mechanically(self, phase):
        """dev/review/test run independent checkers, so they use the loop idiom.

        sdd is excluded on purpose: its step is order-dependent (manifest
        generation must not run on a blocked precondition), so it checks `$?`
        per stage and stops at the first failure instead of looping.
        """
        text = (dist / "agents" / f"{ORCHESTRATOR_BY_PHASE[phase]}.md").read_text(
            encoding="utf-8")
        assert "GATE_FAILED" in text
        assert "GATE_FAILED: none" in text, (
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
