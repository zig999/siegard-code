"""Layer 3 — Cross References: dist/ directory structure and required files."""
import pytest
from conftest import get_dist_dir, get_all_schema_files, get_all_skill_dirs

DIST_DIR = get_dist_dir()

SKIP_SKILL_DIRS = {
    "u-spec-globals",
    "u-spec-templates",
    "u-fe-templates",
    "u-be-templates",
    "u-shared-templates",
}

REQUIRED_SCHEMAS = [
    "task_contract.schema.yaml",
    "handoff-manifest.schema.yaml",
    "validation-result.schema.yaml",
    "blocked-report.schema.yaml",
    "cr.schema.yaml",
]

SKIP_TEMPLATE_SCHEMAS = {
    "backlog.schema.yaml",
    "delivery.schema.yaml",
    "qa-verdict.schema.yaml",
}

_required_dirs = [
    ("agents/", DIST_DIR / "agents"),
    ("agents/spec/", DIST_DIR / "agents" / "spec"),
    ("agents/dev/", DIST_DIR / "agents" / "dev"),
    ("agents/reverse-spec/", DIST_DIR / "agents" / "reverse-spec"),
    ("skills/", DIST_DIR / "skills"),
    ("commands/", DIST_DIR / "commands"),
]

_schema_files = [
    f for f in get_all_schema_files()
    if f.name not in SKIP_TEMPLATE_SCHEMAS
]

_skill_dirs = [d for d in get_all_skill_dirs() if d["name"] not in SKIP_SKILL_DIRS]


class TestLayer3CrossReferences:
    @pytest.mark.parametrize("label,dir_path", _required_dirs, ids=[l for l, _ in _required_dirs])
    def test_required_directory_exists(self, label, dir_path):
        assert dir_path.exists(), f"Directory not found: {dir_path}"

    @pytest.mark.parametrize("schema_name", REQUIRED_SCHEMAS)
    def test_required_schema_exists(self, schema_name):
        schema_path = DIST_DIR / "skills" / "u-shared-templates" / schema_name
        assert schema_path.exists(), f"Missing required schema: {schema_name}"

    @pytest.mark.parametrize("path", _schema_files, ids=[f.name for f in _schema_files])
    def test_schema_has_matching_template(self, path):
        plain = path.parent / path.name.replace(".schema.yaml", ".yaml")
        templated = path.parent / path.name.replace(".schema.yaml", "-template.yaml")
        assert plain.exists() or templated.exists(), f"No template found for {path.name}"

    @pytest.mark.parametrize(
        "name,dir_path",
        [(d["name"], d["path"]) for d in _skill_dirs],
        ids=[d["name"] for d in _skill_dirs],
    )
    def test_skill_dir_has_skill_md(self, name, dir_path):
        skill_file = dir_path / "SKILL.md"
        assert skill_file.exists(), f"SKILL.md not found in dist/skills/{name}/"
