"""Worker compliance gate (audit C4).

Runs the previously-unenforced validator u-worker-compliance/check_worker.py over
the framework's own agent .md files and fails CI if any shipped worker drifts from
the orchestration protocol (rules W01–W06: terminal events, canonical phase values,
register_worker arguments, orch-report skill declaration).

Before this gate existed, u-test-runner.md and u-spec-triage.md had silently
accumulated W03/W06 violations — exactly the drift this test now blocks.
"""
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
_SCRIPTS = dist / "skills" / "u-worker-compliance" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import check_worker  # noqa: E402

AGENT_FILES = sorted((dist / "agents").rglob("*.md"))


def _rel(p: Path) -> str:
    return str(p.relative_to(dist)).replace("\\", "/")


class TestWorkerComplianceGate:
    def test_agent_files_present(self):
        assert AGENT_FILES, "no agent .md files found under dist/.claude/agents"

    @pytest.mark.parametrize("agent", AGENT_FILES, ids=[_rel(p) for p in AGENT_FILES])
    def test_worker_protocol_compliance(self, agent):
        result = check_worker.check_file(agent)
        assert result.status == "pass", (
            f"{_rel(agent)} violates the worker protocol (W01–W06): "
            + "; ".join(
                f"[{v.severity}] {v.rule}: {v.detail}" for v in result.violations
            )
        )
