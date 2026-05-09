"""Layer 1 — Frontmatter: validates agent file frontmatter fields and model."""
import pytest
from conftest import get_top_level_agent_files, parse_frontmatter

WORKER_REQUIRED_FIELDS = ["name", "description", "user-invocable", "model"]
ORCHESTRATOR_REQUIRED_FIELDS = ["name", "description", "model"]
ALLOWED_MODELS = [
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-haiku-4-5-20251001",
]


def _classify_files():
    orchestrators = []
    workers = []
    for f in get_top_level_agent_files():
        parts = list(f.parts)
        idx = parts.index("agents")
        rel_parts = parts[idx + 1:]
        if len(rel_parts) == 1:
            orchestrators.append(f)
        else:
            workers.append(f)
    return orchestrators, workers


_orchestrator_files, _worker_files = _classify_files()


class TestLayer1Frontmatter:
    def test_discovery_sanity(self):
        assert len(get_top_level_agent_files()) > 0, "no agent files found"

    @pytest.mark.parametrize("path", _orchestrator_files, ids=[f.name for f in _orchestrator_files])
    def test_orchestrator_frontmatter_well_formed(self, path):
        fm = parse_frontmatter(path)
        for field in ORCHESTRATOR_REQUIRED_FIELDS:
            assert field in fm, f'"{field}" missing in {path.name}'
        assert fm.get("model") in ALLOWED_MODELS, \
            f'model "{fm.get("model")}" not allowed in {path.name}'
        assert fm.get("name") == path.stem, \
            f'name "{fm.get("name")}" != filename "{path.stem}"'

    @pytest.mark.parametrize("path", _worker_files, ids=[f.name for f in _worker_files])
    def test_worker_frontmatter_well_formed(self, path):
        fm = parse_frontmatter(path)
        for field in WORKER_REQUIRED_FIELDS:
            assert field in fm, f'"{field}" missing in {path.name}'
        assert fm.get("model") in ALLOWED_MODELS, \
            f'model "{fm.get("model")}" not allowed in {path.name}'
        assert isinstance(fm.get("user-invocable"), bool), \
            f"user-invocable must be boolean in {path.name}"
        assert fm.get("name") == path.stem, \
            f'name "{fm.get("name")}" != filename "{path.stem}"'
