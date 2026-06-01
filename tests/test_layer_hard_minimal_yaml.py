"""Layer Hard Minimal YAML — stdlib-only YAML subset loader (task 03a).

Replaces the pyyaml dependency (check_worker.py) and backs the handoff validator.
Supports the subset Siegard artifacts use: block mappings, block sequences,
nested-by-indentation, quoted/plain scalars, inline comments, block scalars
('>' / '|'). Coerces only true/false/null. NOT a general YAML parser.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))
FIX = ROOT / "tests" / "fixtures"


class TestMinimalYAML:
    def test_flat_mapping(self):
        from minimal_yaml import load
        d = load("name: u-be-developer\nmodel: claude-sonnet-4-6\n")
        assert d == {"name": "u-be-developer", "model": "claude-sonnet-4-6"}

    def test_nested_mapping(self):
        from minimal_yaml import load
        d = load("handoff:\n  type: new_domain\n  delivered_by: u-spec-orchestrator\n")
        assert d["handoff"]["type"] == "new_domain"
        assert d["handoff"]["delivered_by"] == "u-spec-orchestrator"

    def test_list_of_scalars(self):
        from minimal_yaml import load
        d = load("tools:\n  - Read\n  - Edit\nskills:\n  - orch-report\n  - orch-log\n")
        assert d["tools"] == ["Read", "Edit"]
        assert d["skills"] == ["orch-report", "orch-log"]

    def test_list_of_maps(self):
        from minimal_yaml import load
        text = (
            "backend_package:\n"
            "  - path: specs/auth/openapi.yaml\n"
            "    artifact: openapi\n"
            "    sha256: abc123\n"
            "  - path: specs/auth/back.md\n"
            "    artifact: back-spec\n"
            "    sha256: def456\n"
        )
        d = load(text)
        pkg = d["backend_package"]
        assert len(pkg) == 2
        assert pkg[0] == {"path": "specs/auth/openapi.yaml", "artifact": "openapi", "sha256": "abc123"}
        assert pkg[1]["artifact"] == "back-spec"

    def test_quoted_and_comments(self):
        from minimal_yaml import load
        d = load('a: "2026-04-09T12:00:00Z"  # iso ts\nb: plain value\n# full-line comment\nc: 42\n')
        assert d["a"] == "2026-04-09T12:00:00Z"
        assert d["b"] == "plain value"
        assert d["c"] == 42

    def test_bool_null_coercion_only(self):
        from minimal_yaml import load
        d = load("t: true\nf: false\nn: null\nver: 1.0.0\nname: yes\n")
        assert d["t"] is True and d["f"] is False and d["n"] is None
        assert d["ver"] == "1.0.0"      # version-like stays string
        assert d["name"] == "yes"        # NO yes/no coercion (pyyaml footgun avoided)

    def test_block_scalar_folded_does_not_break_following_keys(self):
        from minimal_yaml import load
        text = (
            "name: u-be-developer\n"
            "description: >\n"
            "  Coding standards and\n"
            "  error handling patterns.\n"
            "model: claude-sonnet-4-6\n"
            "skills:\n"
            "  - orch-report\n"
        )
        d = load(text)
        assert d["name"] == "u-be-developer"
        assert d["model"] == "claude-sonnet-4-6"        # key after block scalar still parsed
        assert d["skills"] == ["orch-report"]
        assert isinstance(d["description"], str) and "Coding standards" in d["description"]

    def test_loads_real_manifest_fixture(self):
        from minimal_yaml import load
        d = load((FIX / "valid" / "handoff-manifest.yaml").read_text())
        assert d["handoff"]["delivered_by"] == "u-spec-orchestrator"
        assert d["handoff"]["type"] == "new_domain"
        assert isinstance(d["domains"], list) and d["domains"][0]["name"] == "auth"
        assert isinstance(d["backend_package"], list) and len(d["backend_package"]) == 2
        assert all("sha256" in p for p in d["backend_package"])

    def test_empty_flow_collections(self):
        from minimal_yaml import load
        d = load("domains: []\nbackend_package: []\nmeta: {}\n")
        assert d["domains"] == []
        assert d["backend_package"] == []
        assert d["meta"] == {}

    def test_empty_and_missing(self):
        from minimal_yaml import load
        assert load("") in ({}, None)
        assert load("# only a comment\n") in ({}, None)


class TestCheckWorkerRefactor:
    """Locks the pyyaml -> minimal_yaml refactor of check_worker.py (task 03c)."""

    def test_no_pyyaml_import(self):
        src = (ROOT / "dist/.claude/skills/u-worker-compliance/scripts/check_worker.py").read_text()
        assert "import yaml" not in src
        assert "minimal_yaml" in src

    def test_parses_real_worker_frontmatter_skills(self):
        sys.path.insert(0, str(ROOT / "dist/.claude/skills/u-worker-compliance/scripts"))
        import check_worker
        fm = check_worker._parse_frontmatter(
            (ROOT / "dist/.claude/agents/dev/u-be-developer.md").read_text()
        )
        assert isinstance(fm, dict)
        assert fm.get("name") == "u-be-developer"
        assert "orch-report" in (fm.get("skills") or [])
