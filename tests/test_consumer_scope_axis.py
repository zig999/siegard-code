"""R13 — mode_hint is a function of compatibility × blast radius.

`mode_hint` had one axis. Anything that modified an existing contract was `full`,
regardless of what it could reach — so a rename of two keys in an injection map
private to one module, every call site in the same repo and updated in the same
commit, paid the same toll as breaking a published DTO.

Measured: that change ran 10 workers / 336,444 tokens / 56 min. With reach
accounted for it is 5 workers — half the tokens. Meanwhile the *larger* change in
the same series (the engine's plan/collect core) ran fast-track. The axis was
inverted in practice.

Root cause, narrower than "the axis is missing": the label vocabulary had no term
for a code-level interface, so `api_contracts` was assigned to changes that touch
no API —

    domains/mwo-catalog/back/mwo-catalog.back.md  ["schemas", "api_contracts"]
    domains/fsm/back/fsm.back.md                  ["api_contracts"]

for named TS interfaces on DI surfaces, a rename of private injection keys, and
three barrel exports. `internal_interfaces` / `module_exports` now exist so reach
is recorded rather than inflated.

The asymmetry that governs every default here: a wrong `public` costs pipeline
time; a wrong `internal` skips cross-domain validation on a published contract.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
CLASSIFY = (dist / "skills" / "u-spec-triage-rules" / "scripts"
            / "classify_consumer_scope.py")
PROJECT_COST = dist / "scripts" / "project_cost.py"
TRIAGE_SKILL = dist / "skills" / "u-spec-triage-rules" / "SKILL.md"
SDD = dist / "agents" / "orchestrator-sdd.md"


def _classify(affected: list[dict]) -> dict:
    proc = subprocess.run(
        [sys.executable, str(CLASSIFY), "--affected-specs", json.dumps(affected)],
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _spec(path: str, *sections: str) -> dict:
    return {"path": path, "changed_sections": list(sections)}


def _module():
    spec = importlib.util.spec_from_file_location("ccs", CLASSIFY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# The classifier
# ---------------------------------------------------------------------------

class TestPublicSignals:
    @pytest.mark.parametrize("section", [
        "endpoints", "api_contracts", "error_codes", "event_types",
        "auth_rules", "schemas", "data_models", "state_contracts",
        "component_props",
    ])
    def test_published_contract_sections_are_public(self, section):
        out = _classify([_spec("domains/a/a.back.md", section)])
        assert out["consumer_scope"] == "public", section

    def test_one_public_section_outweighs_many_internal_ones(self):
        """Reach is a max, not an average — one exposed surface is exposure."""
        out = _classify([
            _spec("domains/a/a.back.md", "internal_interfaces", "module_exports"),
            _spec("domains/b/b.back.md", "endpoints"),
        ])
        assert out["consumer_scope"] == "public"
        assert any("endpoints" in s for s in out["public_signals"])

    def test_openapi_file_forces_public_regardless_of_labels(self):
        """The file IS the published contract; a mislabel cannot hide that."""
        out = _classify([_spec("domains/a/openapi.yaml", "internal_interfaces")])
        assert out["consumer_scope"] == "public"
        assert any("published contract file" in s for s in out["public_signals"])

    def test_data_models_are_always_public(self):
        """Persisted data outlives the change that wrote it."""
        out = _classify([_spec("domains/a/a.back.md", "data_models")])
        assert out["consumer_scope"] == "public"


class TestInternalSignals:
    @pytest.mark.parametrize("section", [
        "internal_interfaces", "module_exports",
        "descriptions", "labels", "examples", "notes", "changelog", "formatting",
    ])
    def test_code_internal_sections_are_internal(self, section):
        out = _classify([_spec("domains/a/a.back.md", section)])
        assert out["consumer_scope"] == "internal", section

    def test_the_measured_case_classifies_internal_when_labelled_correctly(self):
        """The change: named TS interfaces on DI surfaces, a rename of private
        injection map keys, three barrel exports. Nothing reaches an HTTP route,
        an error code or a published event."""
        out = _classify([
            _spec("domains/mwo-catalog/back/mwo-catalog.back.md", "internal_interfaces"),
            _spec("domains/fsm/back/fsm.back.md", "module_exports"),
        ])
        assert out["consumer_scope"] == "internal"
        assert out["public_signals"] == []


class TestConservativeDefaults:
    """A wrong `internal` skips validation on a published contract. The defaults
    are asymmetric on purpose."""

    def test_no_affected_specs_is_public(self):
        """Absence of evidence is not evidence of a small blast radius."""
        assert _classify([])["consumer_scope"] == "public"

    def test_empty_changed_sections_is_public(self):
        out = _classify([_spec("domains/a/a.back.md")])
        assert out["consumer_scope"] == "public"
        assert any("no changed_sections" in s for s in out["public_signals"])

    def test_unrecognized_section_is_public_and_reported(self):
        out = _classify([_spec("domains/a/a.back.md", "brand_new_label")])
        assert out["consumer_scope"] == "public"
        assert out["unrecognized_sections"] == ["brand_new_label"]

    def test_rationale_is_always_present(self):
        for affected in ([], [_spec("domains/a/a.back.md", "endpoints")],
                         [_spec("domains/a/a.back.md", "internal_interfaces")]):
            assert _classify(affected)["rationale"]

    def test_label_sets_are_disjoint(self):
        """An overlap would make the outcome depend on evaluation order."""
        mod = _module()
        assert not (mod.PUBLIC_SECTIONS & mod.INTERNAL_SECTIONS)

    def test_every_structural_label_in_the_skill_is_classified(self):
        """A label the skill documents but the classifier does not know resolves
        to `public` — safe, but it means the label is dead. Catch it here."""
        mod = _module()
        known = mod.PUBLIC_SECTIONS | mod.INTERNAL_SECTIONS
        text = TRIAGE_SKILL.read_text(encoding="utf-8")
        block = text[text.index("Structural labels"):text.index("Text-only labels")]
        documented = {
            line.split("—")[0].strip()
            for line in block.splitlines()
            if "—" in line and line.startswith("  ")
        }
        documented = {d for d in documented if d and " " not in d}
        missing = sorted(documented - known)
        assert not missing, f"labels documented but unclassified: {missing}"


class TestUsageErrors:
    def test_missing_triage_file_errors(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, str(CLASSIFY), "--triage", str(tmp_path / "nope.json")],
            capture_output=True, text=True, timeout=30)
        assert proc.returncode == 1
        assert json.loads(proc.stderr)["reason"] == "triage_not_found"

    def test_non_array_affected_specs_errors(self):
        proc = subprocess.run(
            [sys.executable, str(CLASSIFY), "--affected-specs", '{"not": "a list"}'],
            capture_output=True, text=True, timeout=30)
        assert proc.returncode == 1

    def test_reads_a_real_triage_json(self, tmp_path):
        t = tmp_path / "triage.json"
        t.write_text(json.dumps({
            "affected_specs": [_spec("domains/a/a.back.md", "internal_interfaces")]
        }), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(CLASSIFY), "--triage", str(t)],
            capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0
        assert json.loads(proc.stdout)["consumer_scope"] == "internal"


# ---------------------------------------------------------------------------
# The composite axis, and what it saves
# ---------------------------------------------------------------------------

def _project(tmp_path: Path, triage: dict) -> dict:
    p = tmp_path / "triage.json"
    p.write_text(json.dumps(triage), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(PROJECT_COST), "--triage", str(p), "--json-only"],
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


_MEASURED_TRIAGE = {
    "trigger": "u-improve", "type": "spec_change_required", "stack": "be",
    "greenfield": False, "domains": [],
    "affected_specs": [
        {"path": "domains/mwo-catalog/back/mwo-catalog.back.md",
         "changed_sections": ["internal_interfaces"]},
        {"path": "domains/fsm/back/fsm.back.md",
         "changed_sections": ["module_exports"]},
    ],
}


class TestTheSavingIsReal:
    def test_reach_downgrade_halves_the_worker_count(self, tmp_path):
        """Measured: 10 workers / 336,444 tokens / 56 min. Tokens are charged per
        worker (~34k each here), so halving workers halves the token bill."""
        full = _project(tmp_path, {**_MEASURED_TRIAGE, "mode_hint": "full"})
        downgraded = _project(tmp_path, {**_MEASURED_TRIAGE,
                                         "mode_hint": "fast-track:minor",
                                         "consumer_scope": "internal"})
        assert full["workers"] == 10, "the measured baseline"
        assert downgraded["workers"] == 5
        assert downgraded["mode"] == "targeted"

    def test_projection_reports_the_scope(self, tmp_path):
        """A suspiciously cheap projection must say why it is cheap."""
        out = _project(tmp_path, {**_MEASURED_TRIAGE,
                                  "mode_hint": "fast-track:minor",
                                  "consumer_scope": "internal"})
        assert out["consumer_scope"] == "internal"
        assert "consumer_scope=internal" in out["basis"]

    def test_public_scope_keeps_the_full_pipeline(self, tmp_path):
        out = _project(tmp_path, {**_MEASURED_TRIAGE, "mode_hint": "full",
                                  "consumer_scope": "public"})
        assert out["mode"] == "standard" and out["workers"] == 10


def _consumer_scope_invocation() -> str:
    """The shell command the skill tells triage to run — not the prose mentions."""
    text = TRIAGE_SKILL.read_text(encoding="utf-8")
    marker = ("```bash\npython3 .claude/skills/u-spec-triage-rules/scripts/"
              "classify_consumer_scope.py")
    assert marker in text, "the skill must invoke the classifier in a bash block"
    return text.split(marker, 1)[1].split("```", 1)[0]


class TestTriageContract:
    def test_skill_runs_the_classifier(self):
        text = TRIAGE_SKILL.read_text(encoding="utf-8")
        assert "classify_consumer_scope.py" in text

    def test_mode_hint_rule_names_the_second_axis(self):
        text = TRIAGE_SKILL.read_text(encoding="utf-8")
        assert "consumer_scope == internal" in text
        assert "consumer_scope == public" in text

    def test_classification_is_declared_deterministic(self):
        """Same invariant as `stack` — hand-classification is prohibited."""
        text = TRIAGE_SKILL.read_text(encoding="utf-8")
        assert "consumer_scope_deterministic" in text
        assert "Hand-classification is prohibited" in text

    def test_conservative_invariant_is_declared(self):
        text = TRIAGE_SKILL.read_text(encoding="utf-8")
        assert "consumer_scope_conservative" in text

    def test_new_labels_are_documented_with_disambiguation(self):
        text = TRIAGE_SKILL.read_text(encoding="utf-8")
        assert "internal_interfaces" in text and "module_exports" in text
        assert "NOT `api_contracts`" in text, (
            "the mislabel is the root cause — the guidance must name it"
        )

    def test_triage_json_carries_the_field(self):
        text = TRIAGE_SKILL.read_text(encoding="utf-8")
        assert '"consumer_scope": "public | internal"' in text
        assert "consumer_scope_rationale" in text

    def test_greenfield_is_always_public(self):
        text = TRIAGE_SKILL.read_text(encoding="utf-8")
        assert "consumer_scope: public` — no structural diff is possible" in text

    def test_terminal_event_records_the_scope(self):
        """The classification must be auditable from the log alone."""
        text = TRIAGE_SKILL.read_text(encoding="utf-8")
        assert '"consumer_scope":"{consumer_scope}"' in text

    def test_classifier_is_fed_the_in_memory_array_not_triage_json(self):
        """The step must not read triage.json — that file is written in Step 3.

        Reading it here fails on a new workflow (`triage_not_found`, exit 1) and
        returns the PREVIOUS run's affected_specs on a resumed one. Either way the
        deterministic classification silently does not happen and `consumer_scope`
        falls back to the hand-classification the skill prohibits.
        """
        invocation = _consumer_scope_invocation()
        assert "--affected-specs" in invocation
        assert "--triage" not in invocation, (
            "triage.json does not exist yet at this point in the skill"
        )

    def test_labels_are_assigned_before_the_classifier_runs(self):
        """The labels are the classifier's entire input, so they must come first."""
        text = TRIAGE_SKILL.read_text(encoding="utf-8")
        assign = text.index("**Step 2.5a — assign `changed_sections` per spec.**")
        classify = text.index("**Step 2.5b — classify the blast radius")
        assert assign < classify
        assert assign < text.index("```bash\npython3 .claude/skills/u-spec-triage-rules"
                                   "/scripts/classify_consumer_scope.py")


class TestOrchestratorSurfacesAndAllowsOverride:
    def test_orchestrator_reads_the_field(self):
        text = SDD.read_text(encoding="utf-8")
        assert "- `consumer_scope`:" in text

    def test_override_action_exists(self):
        text = SDD.read_text(encoding="utf-8")
        assert "force_full_pipeline" in text
        assert "Reach correction" in text

    def test_override_is_offered_in_the_gate_options(self):
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("Options: confirm_proceed")
        assert "force_full_pipeline" in text[idx:idx + 200]

    def test_override_rewrites_triage_to_public_and_full(self):
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("Reach correction")
        window = text[idx:idx + 1600]
        assert '"consumer_scope"] = "public"' in window
        assert '"mode_hint"] = "full"' in window

    def test_downgrade_is_disclosed_even_when_e99_is_bypassed(self):
        """A downgrade REDUCES workers, so it can never trip the R11b cost
        threshold — without its own disclosure it would be chosen silently."""
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("Reach-downgrade disclosure")
        window = text[idx:idx + 2200]
        assert "bypass_e99" in text[max(0, idx - 600):idx]
        assert "force_full_pipeline" in window
        assert "SKIPPED" in window

    def test_what_the_downgrade_gives_up_is_stated(self):
        """Silently trading validation for speed is the mirror of the defect R11
        fixes — cost invisible before the decision, now correctness invisible."""
        text = TRIAGE_SKILL.read_text(encoding="utf-8")
        idx = text.index("What the downgrade gives up")
        window = text[idx:idx + 1400]
        assert "spec-validator" in window and "spec-compliance" in window
        assert "not symmetric" in window
