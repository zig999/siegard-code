"""
Tests for sdd-phase exit criteria scripts (Level A).

Scripts under test:
  - check_handoff_manifest_approved.py  (reads SPECS_DIR/handoff-manifest.yaml)
  - check_all_domains_validated.py      (reads SPECS_DIR/_validation/)
  - check_error_codes_synced.py         (reads SPECS_DIR/**/*.yaml + error-codes.md)
"""
import pytest

from .conftest import SDD_SCRIPTS, phase_env, run_check  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _specs_dir(project_dir):
    d = project_dir / "specs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_manifest(project_dir, status="approved"):
    # prod-hardening task 04: the gate now runs the semantic validator, so the
    # manifest must be semantically valid (delivered_by, domains, backend_package).
    # sha256 fields omitted -> integrity check skipped (no staged files needed).
    specs = _specs_dir(project_dir)
    (specs / "handoff-manifest.yaml").write_text(
        "handoff:\n"
        "  delivered_by: u-spec-orchestrator\n"
        "  type: new_domain\n"
        f"Status: {status}\n"
        "stack: be\n"
        "domains:\n"
        "  - name: auth\n"
        "backend_package:\n"
        "  - path: specs/auth/openapi.yaml\n"
        "    artifact: openapi\n"
        "  - path: specs/auth/back.md\n"
        "    artifact: back-spec\n"
    )


def _write_validation_file(project_dir, name, status="VALID"):
    val_dir = _specs_dir(project_dir) / "_validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    (val_dir / name).write_text(f"Domain: auth\nStatus: {status}\n")


def _write_spec_yaml(project_dir, name, error_codes: list[str] | None = None):
    domain_dir = _specs_dir(project_dir) / "domains" / "auth"
    domain_dir.mkdir(parents=True, exist_ok=True)
    content = "openapi: '3.0'\npaths:\n  /auth:\n    post:\n      responses:\n"
    for code in (error_codes or []):
        content += f"        '{code}':\n          error_code: {code}\n"
    (domain_dir / name).write_text(content)


def _write_error_codes_md(project_dir, codes: list[str]):
    specs = _specs_dir(project_dir)
    content = "# Error Codes\n\n"
    for code in codes:
        content += f"| {code} | Description |\n"
    (specs / "error-codes.md").write_text(content)


# ---------------------------------------------------------------------------
# check_handoff_manifest_approved.py
# ---------------------------------------------------------------------------

class TestHandoffManifestApproved:
    def test_file_absent_is_not_met(self, phase_env):
        result = run_check(SDD_SCRIPTS["check_manifest"], phase_env)
        assert result["criterion"] == "handoff_manifest_approved"
        assert result["met"] is False
        assert result["evidence"]["exists"] is False

    def test_status_draft_still_met_approval_is_derived(self, phase_env):
        # F1 reconciliation: approval is derived from the semantic validator, not the
        # vestigial Status: marker (the canonical schema defines no status field). A
        # semantically valid manifest is met regardless of any Status: value.
        _write_manifest(phase_env, status="draft")
        result = run_check(SDD_SCRIPTS["check_manifest"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["exists"] is True
        assert result["evidence"]["status_found"] == "draft"
        assert result["evidence"]["validator_status"] == "valid"

    def test_status_approved_is_met(self, phase_env):
        _write_manifest(phase_env, status="approved")
        result = run_check(SDD_SCRIPTS["check_manifest"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["status_found"] == "approved"

    def test_status_approved_uppercase_is_met(self, phase_env):
        _write_manifest(phase_env, status="APPROVED")
        result = run_check(SDD_SCRIPTS["check_manifest"], phase_env)
        assert result["met"] is True

    def test_status_missing_is_not_met(self, phase_env):
        specs = _specs_dir(phase_env)
        (specs / "handoff-manifest.yaml").write_text("type: new_domain\nstack: be\n")
        result = run_check(SDD_SCRIPTS["check_manifest"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["status_found"] is None

    def test_status_in_progress_still_met_approval_is_derived(self, phase_env):
        # F1 reconciliation: the Status: marker no longer gates approval — only the
        # semantic validator does. Step 6 ordering guarantees the manifest is generated
        # solely over VALID specs, so a valid manifest is approved.
        _write_manifest(phase_env, status="in_progress")
        result = run_check(SDD_SCRIPTS["check_manifest"], phase_env)
        assert result["met"] is True


# ---------------------------------------------------------------------------
# check_all_domains_validated.py
# ---------------------------------------------------------------------------

class TestAllDomainsValidated:
    def test_validation_dir_absent_is_not_met(self, phase_env):
        _specs_dir(phase_env)
        result = run_check(SDD_SCRIPTS["check_domains"], phase_env)
        assert result["criterion"] == "all_domains_validated"
        assert result["met"] is False
        assert result["evidence"]["exists"] is False

    def test_validation_dir_empty_is_not_met(self, phase_env):
        val_dir = _specs_dir(phase_env) / "_validation"
        val_dir.mkdir(parents=True, exist_ok=True)
        result = run_check(SDD_SCRIPTS["check_domains"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["total"] == 0

    def test_one_valid_domain_is_met(self, phase_env):
        _write_validation_file(phase_env, "auth.yaml", status="VALID")
        result = run_check(SDD_SCRIPTS["check_domains"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["passing"] == 1

    def test_multiple_valid_domains_is_met(self, phase_env):
        _write_validation_file(phase_env, "auth.yaml", status="VALID")
        _write_validation_file(phase_env, "billing.yaml", status="VALID")
        result = run_check(SDD_SCRIPTS["check_domains"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["total"] == 2

    def test_one_invalid_domain_is_not_met(self, phase_env):
        _write_validation_file(phase_env, "auth.yaml", status="VALID")
        _write_validation_file(phase_env, "billing.yaml", status="INVALID")
        result = run_check(SDD_SCRIPTS["check_domains"], phase_env)
        assert result["met"] is False
        failing_names = [f["file"] for f in result["evidence"]["failing"]]
        assert "billing.yaml" in failing_names

    def test_all_invalid_is_not_met(self, phase_env):
        _write_validation_file(phase_env, "auth.yaml", status="INVALID")
        result = run_check(SDD_SCRIPTS["check_domains"], phase_env)
        assert result["met"] is False

    def test_md_files_also_scanned(self, phase_env):
        _write_validation_file(phase_env, "auth.md", status="VALID")
        result = run_check(SDD_SCRIPTS["check_domains"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["total"] == 1

    def test_invalid_value_case_insensitive(self, phase_env):
        _write_validation_file(phase_env, "auth.yaml", status="invalid")
        result = run_check(SDD_SCRIPTS["check_domains"], phase_env)
        assert result["met"] is False


# ---------------------------------------------------------------------------
# check_error_codes_synced.py
# ---------------------------------------------------------------------------

class TestErrorCodesSynced:
    def test_no_spec_files_is_trivially_met(self, phase_env):
        """No spec files → no codes to check → trivially met."""
        _specs_dir(phase_env)
        result = run_check(SDD_SCRIPTS["check_error_codes"], phase_env)
        assert result["criterion"] == "error_codes_synced"
        assert result["met"] is True
        assert result["evidence"]["spec_codes_found"] == []

    def test_spec_codes_all_registered_is_met(self, phase_env):
        _write_spec_yaml(phase_env, "openapi.yaml", error_codes=["E001", "E002"])
        _write_error_codes_md(phase_env, ["E001", "E002"])
        result = run_check(SDD_SCRIPTS["check_error_codes"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["missing_codes"] == []

    def test_spec_code_missing_from_md_is_not_met(self, phase_env):
        _write_spec_yaml(phase_env, "openapi.yaml", error_codes=["E001", "E099"])
        _write_error_codes_md(phase_env, ["E001"])
        result = run_check(SDD_SCRIPTS["check_error_codes"], phase_env)
        assert result["met"] is False
        assert "E099" in result["evidence"]["missing_codes"]

    def test_error_codes_file_absent_and_no_codes_is_met(self, phase_env):
        _specs_dir(phase_env)
        result = run_check(SDD_SCRIPTS["check_error_codes"], phase_env)
        assert result["met"] is True

    def test_error_codes_file_absent_but_codes_in_spec_is_not_met(self, phase_env):
        _write_spec_yaml(phase_env, "openapi.yaml", error_codes=["E001"])
        result = run_check(SDD_SCRIPTS["check_error_codes"], phase_env)
        assert result["met"] is False
        assert "E001" in result["evidence"]["missing_codes"]

    def test_validation_dir_excluded_from_scan(self, phase_env):
        """YAML files inside _validation/ should not be scanned for codes."""
        specs = _specs_dir(phase_env)
        val_dir = specs / "_validation"
        val_dir.mkdir(parents=True, exist_ok=True)
        (val_dir / "auth.yaml").write_text("code: E999\n")
        result = run_check(SDD_SCRIPTS["check_error_codes"], phase_env)
        assert result["met"] is True
        assert "E999" not in result["evidence"]["spec_codes_found"]
