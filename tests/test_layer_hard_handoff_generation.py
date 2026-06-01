"""Layer Hard Handoff Generation — generate_handoff_manifest.py (fix F1).

The SDD exit gate required an approved handoff-manifest.yaml that no pipeline
worker produced, so the phase dead-ended at E08. generate_handoff_manifest.py
assembles the manifest deterministically from validated specs + triage.json.

These tests prove F1 without live agents:
  - Level 1: the generator writes a manifest that minimal_yaml parses and
    validate.py (13 rules + sha256) accepts; frontend package is included iff
    front specs exist (back-only -> stack=be).
  - Level 2: the exact Step-6 script sequence now reaches all-ok (the path that
    previously dead-ended at E08).
  - Fail-closed: a compliance block / missing domains yields blocked, no manifest.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "dist/.claude/skills/phase-sdd-rules/scripts"
LIB = ROOT / "dist/.claude/lib"
VALIDATE = ROOT / "dist/.claude/skills/u-handoff-validator/validate.py"

sys.path.insert(0, str(LIB))
from minimal_yaml import load as yaml_load  # noqa: E402

WID = "wf-test"


def _run(script: str, project_dir: Path, *args: str):
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir), "SPECS_DIR": "specs"}
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, env=env,
    )


def _validate(manifest_path: Path, project_dir: Path):
    return subprocess.run(
        [sys.executable, str(VALIDATE), "--manifest", str(manifest_path),
         "--specs-dir", str(project_dir), "--caller", "u-spec-orchestrator"],
        capture_output=True, text=True,
    )


def _build_specs(tmp_path: Path, *, frontend=False, compliance_block=False, invalid=False) -> Path:
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
    status = "INVALID" if invalid else "VALID"
    allowed = "false" if invalid else "true"
    (val / "auth-validation-result.yaml").write_text(
        f"domain: auth\nstatus: {status}\nblocking_count: 0\nhandoff_allowed: {allowed}\n")
    if compliance_block:
        (val / "auth-compliance.yaml").write_text("domain: auth\nverdict: non_compliant\n")

    if frontend:
        front = specs / "front"
        (front / "features").mkdir(parents=True)
        (front / "_flows").mkdir(parents=True)
        (front / "front.md").write_text("# Front\n\n> Version: 1.0.0\n")
        (front / "features" / "login.feature.spec.md").write_text("# login\n")
        (front / "_flows" / "auth.flow.md").write_text("# auth flow\n")

    sess = tmp_path / ".orch" / "sessions" / WID
    sess.mkdir(parents=True)
    (sess / "triage.json").write_text(json.dumps({
        "workflow_id": WID, "trigger": "u-spec", "greenfield": True,
        "type": "spec_change_required", "mode_hint": "full",
        "domains": ["auth"], "affected_specs": [],
    }))
    return specs


# --------------------------------------------------------------------------- #
# Level 1 — generator unit                                                    #
# --------------------------------------------------------------------------- #
class TestGeneratorUnit:
    def test_backonly_manifest_is_valid(self, tmp_path):
        specs = _build_specs(tmp_path)
        gen = _run("generate_handoff_manifest.py", tmp_path, "--workflow-id", WID)
        assert gen.returncode == 0, gen.stdout + gen.stderr
        out = json.loads(gen.stdout)
        assert out["status"] == "ok"
        assert out["stack_implied"] == "be"
        assert out["domains"] == ["auth"]

        manifest = specs / "handoff-manifest.yaml"
        assert manifest.exists()

        # minimal_yaml (the loader validate.py uses) must parse the emitted YAML.
        data = yaml_load(manifest.read_text())
        assert data["handoff"]["delivered_by"] == "u-spec-orchestrator"
        assert data["handoff"]["type"] == "new_domain"
        assert data["domains"][0]["name"] == "auth"
        artifacts = {p["artifact"] for p in data["backend_package"]}
        assert {"openapi", "back-spec"} <= artifacts          # FLOW-037
        assert "frontend_package" not in data                 # back-only

        # the 13-rule semantic validator (incl. sha256) must accept it.
        val = _validate(manifest, tmp_path)
        assert val.returncode == 0, val.stdout
        assert json.loads(val.stdout)["status"] == "valid"

    def test_fullstack_includes_frontend(self, tmp_path):
        specs = _build_specs(tmp_path, frontend=True)
        gen = _run("generate_handoff_manifest.py", tmp_path, "--workflow-id", WID)
        assert gen.returncode == 0, gen.stdout + gen.stderr
        assert json.loads(gen.stdout)["stack_implied"] == "fullstack"

        data = yaml_load((specs / "handoff-manifest.yaml").read_text())
        assert "frontend_artifacts" in data
        fe_artifacts = {p["artifact"] for p in data["frontend_package"]}
        assert "front" in fe_artifacts and "feature-spec" in fe_artifacts

        val = _validate(specs / "handoff-manifest.yaml", tmp_path)
        assert val.returncode == 0, val.stdout
        assert json.loads(val.stdout)["status"] == "valid"


# --------------------------------------------------------------------------- #
# Level 2 — Step-6 script sequence (the path that used to dead-end at E08)     #
# --------------------------------------------------------------------------- #
class TestStep6Sequence:
    def _sequence(self, tmp_path):
        return [
            _run("check_all_domains_validated.py", tmp_path),
            _run("check_error_codes_synced.py", tmp_path),
            _run("generate_handoff_manifest.py", tmp_path, "--workflow-id", WID),
            _run("check_handoff_manifest_approved.py", tmp_path),
        ]

    def test_backonly_sequence_all_ok(self, tmp_path):
        _build_specs(tmp_path)
        results = self._sequence(tmp_path)
        for r in results:
            assert r.returncode == 0, r.stdout + r.stderr

    def test_fullstack_sequence_all_ok(self, tmp_path):
        _build_specs(tmp_path, frontend=True)
        results = self._sequence(tmp_path)
        for r in results:
            assert r.returncode == 0, r.stdout + r.stderr


# --------------------------------------------------------------------------- #
# Fail-closed                                                                 #
# --------------------------------------------------------------------------- #
class TestFailClosed:
    def test_compliance_block_blocks_generation(self, tmp_path):
        specs = _build_specs(tmp_path, compliance_block=True)
        gen = _run("generate_handoff_manifest.py", tmp_path, "--workflow-id", WID)
        assert gen.returncode != 0
        out = json.loads(gen.stdout)
        assert out["status"] == "blocked"
        assert out["reason"] == "approval_blocked"
        assert not (specs / "handoff-manifest.yaml").exists()

    def test_no_domains_blocks(self, tmp_path):
        (tmp_path / "specs").mkdir()
        gen = _run("generate_handoff_manifest.py", tmp_path, "--workflow-id", WID)
        assert gen.returncode != 0
        assert json.loads(gen.stdout)["reason"] == "no_domains_found"
