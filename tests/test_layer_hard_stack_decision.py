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


def _classify(requirement: str) -> dict:
    p = subprocess.run(
        [sys.executable, str(CLASSIFY), "--requirement", requirement],
        capture_output=True, text=True,
    )
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


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
