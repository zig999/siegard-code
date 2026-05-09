"""Unified conftest — orch_core fixtures + dist artifact helpers."""
import json
import os
import re
import sys
from pathlib import Path

import pytest
import yaml
import jsonschema

# ─── Paths ────────────────────────────────────────────────────────────────────

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
DIST_DIR = _REPO_ROOT / "dist" / ".claude"
FIXTURES_DIR = _TESTS_DIR / "fixtures"

_LIB = _REPO_ROOT / "dist" / ".claude" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

# ─── Dist artifact helpers ────────────────────────────────────────────────────


def get_dist_dir() -> Path:
    return DIST_DIR


def parse_frontmatter(file_path: Path) -> dict:
    content = Path(file_path).read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def load_yaml(file_path: Path) -> object:
    return yaml.safe_load(Path(file_path).read_text(encoding="utf-8"))


def load_fixture(relative_path: str) -> object:
    return load_yaml(FIXTURES_DIR / relative_path)


def walk_dir(directory: Path, ext: str | None = None) -> list[Path]:
    results = []
    if not directory.exists():
        return results
    for entry in sorted(directory.rglob("*")):
        if entry.is_file():
            if ext is None or entry.suffix == ext:
                results.append(entry)
    return results


def get_all_agent_files() -> list[Path]:
    return walk_dir(DIST_DIR / "agents", ".md")


def get_top_level_agent_files() -> list[Path]:
    return [
        f for f in get_all_agent_files()
        if "protocols" not in f.parts and not f.name.endswith("-protocols.md")
    ]


def get_protocol_index_files() -> list[Path]:
    return [
        f for f in get_all_agent_files()
        if "protocols" not in f.parts and f.name.endswith("-protocols.md")
    ]


def get_protocol_content_files() -> list[Path]:
    return [f for f in get_all_agent_files() if "protocols" in f.parts]


def get_all_skill_dirs() -> list[dict]:
    skills_dir = DIST_DIR / "skills"
    if not skills_dir.exists():
        return []
    return [
        {"name": d.name, "path": d}
        for d in sorted(skills_dir.iterdir())
        if d.is_dir()
    ]


def get_all_schema_files() -> list[Path]:
    schema_dir = DIST_DIR / "skills" / "u-shared-templates"
    if not schema_dir.exists():
        return []
    return sorted(schema_dir.glob("*.schema.yaml"))


def _make_validator(schema: dict) -> jsonschema.Draft7Validator:
    return jsonschema.Draft7Validator(schema)


def validate(schema_file: Path, data: object) -> dict:
    schema = load_yaml(schema_file)
    validator = _make_validator(schema)
    errors = list(validator.iter_errors(data))
    return {"valid": len(errors) == 0, "errors": errors}


def compile_all_schemas() -> list[dict]:
    results = []
    for f in get_all_schema_files():
        try:
            schema = load_yaml(f)
            _make_validator(schema)
            results.append({"file": f, "compiled": True, "error": None})
        except Exception as exc:
            results.append({"file": f, "compiled": False, "error": str(exc)})
    return results


# ─── orch_core fixtures ───────────────────────────────────────────────────────


def build_task_created_data(
    phase: str = "sdd",
    tier: str = "standard",
    task_type: str = "spec",
    spec: str = "Do the thing",
    deps: list | None = None,
) -> dict:
    return {
        "phase": phase,
        "tier": tier,
        "type": task_type,
        "spec": spec,
        "deps": deps or [],
    }


@pytest.fixture
def orch_dir(tmp_path: Path):
    log_dir = tmp_path / ".orch"
    log_dir.mkdir()
    for sub in ("blobs", "state", "dlq", "audit", "metrics", "workers"):
        (log_dir / sub).mkdir()

    prev = os.environ.get("ORCH_PROJECT_DIR")
    os.environ["ORCH_PROJECT_DIR"] = str(tmp_path)

    import importlib
    import orch_core
    importlib.reload(orch_core)

    yield tmp_path

    if prev is None:
        os.environ.pop("ORCH_PROJECT_DIR", None)
    else:
        os.environ["ORCH_PROJECT_DIR"] = prev

    importlib.reload(orch_core)


@pytest.fixture
def make_event(orch_dir):
    import orch_core

    def _factory(
        event_type: str,
        *,
        agent: str = "test-agent",
        task_id: str | None = None,
        attempt: int = 1,
        data: dict | None = None,
    ):
        return orch_core.append_event(
            event_type=event_type,
            agent=agent,
            task_id=task_id,
            attempt=attempt,
            data=data or {},
        )

    return _factory


@pytest.fixture
def make_active_phase(make_event):
    _entered: set[str] = set()

    def _factory(phase: str = "sdd", order: int = 1, workflow_id: str = "wf-test"):
        if phase not in _entered:
            make_event("phase_declared", data={
                "workflow_id": workflow_id,
                "phases": [{"name": phase, "order": order, "required": True}],
            })
            make_event("phase_entered", data={
                "phase": phase, "order": order, "workflow_id": workflow_id,
            })
            _entered.add(phase)
        return phase

    return _factory


@pytest.fixture
def make_task(make_event, make_active_phase):
    def _factory(
        task_id: str = "task-001",
        phase: str = "sdd",
        tier: str = "standard",
        task_type: str = "spec",
        spec: str = "Do the thing",
        deps: list | None = None,
    ):
        make_active_phase(phase)
        make_event(
            "task_created",
            task_id=task_id,
            data={
                "phase": phase,
                "tier": tier,
                "type": task_type,
                "spec": spec,
                "deps": deps or [],
            },
        )
        return task_id

    return _factory
