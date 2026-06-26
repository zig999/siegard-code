"""Layer 2 — Schema Conformance: YAML schemas compile and fixtures validate correctly."""
import pytest
from conftest import (
    get_dist_dir,
    get_all_schema_files,
    load_fixture,
    validate,
    compile_all_schemas,
)

SCHEMA_DIR = get_dist_dir() / "skills" / "u-shared-templates"

SCHEMA_FIXTURE_MAP = {
    "task_contract.schema.yaml": {
        "valid": "valid/task-contract.yaml",
        "invalid": [
            "invalid/task-contract-scope-both.yaml",
            "invalid/task-contract-estimate-l.yaml",
        ],
        "extra_valid": ["valid/task-contract-no-constraints.yaml"],
    },
    "handoff-manifest.schema.yaml": {
        "valid": "valid/handoff-manifest.yaml",
        "invalid": ["invalid/handoff-manifest-empty-domains.yaml"],
    },
    "validation-result.schema.yaml": {
        "valid": "valid/validation-result.yaml",
        "invalid": [],
    },
    "blocked-report.schema.yaml": {
        "valid": "valid/blocked-report.yaml",
        "invalid": [],
    },
    "cr.schema.yaml": {
        "valid": "valid/cr.yaml",
        "invalid": [],
    },
    "be-to-fe-handoff.schema.yaml": {
        "valid": "valid/be-to-fe-handoff.yaml",
        "invalid": [
            "invalid/be-to-fe-handoff-empty-endpoints.yaml",
            "invalid/be-to-fe-handoff-wrong-status.yaml",
        ],
        "extra_valid": ["valid/be-to-fe-handoff-with-deviations.yaml"],
    },
    "ui-agent-output.schema.yaml": {
        "valid": "valid/ui-agent-output.yaml",
        "invalid": ["invalid/ui-agent-output-no-tasks.yaml"],
    },
    "security-finding.schema.yaml": {
        "valid": "valid/security-finding.yaml",
        "invalid": ["invalid/security-finding-wrong-verdict.yaml"],
        "extra_valid": ["valid/security-finding-blocked.yaml"],
    },
    "architecture-finding.schema.yaml": {
        "valid": "valid/architecture-finding.yaml",
        "invalid": ["invalid/architecture-finding-empty-deliveries.yaml"],
        "extra_valid": ["valid/architecture-finding-with-findings.yaml"],
    },
    "improve-handoff-envelope.schema.yaml": {
        "valid": "valid/improve-handoff-envelope.yaml",
        "invalid": [
            "invalid/improve-handoff-envelope-bad-id.yaml",
            "invalid/improve-handoff-envelope-missing-return-contract.yaml",
            "invalid/improve-handoff-envelope-bad-mode-hint.yaml",
            "invalid/improve-handoff-envelope-bad-source.yaml",
            "invalid/improve-handoff-envelope-empty-improve-session.yaml",
            "invalid/improve-handoff-envelope-update-field-wrong.yaml",
            "invalid/improve-handoff-envelope-missing-execution-policy.yaml",
            "invalid/improve-handoff-envelope-bad-pipeline.yaml",
        ],
        "extra_valid": [
            "valid/improve-handoff-envelope-fast-track-patch.yaml",
            "valid/improve-handoff-envelope-full.yaml",
            "valid/improve-handoff-envelope-lean.yaml",
            "valid/improve-handoff-envelope-no-tdd.yaml",
        ],
    },
    "spec-changelog-notify.schema.yaml": {
        "valid": "valid/spec-changelog-notify.yaml",
        "invalid": [
            "invalid/spec-changelog-notify-bad-origin.yaml",
            "invalid/spec-changelog-notify-empty-changed-files.yaml",
        ],
    },
    "handoff-receipt.schema.yaml": {
        "valid": "valid/handoff-receipt.yaml",
        "invalid": [
            "invalid/handoff-receipt-bad-consumer.yaml",
            "invalid/handoff-receipt-bad-hash.yaml",
        ],
        "extra_valid": ["valid/handoff-receipt-halted.yaml"],
    },
    "handoff-validation-envelope.schema.yaml": {
        "valid": "valid/handoff-validation-envelope-valid.yaml",
        "invalid": ["invalid/handoff-validation-envelope-valid-with-errors.yaml"],
        "extra_valid": ["valid/handoff-validation-envelope-invalid.yaml"],
    },
}

_compile_results = compile_all_schemas()

# Build parametrize lists at module level
_valid_cases = [
    (name, entry["valid"], SCHEMA_DIR / name)
    for name, entry in SCHEMA_FIXTURE_MAP.items()
]
_invalid_cases = [
    (name, fix, SCHEMA_DIR / name)
    for name, entry in SCHEMA_FIXTURE_MAP.items()
    for fix in entry.get("invalid", [])
]
_extra_valid_cases = [
    (name, fix, SCHEMA_DIR / name)
    for name, entry in SCHEMA_FIXTURE_MAP.items()
    for fix in entry.get("extra_valid", [])
]


class TestLayer2SchemaConformance:
    @pytest.mark.parametrize(
        "result",
        _compile_results,
        ids=[r["file"].name for r in _compile_results],
    )
    def test_schema_compiles_successfully(self, result):
        assert result["compiled"], result.get("error") or ""

    @pytest.mark.parametrize(
        "schema_name,fixture_path,schema_file",
        _valid_cases,
        ids=[f"{n}:{p}" for n, p, _ in _valid_cases],
    )
    def test_valid_fixture_passes_schema(self, schema_name, fixture_path, schema_file):
        data = load_fixture(fixture_path)
        result = validate(schema_file, data)
        errors_msg = "\n".join(str(e) for e in result["errors"])
        assert result["valid"], f"Schema errors:\n{errors_msg}"

    @pytest.mark.parametrize(
        "schema_name,fixture_path,schema_file",
        _invalid_cases,
        ids=[f"{n}:{p}" for n, p, _ in _invalid_cases],
    )
    def test_invalid_fixture_fails_schema(self, schema_name, fixture_path, schema_file):
        data = load_fixture(fixture_path)
        result = validate(schema_file, data)
        assert not result["valid"], f"Expected {fixture_path} to fail {schema_name}"

    @pytest.mark.parametrize(
        "schema_name,fixture_path,schema_file",
        _extra_valid_cases,
        ids=[f"{n}:{p}" for n, p, _ in _extra_valid_cases],
    )
    def test_extra_valid_fixture_passes_schema(self, schema_name, fixture_path, schema_file):
        data = load_fixture(fixture_path)
        result = validate(schema_file, data)
        errors_msg = "\n".join(str(e) for e in result["errors"])
        assert result["valid"], f"Schema errors:\n{errors_msg}"
