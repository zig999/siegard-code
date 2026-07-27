"""F2 — handoff_allowed derived from the verdict, not the flow shape.

Regression guard for the E08 trap: a back-only SDD flow's terminal validation used
to stay `incremental_back`, which the schema forces to `handoff_allowed: false`, so
generate_handoff_manifest.py blocked and the phase dead-ended at E08 until a human
hand-edited every `_validation/*.yaml` to `true`.

The fix wires `validation_mode` through the spec-validator dispatch: back-only
(`ui_task == false`) terminal validation runs `final_complete` (handoff follows the
verdict), fullstack back-pass stays `incremental_back` (front leg still pending, the
front-pass is the terminal verdict). These are prompt-level contracts, so this gate
asserts the wiring is present in the shipped artifacts — the downstream executable
path (handoff generation) is covered by test_layer_hard_handoff_generation.py.
"""
import re

from conftest import get_dist_dir

dist = get_dist_dir()
ORCH = (dist / "agents" / "orchestrator-sdd.md").read_text(encoding="utf-8")
VALIDATOR = (dist / "agents" / "spec" / "u-spec-validator.md").read_text(encoding="utf-8")
SCHEMA = (dist / "skills" / "u-shared-templates" / "validation-result.schema.yaml").read_text(encoding="utf-8")

# The conditional every spec-validator dispatch (back pass + repair) must carry.
_COND = re.compile(
    r'"validation_mode"\s*:\s*"<incremental_back if triage\.ui_task else final_complete>"'
)


class TestOrchestratorWiring:
    def test_every_back_leg_validator_dispatch_carries_conditional_mode(self):
        """Three dispatch sites, each needing the same F2 conditional:

          1. Step 4 back-pass
          2. repair-cycle (`spec-validator-repair-N`)
          3. R08 stale-verdict revalidation (`spec-validator-revalidate-N`)

        The third is new: a stale INVALID verdict — one written before the specs it
        judges were last edited — is answered by re-running the validator instead
        of dispatching a repair pipeline over findings nobody re-checked. It is a
        back-leg validator like the other two, so a back-only workflow must reach
        `final_complete` here as well or the repaired domain hands off with a
        spurious E08 (the original F2 defect).
        """
        assert len(_COND.findall(ORCH)) == 3, (
            "the Step-4 back-pass, the repair-cycle, and the R08 revalidation "
            "spec-validator dispatches must all set validation_mode conditionally "
            "on triage.ui_task"
        )

    def test_revalidation_dispatch_is_one_of_them(self):
        """Pin the R08 site specifically, so a count change cannot mask its loss."""
        idx = ORCH.index("spec-validator-revalidate-")
        window = ORCH[idx:idx + 900]
        assert _COND.search(window), (
            "the stale-verdict revalidation task must carry the conditional "
            "validation_mode, not a hardcoded one"
        )

    def test_front_pass_validator_is_final_complete(self):
        assert '"validation_mode":"final_complete"' in ORCH, (
            "the front-pass spec-validator is always terminal → final_complete"
        )


class TestValidatorContract:
    def test_validator_derives_handoff_from_verdict_and_mode(self):
        # The derivation must be explicit and gated only by incremental_back.
        assert 'validation.mode != "incremental_back"' in VALIDATOR
        assert "final_complete" in VALIDATOR
        # It must NOT infer the mode from on-disk artifacts.
        assert "never infer it" in VALIDATOR or "do not infer" in VALIDATOR.lower()


class TestSchemaConsistency:
    def test_schema_only_forces_false_in_incremental_back(self):
        # The conditional block still forces false for incremental_back...
        assert "const: incremental_back" in SCHEMA
        # ...and the description reflects the verdict-derived rule (fix F2).
        assert "mode!=incremental_back" in SCHEMA
        assert "final_complete" in SCHEMA
