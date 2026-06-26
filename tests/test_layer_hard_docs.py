"""Layer Hard Docs — documentation/vocabulary reconciliation (task 13).

A7-F5 (mode event name — fixed in task 11), ESCALATION_CODES E18/E19 mislabel.
Note: the extras/WORKFLOW_REFERENCE.md checks (A7-F1 canonical ref, A7-F2
circuit window, A2-F3 recovery latency) were removed — that reference file is
no longer present in the repo.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent


class TestDocsReconciled:
    def test_no_orchestrator_emits_mode_declared(self):
        for md in (ROOT / "dist" / ".claude" / "agents").glob("orchestrator-*.md"):
            assert "event-type mode_declared" not in md.read_text(encoding="utf-8"), md.name

    def test_escalation_codes_e18_e19_documented(self):
        ec = (ROOT / "dist" / ".claude" / "ESCALATION_CODES.md").read_text(encoding="utf-8")
        assert "E18–E19" in ec, "E18/E19 must be documented as used, not lumped into Reserved"
