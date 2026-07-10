"""Protocol conformance for the /u-supervise command (E2 / B(b)).

Guards the foreground-only contract (CLAUDE.md): the supervisor re-invokes the meta-
orchestrator, which needs Bash in the foreground, so the command MUST fail-fast on E_NO_BASH
and MUST NOT spawn the orchestrator in the background. It must also run the deterministic tick
and record the resume for budget accounting.
"""
from pathlib import Path

import pytest

COMMANDS = Path(__file__).resolve().parents[1] / "dist" / ".claude" / "commands"
CMD = COMMANDS / "u-supervise.md"


@pytest.fixture(scope="module")
def text():
    return CMD.read_text(encoding="utf-8")


def test_command_exists():
    assert CMD.is_file(), "dist/.claude/commands/u-supervise.md is missing"


def test_valid_frontmatter(text):
    assert text.startswith("---\n"), "command must start with YAML frontmatter"
    end = text.index("\n---", 3)
    front = text[4:end]
    assert "description:" in front, "frontmatter must carry a description"


def test_step0_bash_failfast(text):
    # Step 0 must guard the foreground/Bash precondition and name E_NO_BASH.
    assert "check_bash_available" in text
    assert "E_NO_BASH" in text


def test_runs_supervisor_tick(text):
    assert "supervisor_tick.py" in text


def test_records_resume_for_budget(text):
    # Must emit orchestrator_resumed so the per-phase budget accounting works.
    assert "orchestrator_resumed" in text


def test_never_backgrounds_the_orchestrator(text):
    # The orchestrator must run in the foreground (has Bash). The doc must explicitly
    # forbid backgrounding it.
    lowered = text.lower()
    # It must be mentioned only to forbid it — require the explicit prohibition phrase.
    assert "not `run_in_background`" in lowered


def test_race_recheck_before_reinvoke(text):
    # R3 fix: re-derive and confirm the stall before spawning a second meta.
    assert "reduce.py" in text
    assert "recovered" in text.lower()
