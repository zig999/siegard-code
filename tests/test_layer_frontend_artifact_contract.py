"""F-07 — front ↔ validator design-system contract alignment.

The validator blocks the handoff on the 5 design-system files + design-system-rules.md
synced to tokens.md (rules 10/12b, blocking). The front spec agent must produce and
sync those on its FIRST pass, or every frontend wave incurs a guaranteed INVALID +
repair round. These tests lock the single source of truth and its references.
"""
from pathlib import Path

DIST = Path(__file__).parent.parent / "dist" / ".claude"
SSOT = DIST / "skills" / "u-spec-templates" / "FRONTEND-MANDATORY-ARTIFACTS.md"
FRONT = DIST / "agents" / "spec" / "u-spec-front.md"
VALIDATOR = DIST / "agents" / "spec" / "u-spec-validator.md"

REQUIRED_FILES = [
    "_index.md", "tokens.md", "composition.md", "components.md", "implementation.md",
    "design-system-rules.md",
]


def _read(p):
    return p.read_text(encoding="utf-8")


class TestSingleSourceOfTruth:
    def test_ssot_exists(self):
        assert SSOT.exists(), "FRONTEND-MANDATORY-ARTIFACTS.md must be published"

    def test_ssot_lists_every_required_file(self):
        t = _read(SSOT)
        for f in REQUIRED_FILES:
            assert f in t, f"SSOT must list {f}"

    def test_ssot_states_blocking_rules_membership(self):
        t = _read(SSOT)
        assert "12b" in t and "blocking" in t.lower()


class TestProducerSelfChecks:
    def test_front_references_ssot(self):
        assert "FRONTEND-MANDATORY-ARTIFACTS.md" in _read(FRONT), \
            "u-spec-front must reference the shared contract"

    def test_front_step5_checks_rules_tokens_sync(self):
        t = _read(FRONT)
        # The self-verification checklist must include the 12b blocking sync,
        # so the producer catches it before the validator does.
        assert "12b" in t
        assert "design-system-rules.md" in t and "tokens.md" in t


class TestGateReferencesSsot:
    def test_validator_references_ssot(self):
        assert "FRONTEND-MANDATORY-ARTIFACTS.md" in _read(VALIDATOR), \
            "u-spec-validator must reference the shared contract"

    def test_validator_keeps_12b_blocking(self):
        t = _read(VALIDATOR)
        idx = t.find("12b. **Design system rules sync")
        assert idx != -1, "rule 12b definition must exist"
        assert "blocking" in t[idx: idx + 400].lower()


class TestTemplatesExistForFirstPass:
    def test_design_system_templates_present(self):
        ds = DIST / "skills" / "u-spec-templates" / "TEMPLATE.design-system"
        for f in ("_index.md", "tokens.md", "composition.md", "components.md", "implementation.md"):
            assert (ds / f).exists(), f"template {f} required for first-pass creation"
        assert (DIST / "skills" / "u-spec-templates" / "TEMPLATE.design-system-rules.md").exists()
