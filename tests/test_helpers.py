"""Smoke tests for shared helper functions."""
from pathlib import Path
from conftest import (
    get_dist_dir,
    get_all_agent_files,
    get_top_level_agent_files,
    get_all_schema_files,
    parse_frontmatter,
    load_fixture,
    validate,
    compile_all_schemas,
)


class TestHelpers:
    def test_get_dist_dir_returns_existing_dir(self):
        d = get_dist_dir()
        assert str(d).endswith("dist/.claude")
        assert len(get_all_agent_files()) > 10

    def test_parse_frontmatter_extracts_fields(self):
        fm = parse_frontmatter(get_top_level_agent_files()[0])
        assert "name" in fm
        assert "description" in fm

    def test_load_fixture_returns_parsed_yaml(self):
        data = load_fixture("valid/task-contract.yaml")
        assert isinstance(data, dict)
        assert data is not None

    def test_validate_returns_valid_for_good_fixture(self):
        schema_file = get_dist_dir() / "skills" / "u-shared-templates" / "task_contract.schema.yaml"
        result = validate(schema_file, load_fixture("valid/task-contract.yaml"))
        assert result["valid"] is True
        assert isinstance(result["errors"], list)

    def test_compile_all_schemas_all_succeed(self):
        results = compile_all_schemas()
        assert len(get_all_schema_files()) > 0
        failures = [r for r in results if not r["compiled"]]
        assert failures == [], f"Failed schemas: {[str(f['file']) for f in failures]}"
