"""Layer Hard Docs — documentation/vocabulary reconciliation (task 13).

A7-F1 (CLAUDE.md canonical ref dangling), A7-F2 (retry/circuit config drift),
A7-F5 (mode event name — fixed in task 11), ESCALATION_CODES E18/E19 mislabel.
monitor.py uncommitted diff + slide/ untracked: LEFT in place per user decision.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


class TestDocsReconciled:
    def test_claude_md_canonical_ref_resolves(self):
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        m = re.search(r"Canonical reference:\s*`([^`]+)`", claude)
        assert m, "no canonical reference line in CLAUDE.md"
        assert "architecture.md" not in m.group(1), "dangling architecture.md pointer must be gone"
        assert (ROOT / m.group(1)).exists(), f"canonical ref {m.group(1)} does not exist"

    def test_no_orchestrator_emits_mode_declared(self):
        for md in (ROOT / "dist" / ".claude" / "agents").glob("orchestrator-*.md"):
            assert "event-type mode_declared" not in md.read_text(encoding="utf-8"), md.name

    def test_workflow_reference_circuit_window_aligned_to_config(self):
        wf = (ROOT / "extras" / "WORKFLOW_REFERENCE.md").read_text(encoding="utf-8")
        assert "10 min" in wf, "circuit window must match default_config (10 min), not the old 5 min"

    def test_escalation_codes_e18_e19_documented(self):
        ec = (ROOT / "dist" / ".claude" / "ESCALATION_CODES.md").read_text(encoding="utf-8")
        assert "E18–E19" in ec, "E18/E19 must be documented as used, not lumped into Reserved"

    def test_recovery_latency_documented(self):  # task 14 (A2-F3, Option A)
        wf = (ROOT / "extras" / "WORKFLOW_REFERENCE.md").read_text(encoding="utf-8")
        assert "Recuperação e latência" in wf
        assert "ilimitada" in wf.lower() and "re-invoc" in wf.lower()
