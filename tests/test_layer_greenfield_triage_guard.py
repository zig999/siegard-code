"""F-06 — greenfield triage guard (regression).

Field incident (2026-06-19): a /u-spec run for a brand-new domain was classified
`implementation_only_no_spec_change` and skipped spec authoring entirely. The
guard now in u-spec-triage forces `spec_change_required` whenever no domain spec
exists. These tests lock that contract in the published SKILL.md so a future edit
cannot silently reintroduce the misclassification.

The triage logic is executed by an LLM worker from prose (SKILL.md), so the
binding regression here is structural: the SKILL.md must (a) detect greenfield by
the absence of domain spec files, and (b) deterministically set
type=spec_change_required for greenfield — never implementation_only.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dist" / ".claude" / "lib"))

DIST = Path(__file__).parent.parent / "dist" / ".claude"
TRIAGE = DIST / "skills" / "u-spec-triage" / "SKILL.md"


def _text():
    return TRIAGE.read_text(encoding="utf-8")


class TestGreenfieldGuardContract:
    def test_skill_exists(self):
        assert TRIAGE.exists(), "u-spec-triage/SKILL.md must be published"

    def test_greenfield_detected_by_absence_of_domain_specs(self):
        t = _text()
        # The detection clause: domains/ absent or with no spec files → greenfield true
        assert "Detect greenfield" in t
        assert re.search(r"domains/.*(absent|no spec files)", t), \
            "greenfield must be derived from the absence of domain spec files"

    def test_greenfield_forces_spec_change_required(self):
        t = _text()
        # Locate the `If greenfield: true` block and assert it sets spec_change_required.
        idx = t.find("If `greenfield: true`")
        assert idx != -1, "greenfield:true branch must exist"
        block = t[idx: idx + 1200]
        assert "type: spec_change_required" in block, \
            "greenfield:true must set type: spec_change_required"

    def test_greenfield_never_maps_to_implementation_only(self):
        t = _text()
        idx = t.find("If `greenfield: true`")
        block = t[idx: idx + 1200]
        assert "implementation_only" not in block, \
            "greenfield:true must never be classified implementation_only"


class TestTriageStackClassifierPresent:
    """The deterministic stack classifier (P0 fix) backs the front/back legs."""

    def test_classifier_script_published(self):
        script = DIST / "skills" / "u-spec-triage" / "scripts" / "classify_stack.py"
        assert script.exists(), "classify_stack.py must ship with the triage skill"
