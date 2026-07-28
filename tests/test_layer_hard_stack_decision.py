"""Layer Hard Stack Decision — fix P0-1 (fe|be|fullstack front/back/both).

The SDD front/back/both decision used to be a single boolean (`ui_task`) derived
by LLM keyword prose with an UNCONDITIONAL backend-suppression rule: any backend
keyword forced ui_task=false even with UI signals present, silently collapsing
fullstack requirements to back-only. This proves the two-part fix without agents:

  - TestStackClassifier: classify_stack.py is deterministic and co-presence aware
    (the canonical P0 case "checkout page + payment API" now resolves to fullstack,
    not back-only), bilingual, and free of substring false positives.
  - TestHandoffStackGuard: generate_handoff_manifest.py fails closed when triage
    declared a front-bearing stack (fullstack|fe) but no front artifacts exist —
    the downstream half that makes a wrongly-skipped front leg loud, not silent.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CLASSIFY = ROOT / "dist/.claude/skills/u-spec-triage-rules/scripts/classify_stack.py"
SCRIPTS = ROOT / "dist/.claude/skills/phase-sdd-rules/scripts"

WID = "wf-test"


def _classify(requirement: str, project_domain: str | None = None,
              affected_specs: list | None = None) -> dict:
    args = [sys.executable, str(CLASSIFY), "--requirement", requirement]
    if project_domain:
        args += ["--project-domain", project_domain]
    if affected_specs is not None:
        args += ["--affected-specs", json.dumps(affected_specs)]
    p = subprocess.run(args, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def _spec(path: str) -> dict:
    return {"path": path, "sections": ["§2"], "changed_sections": ["schemas"],
            "change_summary": "x"}


# The measured case: a backend-only /u-improve described in domain vocabulary.
# No term in it belongs to either signal list, so text alone yields the
# conservative fullstack default.
FSM_REQUIREMENT = ("Refatorar a FSM para distinguir os estados terminais e "
                   "remover answerType e hasThumb")
BACK_ONLY_SPECS = [_spec("domains/fsm/back/fsm.back.md"), _spec("domains/fsm/fsm.spec.md")]


def _gen(project_dir: Path):
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir), "SPECS_DIR": "specs"}
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "generate_handoff_manifest.py"),
         "--workflow-id", WID],
        capture_output=True, text=True, env=env,
    )


def _build(tmp_path: Path, *, frontend=False, triage_stack=None) -> Path:
    specs = tmp_path / "specs"
    auth = specs / "domains" / "auth"
    (auth / "back").mkdir(parents=True)
    (auth / "openapi.yaml").write_text(
        "openapi: 3.0.3\ninfo:\n  title: Auth\n  version: 1.2.0\npaths: {}\n")
    (auth / "auth.spec.md").write_text("# Auth\n\n> Version: 1.2.0\n")
    (auth / "back" / "auth.back.md").write_text("# Auth back\n\n> Version: 1.2.0\n")
    (specs / "error-codes.md").write_text("# Error Codes\n")

    val = specs / "_validation"
    val.mkdir()
    (val / "auth-validation-result.yaml").write_text(
        "domain: auth\nstatus: VALID\nblocking_count: 0\nhandoff_allowed: true\n")

    if frontend:
        front = specs / "front"
        (front / "features").mkdir(parents=True)
        (front / "_flows").mkdir(parents=True)
        (front / "front.md").write_text("# Front\n\n> Version: 1.0.0\n")
        (front / "features" / "login.feature.spec.md").write_text("# login\n")
        (front / "_flows" / "auth.flow.md").write_text("# auth flow\n")

    sess = tmp_path / ".orch" / "sessions" / WID
    sess.mkdir(parents=True)
    triage = {
        "workflow_id": WID, "trigger": "u-spec", "greenfield": True,
        "type": "spec_change_required", "mode_hint": "full",
        "domains": ["auth"], "affected_specs": [],
    }
    if triage_stack is not None:
        triage["stack"] = triage_stack
        triage["ui_task"] = triage_stack in ("fe", "fullstack")
    (sess / "triage.json").write_text(json.dumps(triage))
    return specs


# --------------------------------------------------------------------------- #
# Classifier — deterministic, co-presence aware, bilingual                    #
# --------------------------------------------------------------------------- #
class TestStackClassifier:
    def test_copresence_is_fullstack(self):
        # The canonical P0 case: a backend keyword no longer suppresses the front leg.
        r = _classify("Build a checkout page that consumes the payment API")
        assert r["stack"] == "fullstack"
        assert r["ui_task"] is True
        assert r["ui_signals"] and r["backend_signals"]

    def test_old_suppression_case_no_longer_collapses(self):
        # "endpoint" + "form"/"page" used to force ui_task=false (back-only). Now fullstack.
        r = _classify("Add an endpoint and a form to the user page")
        assert r["stack"] == "fullstack"
        assert r["ui_task"] is True

    def test_ui_only_is_fe(self):
        r = _classify("A settings screen with a sidebar and a modal")
        assert r["stack"] == "fe"
        assert r["ui_task"] is True
        assert not r["backend_signals"]

    def test_backend_only_is_be(self):
        r = _classify("Nightly cron that calls the billing service and writes to the database")
        assert r["stack"] == "be"
        assert r["ui_task"] is False
        assert not r["ui_signals"]

    def test_no_signals_defaults_fullstack(self):
        # Conservative default — never silently drop the front leg.
        r = _classify("Rapid processing of records")
        assert r["stack"] == "fullstack"
        assert r["ui_task"] is True
        assert not r["ui_signals"] and not r["backend_signals"]

    def test_ptbr_copresence_fullstack(self):
        r = _classify("Tela de login com autenticação via API")
        assert r["stack"] == "fullstack"
        assert r["ui_task"] is True

    def test_ptbr_backend_only_is_be(self):
        r = _classify("Webhook de pagamentos gravando no banco de dados")
        assert r["stack"] == "be"
        assert r["ui_task"] is False

    def test_no_substring_false_positive(self):
        # "api" must not match inside "rapid"; "tela" must not match inside "etiqueta".
        r = _classify("Rapid etiqueta processing of records")
        assert "api" not in r["backend_signals"]
        assert "tela" not in r["ui_signals"]

    def test_ui_task_derivation_is_consistent(self):
        for req in (
            "Build a checkout page that consumes the payment API",
            "A settings screen",
            "Nightly cron writing to the database",
            "Rapid processing of records",
            "Tela de login com autenticação via API",
        ):
            r = _classify(req)
            assert r["ui_task"] == (r["stack"] in ("fe", "fullstack"))

    def test_no_duplicate_signals(self):
        # "webhook" appears in both EN and PT lists — output must dedup.
        r = _classify("webhook webhook webhook")
        assert r["backend_signals"].count("webhook") == 1


class TestStackConfidence:
    """Confidence is advisory (fix F5) — it NEVER changes `stack`, it only steers
    a faster human override at the E99 gate."""

    def test_backend_dominant_single_ui_is_low_confidence_fullstack(self):
        # The reported false 'fullstack': one incidental UI word in a backend-heavy
        # requirement. Still classified fullstack (P0-1 safety), but flagged low.
        r = _classify("Nightly cron that writes a report page to the database and calls the billing service")
        assert r["stack"] == "fullstack"          # decision unchanged
        assert r["confidence"] == "low"
        assert "force_backend_only" in r["confidence_hint"]

    def test_clear_copresence_is_high_confidence(self):
        r = _classify("A dashboard screen with forms that consume the auth API and the billing service")
        assert r["stack"] == "fullstack"
        assert r["confidence"] == "high"

    def test_balanced_one_and_one_is_high_confidence(self):
        # The canonical checkout case (1 UI + 1 backend) is a genuine fullstack.
        r = _classify("Build a checkout page that consumes the payment API")
        assert r["stack"] == "fullstack"
        assert r["confidence"] == "high"

    def test_no_signals_default_is_low_confidence(self):
        r = _classify("Rapid processing of records")
        assert r["stack"] == "fullstack"
        assert r["confidence"] == "low"

    def test_single_sided_is_high_confidence(self):
        assert _classify("A settings screen with a sidebar")["confidence"] == "high"
        assert _classify("Nightly cron writing to the database")["confidence"] == "high"


class TestStackNegationAware:
    """SGD-001: a backend signal that appears only inside a negation clause must
    not inflate the stack to a false fullstack (the reported seq-9 gate)."""

    def test_negated_backend_is_dropped(self):
        # The exact reported case: UI work explicitly excluding backend specs.
        r = _classify("Criar componentes de dashboard. NÃO gerar specs de backend nem OpenAPI.")
        assert r["stack"] == "fe"
        assert "backend" not in r["backend_signals"]
        assert r["confidence"] == "high"

    def test_negated_backend_english(self):
        r = _classify("Build the settings screen; do not add any backend service or API.")
        assert r["stack"] == "fe"
        assert r["backend_signals"] == []

    def test_non_negated_backend_still_counts(self):
        # A negation cue in a PREVIOUS clause must not negate a later real signal.
        r = _classify("No layout changes. Add a billing API and a payment service.")
        assert "api" in r["backend_signals"] or "service" in r["backend_signals"]
        assert r["stack"] in ("be", "fullstack")

    def test_genuine_copresence_unaffected(self):
        r = _classify("A checkout page that consumes the payment API")
        assert r["stack"] == "fullstack"


class TestStackStructuralPrecedence:
    """SGD-001: a declared project domain resolves a LOW-confidence decision in
    code instead of escalating — but never overrides a high-confidence one."""

    def test_frontend_domain_resolves_low_confidence_fullstack(self):
        base = _classify("Nightly report page that also hits the billing service and the API")
        assert base["stack"] == "fullstack" and base["confidence"] == "low"
        r = _classify("Nightly report page that also hits the billing service and the API",
                      project_domain="frontend")
        assert r["stack"] == "fe"
        assert r["confidence"] == "high"
        assert r["structural_override"] == "fullstack->fe"

    def test_no_signals_default_resolved_by_domain(self):
        r = _classify("Rapid processing of records", project_domain="frontend")
        assert r["stack"] == "fe"
        assert r["structural_override"] == "fullstack->fe"

    def test_domain_does_not_override_high_confidence(self):
        # A genuine fullstack (high confidence) is NOT silently downgraded — it
        # still surfaces for a human decision.
        r = _classify("A dashboard screen with forms consuming the auth API and billing service",
                      project_domain="frontend")
        assert r["stack"] == "fullstack"
        assert r["structural_override"] is None

    def test_backend_domain_resolves_low_confidence(self):
        r = _classify("Rapid processing of records", project_domain="backend")
        assert r["stack"] == "be"
        assert r["structural_override"] == "fullstack->be"


class TestStackArtifactRefinement:
    """SGD-002: `affected_specs` narrows the conservative text-only default.

    The conservative default (no signals -> fullstack) dispatched spec-front plus
    the front validator into repositories with no front specs at all — 2 workers
    per occurrence — and `/u-improve` sets bypass_e99, so `force_backend_only` was
    never offered in the flow where it fired. Once Step 2.1 has resolved
    `affected_specs`, the structural answer is on hand: every front artifact lives
    under `{SPECS_DIR}/front/`.

    The guards matter as much as the refinement: it must never recreate P0-1 from
    the other side by dropping a front leg that a UI signal justified.
    """

    def test_no_signals_without_affected_specs_still_defaults_fullstack(self):
        # The conservative default is unchanged when there is no structural input.
        r = _classify(FSM_REQUIREMENT)
        assert r["stack"] == "fullstack"
        assert r["artifact_refinement"] is None

    def test_back_only_affected_specs_refine_to_be(self):
        r = _classify(FSM_REQUIREMENT, affected_specs=BACK_ONLY_SPECS)
        assert r["stack"] == "be"
        assert r["ui_task"] is False
        assert r["confidence"] == "high"
        assert r["artifact_refinement"] == "fullstack->be"

    def test_front_artifact_in_scope_blocks_refinement(self):
        for path in ("front/features/login.feature.spec.md",
                     "front/components/badge.component.spec.md",
                     "front/_flows/auth.flow.md",
                     "front/front.md",
                     "front/design-system/tokens.md",
                     "specs/front/design-system-rules.md"):
            r = _classify(FSM_REQUIREMENT,
                          affected_specs=BACK_ONLY_SPECS + [_spec(path)])
            assert r["stack"] == "fullstack", path
            assert r["artifact_refinement"] is None, path

    def test_ui_signal_in_text_always_wins(self):
        # Positive UI evidence is never overturned by the absence of a front spec:
        # the artifact may not exist yet precisely because it is being requested.
        r = _classify("Adicionar uma tela de acompanhamento da FSM",
                      affected_specs=BACK_ONLY_SPECS)
        assert r["ui_task"] is True
        assert r["artifact_refinement"] is None

    def test_entry_without_readable_path_disables_refinement(self):
        # Absence of a path is absence of evidence — it must not license a
        # narrowing, because the unreadable entry could be the front artifact.
        for bad in ({"sections": ["§2"]}, {"path": ""}, {"path": "   "}, 42):
            r = _classify(FSM_REQUIREMENT, affected_specs=[_spec("domains/x/back/x.back.md"), bad])
            assert r["stack"] == "fullstack", bad
            assert r["artifact_refinement"] is None, bad

    def test_empty_affected_specs_does_not_refine(self):
        r = _classify(FSM_REQUIREMENT, affected_specs=[])
        assert r["stack"] == "fullstack"
        assert r["artifact_refinement"] is None

    def test_refinement_never_overturns_a_signalled_decision(self):
        # `fe` and `be` both come from real signals and are left alone; only the
        # evidence-free `fullstack` default is narrowed.
        fe = _classify("Ajustar o componente de badge", affected_specs=BACK_ONLY_SPECS)
        assert fe["stack"] == "fe" and fe["artifact_refinement"] is None
        be = _classify("Ajustar o repositório de atendimentos", affected_specs=BACK_ONLY_SPECS)
        assert be["stack"] == "be" and be["artifact_refinement"] is None

    def test_copresence_fullstack_is_not_narrowed(self):
        # A fullstack backed by BOTH signals is a real decision, not the default.
        r = _classify("Checkout page consuming the payment API",
                      affected_specs=BACK_ONLY_SPECS)
        assert r["stack"] == "fullstack"
        assert r["artifact_refinement"] is None

    def test_declared_frontend_domain_outranks_the_refinement(self):
        # An author's explicit `domain: frontend` is stronger than inferred
        # structure, and it resolves first — the refinement must not undo it.
        r = _classify(FSM_REQUIREMENT, project_domain="frontend",
                      affected_specs=BACK_ONLY_SPECS)
        assert r["stack"] == "fe"
        assert r["structural_override"] == "fullstack->fe"
        assert r["artifact_refinement"] is None

    def test_storefront_domain_is_not_a_front_artifact(self):
        # Exact path-segment match: `storefront` must not read as `front`.
        r = _classify(FSM_REQUIREMENT,
                      affected_specs=[_spec("domains/storefront/back/storefront.back.md")])
        assert r["stack"] == "be"
        assert r["artifact_refinement"] == "fullstack->be"

    def test_plain_string_entries_are_accepted(self):
        r = _classify(FSM_REQUIREMENT, affected_specs=["domains/fsm/back/fsm.back.md"])
        assert r["stack"] == "be"
        r2 = _classify(FSM_REQUIREMENT, affected_specs=["front/features/x.feature.spec.md"])
        assert r2["stack"] == "fullstack"

    def test_windows_separators_are_normalized(self):
        r = _classify(FSM_REQUIREMENT,
                      affected_specs=[_spec("front\\features\\login.feature.spec.md")])
        assert r["stack"] == "fullstack"
        assert r["artifact_refinement"] is None

    def test_malformed_affected_specs_json_is_a_usage_error(self):
        p = subprocess.run(
            [sys.executable, str(CLASSIFY), "--requirement", "x",
             "--affected-specs", "{not json"],
            capture_output=True, text=True)
        assert p.returncode == 1
        assert json.loads(p.stderr)["error"] == "invalid_json"

    def test_refined_stack_passes_the_handoff_guard(self, tmp_path):
        # End to end: the refinement produces exactly the stack the downstream
        # guard demands when no front artifacts exist. Before it, the same repo
        # reached handoff declaring `fullstack` and was blocked — after two
        # workers had already run.
        assert _classify(FSM_REQUIREMENT, affected_specs=BACK_ONLY_SPECS)["stack"] == "be"
        _build(tmp_path, frontend=False, triage_stack="be")
        assert _gen(tmp_path).returncode == 0, _gen(tmp_path).stdout


class TestRefinementIsWiredIntoTheProtocol:
    """A classifier nobody calls fixes nothing — the skill and the orchestrator
    must actually route through it."""

    TRIAGE_SKILL = ROOT / "dist/.claude/skills/u-spec-triage-rules/SKILL.md"
    SDD = ROOT / "dist/.claude/agents/orchestrator-sdd.md"

    def test_skill_declares_the_refinement_step(self):
        text = self.TRIAGE_SKILL.read_text(encoding="utf-8")
        assert "## Step 2.1b — Stack refinement from affected artifacts" in text
        assert "--affected-specs" in text

    def test_refinement_runs_after_affected_specs_are_known(self):
        text = self.TRIAGE_SKILL.read_text(encoding="utf-8")
        assert (text.index("## Step 2.1 — Identify affected specs or domains")
                < text.index("## Step 2.1b — Stack refinement"))

    def test_skipping_the_refinement_is_prohibited(self):
        text = self.TRIAGE_SKILL.read_text(encoding="utf-8")
        assert "stack_refinement_mandatory" in text

    def test_triage_json_carries_the_audit_field(self):
        text = self.TRIAGE_SKILL.read_text(encoding="utf-8")
        assert '"stack_refinement"' in text

    def test_orchestrator_reads_and_logs_the_decision(self):
        """Under bypass_e99 the log is the only surface the decision reaches (P8)."""
        text = self.SDD.read_text(encoding="utf-8")
        assert "`stack_refinement`" in text
        # The canonical operation-mode declaration is the payload carrying
        # bypass_e99 — the reconciliation emit is a separate, narrower event.
        declared = next(chunk for chunk in text.split("--event-type operation_mode_declared")[1:]
                        if "bypass_e99" in chunk.split("```", 1)[0])
        payload = declared.split("```", 1)[0]
        for field in ("stack", "stack_confidence", "stack_refinement"):
            assert f'"{field}"' in payload, field

    def test_human_override_is_not_attributed_to_the_classifier(self):
        text = self.SDD.read_text(encoding="utf-8")
        assert 't["stack_refinement"] = "human_override"' in text


# --------------------------------------------------------------------------- #
# Handoff guard — fail closed on declared-front / missing-front mismatch       #
# --------------------------------------------------------------------------- #
class TestHandoffStackGuard:
    def test_fullstack_without_front_blocks(self, tmp_path):
        specs = _build(tmp_path, frontend=False, triage_stack="fullstack")
        gen = _gen(tmp_path)
        assert gen.returncode != 0, gen.stdout
        out = json.loads(gen.stdout)
        assert out["status"] == "blocked"
        assert out["reason"] == "stack_mismatch_front_expected_but_missing"
        assert not (specs / "handoff-manifest.yaml").exists()

    def test_fe_without_front_blocks(self, tmp_path):
        specs = _build(tmp_path, frontend=False, triage_stack="fe")
        gen = _gen(tmp_path)
        assert gen.returncode != 0
        assert json.loads(gen.stdout)["reason"] == "stack_mismatch_front_expected_but_missing"
        assert not (specs / "handoff-manifest.yaml").exists()

    def test_fullstack_with_front_ok(self, tmp_path):
        specs = _build(tmp_path, frontend=True, triage_stack="fullstack")
        gen = _gen(tmp_path)
        assert gen.returncode == 0, gen.stdout + gen.stderr
        out = json.loads(gen.stdout)
        assert out["status"] == "ok"
        assert out["stack_implied"] == "fullstack"
        assert (specs / "handoff-manifest.yaml").exists()

    def test_be_without_front_ok(self, tmp_path):
        # back-only is a legitimate stack — no front expected, no block.
        specs = _build(tmp_path, frontend=False, triage_stack="be")
        gen = _gen(tmp_path)
        assert gen.returncode == 0, gen.stdout + gen.stderr
        out = json.loads(gen.stdout)
        assert out["status"] == "ok"
        assert out["stack_implied"] == "be"
        assert (specs / "handoff-manifest.yaml").exists()

    def test_legacy_triage_without_stack_not_blocked(self, tmp_path):
        # Back-compat: triage that predates the `stack` field must still generate.
        specs = _build(tmp_path, frontend=False, triage_stack=None)
        gen = _gen(tmp_path)
        assert gen.returncode == 0, gen.stdout + gen.stderr
        assert json.loads(gen.stdout)["status"] == "ok"
        assert (specs / "handoff-manifest.yaml").exists()
