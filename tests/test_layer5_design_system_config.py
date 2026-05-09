"""Layer 5 — Design System Config: fe-validate-report schema and fixtures."""
import pytest
from conftest import get_dist_dir, load_fixture, validate, _make_validator, load_yaml

DIST_DIR = get_dist_dir()

FE_VALIDATE_CMD = DIST_DIR / "commands" / "u-fe-validate.md"
SCHEMA_FILE = DIST_DIR / "skills" / "u-shared-templates" / "fe-validate-report.schema.yaml"
TEMPLATE_FILE = DIST_DIR / "skills" / "u-shared-templates" / "fe-validate-report.yaml"

VALID_FIXTURES = [
    ("fe-validate-report (rejected)", "valid/fe-validate-report.yaml"),
    ("fe-validate-report (approved)", "valid/fe-validate-report-approved.yaml"),
    ("fe-validate-report (approved_with_caveats)", "valid/fe-validate-report-caveats.yaml"),
]

INVALID_FIXTURES = [
    ("missing meta field", "invalid/fe-validate-report-missing-meta.yaml"),
    ("invalid verdict value", "invalid/fe-validate-report-invalid-verdict.yaml"),
    ("invalid run_id pattern", "invalid/fe-validate-report-invalid-run-id.yaml"),
    ("invalid finding severity value", "invalid/fe-validate-report-invalid-finding-severity.yaml"),
    ("wrong validated_by value", "invalid/fe-validate-report-wrong-validated-by.yaml"),
]

VERDICT_FIXTURES = [
    "valid/fe-validate-report.yaml",
    "valid/fe-validate-report-approved.yaml",
    "valid/fe-validate-report-caveats.yaml",
]


class TestLayer5FileExistence:
    @pytest.mark.parametrize("label,path", [
        ("u-fe-validate command", FE_VALIDATE_CMD),
        ("fe-validate-report.schema.yaml", SCHEMA_FILE),
        ("fe-validate-report.yaml", TEMPLATE_FILE),
    ], ids=["u-fe-validate", "schema", "template"])
    def test_required_file_exists(self, label, path):
        assert path.exists(), f"File not found: {path}"


class TestLayer5FeValidateReportSchema:
    def test_schema_compiles_without_errors(self):
        schema = load_yaml(SCHEMA_FILE)
        _make_validator(schema)  # raises on error

    @pytest.mark.parametrize("label,fixture_path", VALID_FIXTURES, ids=[l for l, _ in VALID_FIXTURES])
    def test_valid_fixture_passes_schema(self, label, fixture_path):
        data = load_fixture(fixture_path)
        result = validate(SCHEMA_FILE, data)
        errors = "\n".join(f"{e.json_path} {e.message}" for e in result["errors"])
        assert result["valid"], f"Schema validation failed:\n{errors}"

    @pytest.mark.parametrize("label,fixture_path", INVALID_FIXTURES, ids=[l for l, _ in INVALID_FIXTURES])
    def test_invalid_fixture_fails_schema(self, label, fixture_path):
        data = load_fixture(fixture_path)
        result = validate(SCHEMA_FILE, data)
        assert not result["valid"], f"Expected schema to reject: {fixture_path}"

    def test_approved_fixture_has_zero_total(self):
        data = load_fixture("valid/fe-validate-report-approved.yaml")
        assert data["summary"]["total"] == 0
        assert data["verdict"] == "approved"

    def test_approved_with_caveats_has_no_critical_or_high(self):
        data = load_fixture("valid/fe-validate-report-caveats.yaml")
        assert data["summary"]["critical"] == 0
        assert data["summary"]["high"] == 0
        assert data["summary"]["total"] > 0
        assert data["verdict"] == "approved_with_caveats"

    def test_rejected_fixture_has_at_least_one_critical(self):
        data = load_fixture("valid/fe-validate-report.yaml")
        assert data["summary"]["critical"] > 0
        assert data["verdict"] == "rejected"

    @pytest.mark.parametrize("fixture_path", VERDICT_FIXTURES)
    def test_summary_total_equals_sum_of_severities(self, fixture_path):
        data = load_fixture(fixture_path)
        s = data["summary"]
        total = s["critical"] + s["high"] + s["medium"] + s["low"]
        assert total == s["total"], f"summary.total mismatch in {fixture_path}"

    @pytest.mark.parametrize("fixture_path", VERDICT_FIXTURES)
    def test_findings_length_matches_summary_total(self, fixture_path):
        data = load_fixture(fixture_path)
        assert len(data["findings"]) == data["summary"]["total"], \
            f"findings.length mismatch in {fixture_path}"
