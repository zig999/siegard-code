"""Layer — Least privilege (P6) enforcement gates.

Turns the least-privilege posture into CI invariants (same pattern as the
W01-W06 worker-compliance gate): a bug class fixed once must be impossible to
reintroduce silently.

Gates:
  LP1 — Reviewer/scanner agents must not carry `Edit`. A reviewer reads
        delivered (untrusted) code and produces findings; granting it the
        tool to modify the code it audits is a privilege inversion and a
        prompt-injection escalation vector. `Write` stays allowed (findings
        artifact); `Bash` stays allowed (emit.py terminal-event protocol,
        W03/W06).
  LP2 — The shipped settings.json must carry a non-empty permissions.deny
        list (headless runs have no interactive permission fallback).
  LP3 — Every skill that ships a scripts/ directory must declare
        `allowed-tools` in its SKILL.md frontmatter (frontmatter standard:
        mandatory when the skill executes tools).
"""
import json

import pytest
from conftest import DIST_DIR, get_all_agent_files, parse_frontmatter

# Agents whose role is to audit/scan and produce findings — never to modify
# the artifacts under review. Matched by name suffix.
_REVIEWER_SUFFIXES = ("-reviewer",)


def _reviewer_agents():
    return [
        f for f in get_all_agent_files()
        if f.stem.endswith(_REVIEWER_SUFFIXES)
    ]


class TestLP1ReviewersCannotEdit:
    def test_reviewer_agents_exist(self):
        assert len(_reviewer_agents()) >= 3  # security, architecture, spec

    @pytest.mark.parametrize(
        "path", _reviewer_agents(), ids=lambda p: p.stem,
    )
    def test_reviewer_has_no_edit_tool(self, path):
        fm = parse_frontmatter(path)
        tools = fm.get("tools") or []
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",")]
        assert "Edit" not in tools, (
            f"{path.name}: reviewer/scanner agents must not carry Edit "
            f"(privilege inversion — LP1). Tools: {tools}"
        )


class TestLP2SettingsDenyList:
    def test_settings_has_nonempty_deny_list(self):
        settings = json.loads(
            (DIST_DIR / "settings.json").read_text(encoding="utf-8")
        )
        deny = settings.get("permissions", {}).get("deny")
        assert isinstance(deny, list) and len(deny) > 0, (
            "settings.json must ship a non-empty permissions.deny list (LP2)"
        )

    def test_deny_covers_privilege_escalation(self):
        settings = json.loads(
            (DIST_DIR / "settings.json").read_text(encoding="utf-8")
        )
        deny = settings.get("permissions", {}).get("deny", [])
        assert any(d.startswith("Bash(sudo") for d in deny), (
            "deny list must cover sudo (no Siegard workflow needs root)"
        )


class TestLP3ScriptSkillsDeclareAllowedTools:
    @pytest.mark.parametrize(
        "skill_dir",
        sorted(
            d for d in (DIST_DIR / "skills").iterdir()
            if d.is_dir() and (d / "scripts").is_dir()
        ),
        ids=lambda d: d.name,
    )
    def test_script_bearing_skill_declares_allowed_tools(self, skill_dir):
        fm = parse_frontmatter(skill_dir / "SKILL.md")
        assert fm.get("allowed-tools"), (
            f"{skill_dir.name}: ships scripts/ but SKILL.md frontmatter has "
            f"no allowed-tools (frontmatter standard / P6 — LP3)"
        )
