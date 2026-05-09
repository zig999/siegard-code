"""Layer 4 — Controlled Vocabulary: banned terms must not appear in agent files."""
import re
import pytest
from conftest import get_all_agent_files

BANNED_TERMS = [
    (re.compile(r"\bappropriate\b", re.IGNORECASE), "appropriate"),
    (re.compile(r"\bplease\b", re.IGNORECASE), "please"),
    (re.compile(r"\bif possible\b", re.IGNORECASE), "if possible"),
    (re.compile(r"\bbetter\b", re.IGNORECASE), "better"),
]

_agent_files = get_all_agent_files()


def _extract_violations(file_path):
    lines = file_path.read_text(encoding="utf-8").split("\n")
    violations = []
    in_frontmatter = False

    for i, line in enumerate(lines):
        trimmed = line.strip()
        if i == 0 and trimmed == "---":
            in_frontmatter = True
            continue
        if in_frontmatter and trimmed == "---":
            in_frontmatter = False
            continue
        if in_frontmatter:
            continue
        if trimmed.startswith("#") or trimmed.startswith("<!--"):
            continue

        for pattern, term in BANNED_TERMS:
            if pattern.search(line):
                violations.append({"line": i + 1, "term": term, "content": trimmed[:100]})

    return violations


class TestLayer4Vocabulary:
    def test_finds_agent_files_to_scan(self):
        assert len(_agent_files) > 0

    @pytest.mark.parametrize("path", _agent_files, ids=[f.name for f in _agent_files])
    def test_no_banned_terms(self, path):
        violations = _extract_violations(path)
        report = "\n".join(
            f'  L{v["line"]} ["{v["term"]}"]: {v["content"]}'
            for v in violations
        )
        assert len(violations) == 0, f"Banned terms in {path.name}:\n{report}"
