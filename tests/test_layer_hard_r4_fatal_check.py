"""R4 fatal-check wiring (2026-07-15 post-fix audit, item "E05/E06 phase key").

orchestrator-dev.md's R4 guard detects a fatally-terminated SDD pipeline with
`read_events_filtered(event_type=escalation, phase='sdd')` and matches codes
E05_rejection_cycle_limit / E06_dispatch_loop_limit. The payloads
orchestrator-sdd.md prescribed carried NO `phase` key, so the filter dropped
them and `sdd_pipeline_fatal` was always false — the E_r4_spec_pipeline_failed
diagnosis was unreachable, and an improve flow whose SDD died on E05/E06
looped on "blocked: re-invoke after sdd completes" with no diagnosis, forever.

Pins (a) the payload templates and (b) the functional round-trip through the
exact filter the R4 guard runs.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SDD_MD = ROOT / "dist/.claude/agents/orchestrator-sdd.md"
sys.path.insert(0, str(ROOT / "dist/.claude/lib"))

_FATAL_CODES = ("E05_rejection_cycle_limit", "E06_dispatch_loop_limit")


class TestEscalationPayloadTemplates:
    def test_e05_and_e06_payload_templates_carry_phase_sdd(self):
        text = SDD_MD.read_text(encoding="utf-8")
        for code in _FATAL_CODES:
            payload_lines = [
                line for line in text.splitlines()
                if f'"code":"{code}"' in line
            ]
            assert payload_lines, f"no emission payload found for {code}"
            for line in payload_lines:
                assert '"phase":"sdd"' in line, (
                    f"{code} payload lost the phase key — orchestrator-dev's R4 "
                    "fatal-check filters escalations by phase='sdd' and would "
                    "never see it (dead diagnosis, undiagnosed improve block loop)"
                )


class TestR4FilterRoundTrip:
    def _r4_fatal(self, orch_core):
        """The exact query orchestrator-dev.md R4 runs."""
        terminal = orch_core.read_events_filtered(
            event_type=orch_core.EventType.ESCALATION.value, phase="sdd")
        return [e for e in terminal if e.data.get("code") in _FATAL_CODES]

    def test_documented_e05_payload_is_found_by_r4_filter(self, orch_dir):
        import orch_core
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="escalation",
            data={"code": "E05_rejection_cycle_limit", "phase": "sdd",
                  "severity": "critical",
                  "reason": "spec-validator exceeded rejection cycle limit",
                  "evidence": [1],
                  "suggested_actions": ["inspect spec"]})
        fatal = self._r4_fatal(orch_core)
        assert len(fatal) == 1
        assert fatal[0].data["code"] == "E05_rejection_cycle_limit"

    def test_documented_e06_payload_is_found_by_r4_filter(self, orch_dir):
        import orch_core
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="escalation",
            data={"code": "E06_dispatch_loop_limit", "phase": "sdd",
                  "severity": "critical",
                  "reason": "dispatch loop safety limit",
                  "evidence": [1],
                  "suggested_actions": ["inspect log"]})
        assert len(self._r4_fatal(orch_core)) == 1

    def test_phaseless_escalation_is_invisible_to_r4(self, orch_dir):
        """Enshrines WHY the key is load-bearing: the pre-fix payload (no phase)
        is dropped by the filter — exactly the dead branch this fix revives."""
        import orch_core
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="escalation",
            data={"code": "E05_rejection_cycle_limit",
                  "severity": "critical", "reason": "r", "evidence": [1],
                  "suggested_actions": []})
        assert self._r4_fatal(orch_core) == []


class TestDivergenceAcceptedFastPath:
    """divergence_accepted dead-end (2026-07-15 post-fix audit, 5.3).

    E_r4_spec_pipeline_failed's own suggested action #3 tells the operator to
    set spec_change_status=divergence_accepted and run /u-dev — but Step 2
    branched only on pending_spec and not_required, so the value fell through
    to the standard path requiring check_handoff_manifest_approved: exactly the
    manifest a fatally-terminated SDD never produced (loop back to the same
    block), or a STALE manifest from an earlier workflow consumed silently.
    The remediation value must be handled by the no-manifest fast path.
    """

    DEV_MD = ROOT / "dist/.claude/agents/orchestrator-dev.md"

    def test_fast_path_branch_covers_divergence_accepted(self):
        text = self.DEV_MD.read_text(encoding="utf-8")
        branch_headers = [
            line for line in text.splitlines()
            if line.startswith("**If") and "spec_change_status" in line
            and "not_required" in line
        ]
        assert branch_headers, "no-manifest fast-path branch header not found"
        assert any('"divergence_accepted"' in line for line in branch_headers), (
            "the no-manifest fast path does not cover divergence_accepted — the "
            "R4 escalation's own remediation loops back into the manifest gate"
        )

    def test_every_remediation_status_value_has_a_branch(self):
        """Every spec_change_status=<value> the prompt tells an operator to set
        must be a value some Step 2 branch header handles."""
        import re
        text = self.DEV_MD.read_text(encoding="utf-8")
        prescribed = set(re.findall(r"spec_change_status=(\w+)", text))
        branch_headers = "\n".join(
            line for line in text.splitlines()
            if line.startswith("**If") and "spec_change_status" in line
        )
        for value in prescribed:
            assert value in branch_headers, (
                f"prompt prescribes setting spec_change_status={value} but no "
                "Step 2 branch header handles that value (dead-end remediation)"
            )

    def test_manifest_gate_still_required_for_standard_path(self):
        text = self.DEV_MD.read_text(encoding="utf-8")
        assert "check_handoff_manifest_approved.py" in text
