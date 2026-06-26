"""Layer Hard SDD Gate — handoff_manifest_approved invokes the semantic validator (task 04).

The SDD->dev exit criterion passes when the validator returns status:valid. Approval is
DERIVED from semantic validity (F1 reconciliation): the prior `Status: approved` marker is
no longer a gate condition — the canonical schema defines no status field, so requiring the
marker was unsatisfiable. Fail-closed on missing manifest or validator error.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
GATE = ROOT / "dist/.claude/skills/phase-sdd-rules/scripts/check_handoff_manifest_approved.py"
FIX = ROOT / "tests/fixtures"


def _gate(project_dir, specs="specs"):
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir), "SPECS_DIR": specs}
    return subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True, env=env)


def _stage(tmp, fixture_rel):
    specs = tmp / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    data = (FIX / fixture_rel).read_text()
    if "status:" not in data.lower():
        data = "Status: approved\n" + data  # approval marker present for all these cases
    (specs / "handoff-manifest.yaml").write_text(data)
    return specs


class TestSddGateSemantic:
    def test_valid_approved_manifest_passes(self, tmp_path):
        _stage(tmp_path, "valid/handoff-manifest.yaml")
        auth = tmp_path / "specs" / "auth"
        auth.mkdir(parents=True)
        (auth / "openapi.yaml").write_text("")   # sha256 of "" == pinned e3b0c44...
        (auth / "back.md").write_text("")
        p = _gate(tmp_path)
        assert p.returncode == 0, p.stdout
        assert json.loads(p.stdout)["met"] is True

    def test_wrong_sender_blocked_even_with_status_approved(self, tmp_path):
        _stage(tmp_path, "invalid/handoff-manifest-wrong-sender.yaml")
        p = _gate(tmp_path)
        assert p.returncode != 0
        ev = json.loads(p.stdout)
        assert ev["met"] is False
        assert ev["evidence"]["validator_status"] == "invalid"

    def test_empty_domains_blocked_even_with_status_approved(self, tmp_path):
        _stage(tmp_path, "invalid/handoff-manifest-empty-domains.yaml")
        assert _gate(tmp_path).returncode != 0

    def test_no_backend_package_blocked_even_with_status_approved(self, tmp_path):
        _stage(tmp_path, "invalid/handoff-manifest-no-backend-package.yaml")
        assert _gate(tmp_path).returncode != 0

    def test_missing_manifest_fails_closed(self, tmp_path):
        (tmp_path / "specs").mkdir(parents=True)
        p = _gate(tmp_path)
        assert p.returncode != 0
        assert json.loads(p.stdout)["evidence"]["exists"] is False

    def test_valid_manifest_without_approval_marker_is_met(self, tmp_path):
        # F1 reconciliation: approval is derived from the semantic validator, so a
        # schema-valid manifest is approved even without a Status: marker (the canonical
        # schema has no status field — requiring the marker was unsatisfiable).
        specs = tmp_path / "specs"
        specs.mkdir(parents=True)
        auth = specs / "auth"
        auth.mkdir()
        (auth / "openapi.yaml").write_text("")
        (auth / "back.md").write_text("")
        (specs / "handoff-manifest.yaml").write_text(
            (FIX / "valid/handoff-manifest.yaml").read_text()  # no Status: line
        )
        p = _gate(tmp_path)
        assert p.returncode == 0, p.stdout
        ev = json.loads(p.stdout)
        assert ev["evidence"]["validator_status"] == "valid"
        assert ev["met"] is True
