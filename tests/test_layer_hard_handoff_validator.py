"""Layer Hard Handoff Validator — deterministic Python manifest validator (task 03b).

validate.py loads handoff-manifest.yaml (via the stdlib minimal_yaml loader),
runs the 13 rules (FLOW-030..037, HDF-010/020/021/030/040) including sha256
content integrity, and exits non-zero on any blocking error. Closes A3-F1 / C4.

NOTE: version-mismatch is a CHAIN rule (FLOW-063, needs the paired
validation-result) — out of scope for the single-manifest validator.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
VALIDATE = ROOT / "dist/.claude/skills/u-handoff-validator/validate.py"
FIX = ROOT / "tests/fixtures"
EMPTY_SHA = hashlib.sha256(b"").hexdigest()


def _run(manifest_path, specs_dir, caller="u-spec-orchestrator"):
    return subprocess.run(
        [sys.executable, str(VALIDATE), "--manifest", str(manifest_path),
         "--specs-dir", str(specs_dir), "--caller", caller],
        capture_output=True, text=True,
    )


def _errors(proc):
    return json.loads(proc.stdout)["errors"]


class TestHandoffValidator:
    def test_valid_manifest_passes(self, tmp_path):
        # the canonical fixture pins sha256 of the empty string; stage empty files.
        specs = tmp_path / "specs" / "auth"
        specs.mkdir(parents=True)
        (specs / "openapi.yaml").write_text("")
        (specs / "back.md").write_text("")
        p = _run(FIX / "valid/handoff-manifest.yaml", tmp_path)
        assert p.returncode == 0, p.stdout
        assert json.loads(p.stdout)["status"] == "valid"

    def test_wrong_sender_blocked(self, tmp_path):
        p = _run(FIX / "invalid/handoff-manifest-wrong-sender.yaml", tmp_path)
        assert p.returncode != 0
        assert any(e.startswith("FLOW-030") for e in _errors(p))

    def test_empty_domains_blocked(self, tmp_path):
        p = _run(FIX / "invalid/handoff-manifest-empty-domains.yaml", tmp_path)
        assert p.returncode != 0
        assert any(e.startswith("FLOW-031") for e in _errors(p))

    def test_no_backend_package_blocked(self, tmp_path):
        p = _run(FIX / "invalid/handoff-manifest-no-backend-package.yaml", tmp_path)
        assert p.returncode != 0
        assert any(e.startswith("FLOW-032") for e in _errors(p))

    def test_bad_type_blocked(self, tmp_path):
        m = tmp_path / "m.yaml"
        m.write_text(
            "handoff:\n  delivered_by: u-spec-orchestrator\n  type: bogus_type\n"
            "domains:\n  - name: auth\n"
            "backend_package:\n  - path: x\n    artifact: openapi\n  - path: y\n    artifact: back-spec\n"
        )
        p = _run(m, tmp_path)
        assert p.returncode != 0
        assert any(e.startswith("HDF-010") for e in _errors(p))

    def test_sha256_mismatch_blocked(self, tmp_path):
        specs = tmp_path / "specs" / "auth"
        specs.mkdir(parents=True)
        (specs / "openapi.yaml").write_text("openapi: 3.0.0\n")  # non-empty -> hash != pinned
        (specs / "back.md").write_text("# spec\n")
        m = tmp_path / "m.yaml"
        m.write_text(
            "handoff:\n  delivered_by: u-spec-orchestrator\n  type: new_domain\n"
            "domains:\n  - name: auth\n"
            "backend_package:\n"
            f"  - path: specs/auth/openapi.yaml\n    artifact: openapi\n    sha256: {'0'*64}\n"
            f"  - path: specs/auth/back.md\n    artifact: back-spec\n    sha256: {'0'*64}\n"
        )
        p = _run(m, tmp_path)
        assert p.returncode != 0
        assert any(e.startswith("HDF-020") for e in _errors(p))

    def test_sha256_match_passes(self, tmp_path):
        specs = tmp_path / "specs" / "auth"
        specs.mkdir(parents=True)
        oa = specs / "openapi.yaml"; oa.write_text("openapi: 3.0.0\n")
        bs = specs / "back.md"; bs.write_text("# spec\n")
        h = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()
        m = tmp_path / "m.yaml"
        m.write_text(
            "handoff:\n  delivered_by: u-spec-orchestrator\n  type: new_domain\n"
            "domains:\n  - name: auth\n"
            "backend_package:\n"
            f"  - path: specs/auth/openapi.yaml\n    artifact: openapi\n    sha256: {h(oa)}\n"
            f"  - path: specs/auth/back.md\n    artifact: back-spec\n    sha256: {h(bs)}\n"
        )
        p = _run(m, tmp_path)
        assert p.returncode == 0, p.stdout
        assert json.loads(p.stdout)["status"] == "valid"

    def test_missing_manifest_errors(self, tmp_path):
        p = _run(tmp_path / "nope.yaml", tmp_path)
        assert p.returncode != 0
