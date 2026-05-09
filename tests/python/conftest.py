"""Shared pytest fixtures for Siegard orch_core test suite."""
import json
import os
import sys
from pathlib import Path

import pytest

# Inject lib path so `import orch_core` works without installation.
_LIB = Path(__file__).resolve().parents[2] / "dist" / ".claude" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))


@pytest.fixture
def orch_dir(tmp_path: Path):
    """
    Provides an isolated ORCH_PROJECT_DIR backed by tmp_path.
    Creates the full .orch/ directory tree and injects the env var.
    Restores the environment after each test.
    """
    log_dir = tmp_path / ".orch"
    log_dir.mkdir()
    (log_dir / "blobs").mkdir()
    (log_dir / "state").mkdir()
    (log_dir / "dlq").mkdir()
    (log_dir / "audit").mkdir()
    (log_dir / "metrics").mkdir()
    (log_dir / "workers").mkdir()

    prev = os.environ.get("ORCH_PROJECT_DIR")
    os.environ["ORCH_PROJECT_DIR"] = str(tmp_path)

    # Reload module-level path constants so they pick up the new env var.
    import importlib
    import orch_core
    importlib.reload(orch_core)

    yield tmp_path

    if prev is None:
        os.environ.pop("ORCH_PROJECT_DIR", None)
    else:
        os.environ["ORCH_PROJECT_DIR"] = prev

    # Reload again to restore previous state.
    importlib.reload(orch_core)


@pytest.fixture
def make_event(orch_dir):
    """
    Factory that calls orch_core.append_event with sensible defaults.
    Returns the appended Event.
    """
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
    """
    Declares and enters a phase so tasks created with that phase name become READY.
    Returns the phase name.
    """
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
    """
    Declares/enters a phase then creates a task_created event.
    Returns the task_id.
    Tasks are auto-promoted to READY because the phase is active.
    """
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
