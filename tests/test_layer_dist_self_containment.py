"""Self-containment gate for shipped artifacts (dist migration, 2026-07-16).

Installation is a manual copy of dist/.claude/ into <target>/.claude/ — no
tooling runs at install time (CLAUDE.md §Installation). Any shipped .md that
references a path under the LAB's dist/ tree therefore points at a file that
does not exist in the target after the copy. Two live instances motivated this
gate: claude-md-target-template.md told the target author to paste
dist/claude-md-fragments/... (left behind by the copy), and
u-ui-design/SKILL.md referenced dist/skills/... (a path that exists nowhere).

The pattern matches dist/ ONLY when followed by a distribution-internal
component — mentions of a target project's own build-output directory
("node_modules/, dist/, build/") and lab-process prose ("promoting to dist/")
are legitimate and stay allowed.
"""
import re
from pathlib import Path

DIST_CLAUDE = Path(__file__).parent.parent / "dist" / ".claude"

_DIST_INTERNAL_REF = re.compile(
    r"dist/(\.claude|claude-md-fragments|skills|agents|commands|hooks|lib|scripts)\b"
)


def test_no_shipped_md_references_the_lab_dist_tree():
    offenders = []
    for md in sorted(DIST_CLAUDE.rglob("*.md")):
        if "__pycache__" in md.parts:
            continue
        text = md.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if _DIST_INTERNAL_REF.search(line):
                offenders.append(f"{md.relative_to(DIST_CLAUDE.parent.parent)}:{i}: {line.strip()}")
    assert not offenders, (
        "shipped artifacts must be self-contained — these lines reference the "
        "lab's dist/ tree, which does not exist in a target after the manual "
        "copy (write them as .claude/-relative paths instead):\n"
        + "\n".join(offenders)
    )


def test_fragment_directory_ships_inside_the_copy():
    """The fe-stack fragment is consumed at install time by the target author
    (claude-md-target-template.md §Stack — Frontend) — it must live inside the
    copied tree and stay referenced by an in-copy path."""
    fragment = DIST_CLAUDE / "claude-md-fragments" / "fe-stack-react-tailwind-tanstack.md"
    assert fragment.exists(), "fragment must ship inside dist/.claude/claude-md-fragments/"
    template = (DIST_CLAUDE / "claude-md-target-template.md").read_text(encoding="utf-8")
    assert ".claude/claude-md-fragments/fe-stack-react-tailwind-tanstack.md" in template
