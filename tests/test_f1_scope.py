"""F1 — change scope: an /u-improve gates and dispatches only the domains it touches.

A breaking one-domain /u-improve is legitimately classified `full`/`standard`.
Standard mode used to treat every on-disk domain as `new` (full pipeline for all)
and the exit gate + handoff scan required EVERY domain VALID — so a one-domain
change cascaded across the project and a stale INVALID/handoff_allowed:false in an
untouched domain blocked an unrelated change (the F3 symptom).

scope.py derives the affected-domain set from triage.affected_specs; the gate
(check_all_domains_validated) and the handoff scan (generate_handoff_manifest)
restrict themselves to it. u-spec / greenfield keep the global behavior.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "dist/.claude/skills/phase-sdd-rules/scripts"
WID = "wf-test"


def _run(script: str, project_dir: Path, *args: str):
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir), "SPECS_DIR": "specs"}
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, env=env,
    )


def _domain(specs: Path, name: str, *, status: str = "VALID", handoff: str | None = None):
    d = specs / "domains" / name
    (d / "back").mkdir(parents=True, exist_ok=True)
    (d / "openapi.yaml").write_text(
        f"openapi: 3.0.3\ninfo:\n  title: {name}\n  version: 1.0.0\npaths: {{}}\n")
    (d / f"{name}.spec.md").write_text(f"# {name}\n\n> Version: 1.0.0\n")
    (d / "back" / f"{name}.back.md").write_text(f"# {name} back\n\n> Version: 1.0.0\n")
    val = specs / "_validation"
    val.mkdir(parents=True, exist_ok=True)
    ho = handoff if handoff is not None else ("true" if status == "VALID" else "false")
    (val / f"{name}-validation-result.yaml").write_text(
        f"domain: {name}\nstatus: {status}\nblocking_count: 0\nhandoff_allowed: {ho}\n")


def _triage(project_dir: Path, *, trigger: str, affected: list[str]):
    sess = project_dir / ".orch" / "sessions" / WID
    sess.mkdir(parents=True, exist_ok=True)
    (sess / "triage.json").write_text(json.dumps({
        "workflow_id": WID, "trigger": trigger, "greenfield": trigger == "u-spec",
        "type": "spec_change_required", "mode_hint": "full",
        "affected_specs": [{"path": f"specs/domains/{d}/openapi.yaml"} for d in affected],
    }))


def _build(tmp_path: Path, domains: dict, *, trigger: str, affected: list[str]) -> Path:
    specs = tmp_path / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    (specs / "error-codes.md").write_text("# Error Codes\n")
    for name, kw in domains.items():
        _domain(specs, name, **kw)
    _triage(tmp_path, trigger=trigger, affected=affected)
    return specs


# --------------------------------------------------------------------------- #
# scope.py                                                                     #
# --------------------------------------------------------------------------- #
class TestScope:
    def test_improve_returns_affected_domains(self, tmp_path):
        _triage(tmp_path, trigger="u-improve", affected=["ifs-integration"])
        out = json.loads(_run("scope.py", tmp_path, "--workflow-id", WID).stdout)
        assert out["scoped"] is True
        assert out["domains"] == ["ifs-integration"]

    def test_uspec_is_unscoped(self, tmp_path):
        _triage(tmp_path, trigger="u-spec", affected=[])
        out = json.loads(_run("scope.py", tmp_path, "--workflow-id", WID).stdout)
        assert out["scoped"] is False
        assert out["domains"] is None

    def test_front_only_improve_is_unscoped(self, tmp_path):
        # affected_specs with no domains/<slug>/ path → cannot narrow → global.
        sess = tmp_path / ".orch" / "sessions" / WID
        sess.mkdir(parents=True)
        (sess / "triage.json").write_text(json.dumps({
            "workflow_id": WID, "trigger": "u-improve",
            "affected_specs": [{"path": "specs/front/front.md"}],
        }))
        out = json.loads(_run("scope.py", tmp_path, "--workflow-id", WID).stdout)
        assert out["scoped"] is False

    def test_missing_triage_is_unscoped(self, tmp_path):
        out = json.loads(_run("scope.py", tmp_path, "--workflow-id", WID).stdout)
        assert out["scoped"] is False


# --------------------------------------------------------------------------- #
# check_all_domains_validated.py — scoped gate                                 #
# --------------------------------------------------------------------------- #
class TestScopedGate:
    def test_untouched_invalid_domain_does_not_block_improve(self, tmp_path):
        # ifs-integration (touched) VALID; assyst-delivery (untouched) INVALID.
        _build(tmp_path, {
            "ifs-integration": {"status": "VALID"},
            "assyst-delivery": {"status": "INVALID"},
        }, trigger="u-improve", affected=["ifs-integration"])
        r = _run("check_all_domains_validated.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 0, r.stdout
        out = json.loads(r.stdout)
        assert out["met"] is True
        assert out["evidence"]["scoped"] is True
        # the untouched INVALID is surfaced for audit, not blocking
        names = [f["file"] for f in out["evidence"]["out_of_scope_invalid"]]
        assert "assyst-delivery-validation-result.yaml" in names

    def test_touched_invalid_domain_blocks(self, tmp_path):
        _build(tmp_path, {
            "ifs-integration": {"status": "INVALID"},
            "assyst-delivery": {"status": "VALID"},
        }, trigger="u-improve", affected=["ifs-integration"])
        r = _run("check_all_domains_validated.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 1
        out = json.loads(r.stdout)
        assert out["met"] is False
        names = [f["file"] for f in out["evidence"]["failing"]]
        assert "ifs-integration-validation-result.yaml" in names

    def test_uspec_stays_global(self, tmp_path):
        # No scoping for u-spec: an INVALID domain blocks even if "not targeted".
        _build(tmp_path, {
            "auth": {"status": "VALID"},
            "billing": {"status": "INVALID"},
        }, trigger="u-spec", affected=[])
        r = _run("check_all_domains_validated.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 1
        assert json.loads(r.stdout)["evidence"]["scoped"] is False

    def test_no_workflow_id_is_global_backcompat(self, tmp_path):
        _build(tmp_path, {
            "auth": {"status": "VALID"},
            "billing": {"status": "INVALID"},
        }, trigger="u-improve", affected=["auth"])
        r = _run("check_all_domains_validated.py", tmp_path)  # no --workflow-id
        assert r.returncode == 1  # global: billing INVALID blocks
        assert json.loads(r.stdout)["evidence"]["scoped"] is False


# --------------------------------------------------------------------------- #
# generate_handoff_manifest.py — scoped approval scan                          #
# --------------------------------------------------------------------------- #
class TestScopedHandoff:
    def test_untouched_false_does_not_block(self, tmp_path):
        # assyst-delivery (untouched) has a stale handoff_allowed:false; the improve
        # touches only ifs-integration → manifest must still generate (fix F1/F3).
        specs = _build(tmp_path, {
            "ifs-integration": {"status": "VALID", "handoff": "true"},
            "assyst-delivery": {"status": "VALID", "handoff": "false"},
        }, trigger="u-improve", affected=["ifs-integration"])
        r = _run("generate_handoff_manifest.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 0, r.stdout
        assert json.loads(r.stdout)["status"] == "ok"
        assert (specs / "handoff-manifest.yaml").exists()

    def test_touched_false_blocks(self, tmp_path):
        specs = _build(tmp_path, {
            "ifs-integration": {"status": "VALID", "handoff": "false"},
        }, trigger="u-improve", affected=["ifs-integration"])
        r = _run("generate_handoff_manifest.py", tmp_path, "--workflow-id", WID)
        assert r.returncode != 0
        assert json.loads(r.stdout)["reason"] == "approval_blocked"
        assert not (specs / "handoff-manifest.yaml").exists()

    def test_uspec_false_still_blocks_global(self, tmp_path):
        specs = _build(tmp_path, {
            "auth": {"status": "VALID", "handoff": "true"},
            "billing": {"status": "VALID", "handoff": "false"},
        }, trigger="u-spec", affected=[])
        r = _run("generate_handoff_manifest.py", tmp_path, "--workflow-id", WID)
        assert r.returncode != 0
        assert json.loads(r.stdout)["reason"] == "approval_blocked"
        assert not (specs / "handoff-manifest.yaml").exists()
