"""Layer SM — orchestrator-sdd Targeted routing + Validation Repair Loop (S10, S11, S16).

Task 09 of the sm-refactor plan (extras/sm-refactor/tasks/09-sdd-targeted-repair.md).
Red phase: tests must fail before S10/S11/S16 transitions are added.

Decisions covered:
    S10 — Domain worker type by path keyword (front/component → spec-front; back/.back.md/domains → spec-back)
    S11 — Structural diff routing (domain_worker_required → writer+reviewer | reviewer-only)
    S16 — Validation Repair Loop (R1-R3: count cycles, detect INVALID domains, dispatch | escalate E08)
"""
import sys
from pathlib import Path

import pytest

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
sys.path.insert(0, str(DIST_LIB))


class TestSddTargetedPathClassification:
    """S10 — Domain worker type by path keyword."""

    def setup_method(self):
        from orch_core import SDD_TRANSITIONS, SddStateMachine

        self.sm = SddStateMachine(SDD_TRANSITIONS)

    @pytest.mark.parametrize(
        "path,expected_type",
        [
            ("front/components/button.component.spec.md", "spec-front"),
            ("front/features/login.feature.spec.md", "spec-front"),
            ("specs/front/screens/dashboard.spec.md", "spec-front"),
            ("back/auth.back.md", "spec-back"),
            ("specs/back/billing.back.md", "spec-back"),
            ("domains/auth/openapi.yaml", "spec-back"),
            ("domains/auth/auth.spec.md", "spec-back"),
        ],
    )
    def test_S10_path_to_worker_type(self, path, expected_type):
        r = self.sm.evaluate("targeted_classify_path", {"spec_path": path})
        assert r.name == "set_domain_worker_type"
        assert r.params["domain_task_type"] == expected_type
        assert r.params["spec_path"] == path

    def test_S10_ambiguous_path_defaults_to_front(self):
        r = self.sm.evaluate("targeted_classify_path", {"spec_path": "misc/unclassified.md"})
        assert r.name == "set_domain_worker_type"
        assert r.params["domain_task_type"] == "spec-front"


class TestSddStructuralDiffRouting:
    """S11 — Structural diff routing."""

    def setup_method(self):
        from orch_core import SDD_TRANSITIONS, SddStateMachine

        self.sm = SddStateMachine(SDD_TRANSITIONS)

    def test_S11_domain_worker_required_creates_two_tasks(self):
        r = self.sm.evaluate(
            "targeted_dispatch_decision",
            {"domain_worker_required": True, "domain_task_type": "spec-back"},
        )
        assert r.name == "create_writer_and_reviewer"
        assert r.params["pipeline"] == ["spec-back", "spec-reviewer"]
        assert r.params["domain_task_type"] == "spec-back"

    def test_S11_domain_worker_required_spec_front(self):
        r = self.sm.evaluate(
            "targeted_dispatch_decision",
            {"domain_worker_required": True, "domain_task_type": "spec-front"},
        )
        assert r.name == "create_writer_and_reviewer"
        assert r.params["pipeline"] == ["spec-front", "spec-reviewer"]

    def test_S11_text_only_change_creates_only_reviewer(self):
        r = self.sm.evaluate(
            "targeted_dispatch_decision",
            {"domain_worker_required": False, "domain_task_type": "spec-front"},
        )
        assert r.name == "create_reviewer_only"
        assert r.params["pipeline"] == ["spec-reviewer"]


class TestValidationRepairLoop:
    """S16 — Validation Repair Loop (R1: count cycles, R2: detect INVALID, R3: dispatch | escalate)."""

    def setup_method(self):
        from orch_core import SDD_TRANSITIONS, SddStateMachine

        self.sm = SddStateMachine(SDD_TRANSITIONS)

    def test_S16_cycles_0_with_invalid_dispatches(self):
        r = self.sm.evaluate(
            "exit_criteria_failed",
            {
                "effective_mode": "standard",
                "repair_cycles": 0,
                "invalid_domains": ["auth", "billing"],
            },
        )
        assert r.name == "dispatch_repair_pipeline"
        assert r.params["repair_cycle_n"] == 1
        assert r.params["domains"] == ["auth", "billing"]
        assert r.params["pipeline"] == ["spec-writer", "spec-reviewer", "spec-back", "spec-validator"]

    def test_S16_cycles_1_still_dispatches(self):
        r = self.sm.evaluate(
            "exit_criteria_failed",
            {
                "effective_mode": "standard",
                "repair_cycles": 1,
                "invalid_domains": ["auth"],
            },
        )
        assert r.name == "dispatch_repair_pipeline"
        assert r.params["repair_cycle_n"] == 2

    # ── Stage-granular repair (conservative): defect_origins → per-domain pipelines ──

    FULL = ["spec-writer", "spec-reviewer", "spec-back", "spec-validator"]
    REDUCED = ["spec-back", "spec-validator"]

    def _dispatch(self, invalid, origins):
        return self.sm.evaluate(
            "exit_criteria_failed",
            {
                "effective_mode": "standard",
                "repair_cycles": 0,
                "invalid_domains": invalid,
                "defect_origins": origins,
            },
        )

    def test_S16_back_origin_gets_reduced_pipeline(self):
        r = self._dispatch(["chat"], {"chat": "back"})
        assert r.params["pipelines"] == {"chat": self.REDUCED}

    def test_S16_unknown_origin_falls_back_to_full(self):
        """Mis-attribution must degrade to redundant work, never under-repair."""
        r = self._dispatch(["chat"], {"chat": None})
        assert r.params["pipelines"] == {"chat": self.FULL}

    def test_S16_non_back_origins_full(self):
        for origin in ("writer", "front", "cross-domain", "reviewer"):
            r = self._dispatch(["chat"], {"chat": origin})
            assert r.params["pipelines"] == {"chat": self.FULL}, origin

    def test_S16_mixed_domains_independent_pipelines(self):
        """Eternal audit shape: chat back-only defect, ingestion unattributed —
        chat repairs 2 stages, ingestion keeps the full pipeline."""
        r = self._dispatch(["chat", "ingestion"], {"chat": "back", "ingestion": None})
        assert r.params["pipelines"] == {"chat": self.REDUCED, "ingestion": self.FULL}
        # Repair scope is exactly the invalid set — never a neighboring domain.
        assert set(r.params["pipelines"]) == set(r.params["domains"]) == {"chat", "ingestion"}

    def test_S16_missing_defect_origins_is_legacy_full(self):
        """Backward compatible: no defect_origins input → full pipeline everywhere."""
        r = self.sm.evaluate(
            "exit_criteria_failed",
            {"effective_mode": "standard", "repair_cycles": 0,
             "invalid_domains": ["auth", "billing"]},
        )
        assert r.params["pipelines"] == {"auth": self.FULL, "billing": self.FULL}
        assert r.params["pipeline"] == self.FULL  # legacy key preserved

    def test_S16_cycles_2_escalates(self):
        r = self.sm.evaluate(
            "exit_criteria_failed",
            {
                "effective_mode": "standard",
                "repair_cycles": 2,
                "invalid_domains": ["auth"],
            },
        )
        assert r.name == "escalate_e08"
        assert r.params.get("code") == "E08_exit_criteria_not_met"
        assert r.params.get("reason") == "max_repair_cycles_reached"

    def test_S16_targeted_mode_skips_repair(self):
        r = self.sm.evaluate(
            "exit_criteria_failed",
            {
                "effective_mode": "targeted",
                "repair_cycles": 0,
                "invalid_domains": ["auth"],
            },
        )
        assert r.name == "escalate_e08"
        assert r.params.get("reason") == "non_standard_mode"

    def test_S16_no_invalid_domains_escalates(self):
        r = self.sm.evaluate(
            "exit_criteria_failed",
            {
                "effective_mode": "standard",
                "repair_cycles": 0,
                "invalid_domains": [],
            },
        )
        assert r.name == "escalate_e08"
        assert r.params.get("reason") == "no_repairable_invalid_domains"

    def test_S16_e08_includes_repair_cycles_attempted(self):
        r = self.sm.evaluate(
            "exit_criteria_failed",
            {"effective_mode": "standard", "repair_cycles": 2, "invalid_domains": ["x"]},
        )
        assert r.name == "escalate_e08"
        assert r.params.get("repair_cycles_attempted") == 2
