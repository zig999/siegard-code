"""Layer 1 — Skill frontmatter: validates SKILL.md frontmatter for every skill directory.

Enforces the "Frontmatter standard (MANDATORY)" section of CLAUDE.md:
every directory under dist/.claude/skills/ ships a SKILL.md beginning with
valid YAML frontmatter (name == directory, description, user-invocable),
and allowed-tools lives in frontmatter only — never as a body prose section.
"""
import pytest
from conftest import get_all_skill_dirs, parse_frontmatter

SKILL_REQUIRED_FIELDS = ["name", "description", "user-invocable"]
MIN_DESCRIPTION_LENGTH = 30

_skill_dirs = get_all_skill_dirs()


class TestLayer1SkillFrontmatter:
    @pytest.mark.parametrize("skill", _skill_dirs, ids=[s["name"] for s in _skill_dirs])
    def test_skill_md_exists(self, skill):
        assert (skill["path"] / "SKILL.md").is_file(), \
            f'{skill["name"]}: SKILL.md missing — every skill directory must ship one'

    @pytest.mark.parametrize("skill", _skill_dirs, ids=[s["name"] for s in _skill_dirs])
    def test_frontmatter_well_formed(self, skill):
        fm = parse_frontmatter(skill["path"] / "SKILL.md")
        assert fm, f'{skill["name"]}: SKILL.md has no parseable YAML frontmatter'
        for field in SKILL_REQUIRED_FIELDS:
            assert field in fm, f'"{field}" missing in {skill["name"]}/SKILL.md'
        assert fm.get("name") == skill["name"], \
            f'name "{fm.get("name")}" != directory "{skill["name"]}"'
        assert isinstance(fm.get("user-invocable"), bool), \
            f'user-invocable must be boolean in {skill["name"]}/SKILL.md'

    @pytest.mark.parametrize("skill", _skill_dirs, ids=[s["name"] for s in _skill_dirs])
    def test_description_is_routing_grade(self, skill):
        fm = parse_frontmatter(skill["path"] / "SKILL.md")
        description = fm.get("description")
        assert isinstance(description, str) and len(description.strip()) >= MIN_DESCRIPTION_LENGTH, \
            f'{skill["name"]}: description must be a string of >= {MIN_DESCRIPTION_LENGTH} chars ' \
            f'(routing is driven by this field)'

    @pytest.mark.parametrize("skill", _skill_dirs, ids=[s["name"] for s in _skill_dirs])
    def test_no_allowed_tools_prose_section(self, skill):
        content = (skill["path"] / "SKILL.md").read_text(encoding="utf-8")
        assert "## allowed-tools" not in content, \
            f'{skill["name"]}: "## allowed-tools" prose section found — ' \
            f'allowed-tools belongs in frontmatter only (single source)'
