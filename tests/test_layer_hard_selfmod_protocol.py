"""Layer Hard Self-Modification Protocol — framework fixes applied in recovery.

Eternal audit (E12 → seq ~818 → seq 831): a fix applied to .claude/lib/orch_core.py
mid-recovery left the working tree dirty and blocked the dev-exit clean-tree gate —
the engine tripped over its own recovery. The allowlist (clean_tree_gates) does not
cover this: a modified framework file is exactly the kind of dirt nobody allowlists.
The protocol rule: any edit under .claude/** made while resolving an escalation MUST
be committed (fix(orch): ...) in the same step, before the workflow resumes.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent

ORCHESTRATORS = [
    "orchestrator-sdd.md",
    "orchestrator-dev.md",
    "orchestrator-review.md",
    "orchestrator-test.md",
]


class TestSelfModificationProtocol:
    def test_every_orchestrator_has_the_protocol_note(self):
        for name in ORCHESTRATORS:
            src = (ROOT / "dist/.claude/agents" / name).read_text(encoding="utf-8")
            assert "Framework self-modification protocol (recovery)" in src, name
            assert 'git commit -m "fix(orch): <summary>"' in src, name

    def test_e12_suggested_actions_include_commit_guidance(self):
        for name in ORCHESTRATORS:
            src = (ROOT / "dist/.claude/agents" / name).read_text(encoding="utf-8")
            e12_lines = [l for l in src.splitlines()
                         if 'E12_state_reduction_failed","severity":"critical"' in l]
            assert e12_lines, f"{name}: no critical E12 block"
            for line in e12_lines:
                assert "commit it in the same step" in line, (
                    f"{name}: E12 suggested_actions missing the commit rule"
                )

    def test_note_names_both_clean_tree_gates(self):
        """The rule must say WHICH gates the dirty file blocks — actionable, not vague."""
        for name in ORCHESTRATORS:
            src = (ROOT / "dist/.claude/agents" / name).read_text(encoding="utf-8")
            note = src.split("Framework self-modification protocol (recovery)")[1].split("\n\n")[0]
            assert "all_branches_integrated_to_main" in note, name
            assert "qa_runs_on_integrated_main" in note, name
