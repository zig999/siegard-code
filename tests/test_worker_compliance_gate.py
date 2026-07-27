"""Worker compliance gate (audit C4).

Runs the previously-unenforced validator u-worker-compliance/check_worker.py over
the framework's own agent .md files and fails CI if any shipped worker drifts from
the orchestration protocol (rules W01–W08: terminal events, canonical phase values,
register_worker arguments, orch-report skill declaration, exit-criteria gate fields).

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
            f"{_rel(agent)} violates the worker protocol (W01–W08): "
            + "; ".join(
                f"[{v.severity}] {v.rule}: {v.detail}" for v in result.violations
            )
        )

class TestW08GateFieldsDeclared:
    """W08 — a field an exit-criteria checker reads must be named by its producer.

    Origin: `documentation_verified` lived only in the qa-report template. The QA
    worker completed the review without it and the review phase blocked with E08 —
    correct work, incomplete record, one human round-trip lost.
    """

    def test_registry_is_not_empty(self):
        assert check_worker.GATE_FIELDS_BY_WORKER, "the artifact -> checker registry is empty"

    def test_every_registered_worker_exists_in_dist(self):
        """A stale registry entry silently checks nothing — catch the typo here."""
        stems = {p.stem for p in AGENT_FILES}
        unknown = sorted(set(check_worker.GATE_FIELDS_BY_WORKER) - stems)
        assert not unknown, f"registry names workers that do not exist under dist/: {unknown}"

    def test_every_named_checker_exists(self):
        """The registry doubles as documentation — the checker paths must be real."""
        checkers = {
            c for pairs in check_worker.GATE_FIELDS_BY_WORKER.values() for _, c in pairs
        }
        found = {p.name for p in (dist / "skills").rglob("check_*.py")}
        missing = sorted(checkers - found)
        assert not missing, f"registry names checkers that do not exist: {missing}"

    @pytest.mark.parametrize(
        "stem,field",
        [(s, f) for s, pairs in check_worker.GATE_FIELDS_BY_WORKER.items() for f, _ in pairs],
        ids=[
            f"{s}:{f}"
            for s, pairs in check_worker.GATE_FIELDS_BY_WORKER.items()
            for f, _ in pairs
        ],
    )
    def test_gate_field_is_declared_by_producer(self, stem, field):
        agent = next(p for p in AGENT_FILES if p.stem == stem)
        assert field in agent.read_text(encoding="utf-8"), (
            f"{_rel(agent)} never names gate field '{field}'"
        )

    def test_rule_fires_when_field_is_absent(self, tmp_path):
        """Negative case — without this, a broken rule would pass the suite silently."""
        stem, pairs = next(iter(check_worker.GATE_FIELDS_BY_WORKER.items()))
        field = pairs[0][0]
        src = next(p for p in AGENT_FILES if p.stem == stem).read_text(encoding="utf-8")
        target = tmp_path / f"{stem}.md"
        target.write_text(src.replace(field, "renamed_away"), encoding="utf-8")

        result = check_worker.check_file(target)
        assert result.status == "fail"
        assert any(v.rule == "W08" and field in v.detail for v in result.violations)

    def test_rule_is_silent_for_unregistered_workers(self, tmp_path):
        target = tmp_path / "u-not-in-registry.md"
        target.write_text("# nothing here\n", encoding="utf-8")
        assert not check_worker._check_w08_gate_fields_declared(
            target.read_text(encoding="utf-8"), target
        )
