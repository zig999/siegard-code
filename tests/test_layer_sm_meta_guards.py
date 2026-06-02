"""Layer SM — meta-orchestrator transversal guards (M1, M2, M3, M9).

Task 02 of the sm-refactor plan (extras/sm-refactor/tasks/02-meta-guards.md).
Red phase: tests must fail before META_TRANSITIONS / MetaStateMachine exist.

Decisions covered:
    M1 — infra check gate (preflight/integrity/circuit blocked → block)
    M2 — state derivation error (reduce.py / current_phase.py error → escalate)
    M3 — run_status derivation (raw_run_status + phases[] → status)
    M9 — E13 retry escalation (e13_retry_count 0/1/≥2 → backoff/critical)
"""
import sys
from pathlib import Path

import pytest

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
sys.path.insert(0, str(DIST_LIB))


class TestMetaInfraGate:
    """M1 — Infra check gate."""

    def setup_method(self):
        from orch_core import META_TRANSITIONS, MetaStateMachine

        self.sm = MetaStateMachine(META_TRANSITIONS)

    def test_M1_preflight_blocked(self):
        r = self.sm.evaluate(
            "post_infra",
            {"preflight_status": "blocked", "integrity_status": "ok", "circuit_status": "ok"},
        )
        assert r.name == "block"
        assert r.params.get("reason") == "preflight_failed"

    def test_M1_integrity_blocked(self):
        r = self.sm.evaluate(
            "post_infra",
            {"preflight_status": "ok", "integrity_status": "blocked", "circuit_status": "ok"},
        )
        assert r.name == "block"
        assert r.params.get("reason") == "integrity_failed"

    def test_M1_circuit_blocked(self):
        r = self.sm.evaluate(
            "post_infra",
            {"preflight_status": "ok", "integrity_status": "ok", "circuit_status": "blocked"},
        )
        assert r.name == "block"
        assert r.params.get("reason") == "circuit_failed"

    def test_M1_all_ok_proceeds(self):
        r = self.sm.evaluate(
            "post_infra",
            {"preflight_status": "ok", "integrity_status": "ok", "circuit_status": "ok"},
        )
        assert r.name != "block"


class TestMetaStateDerivationError:
    """M2 — State derivation error."""

    def setup_method(self):
        from orch_core import META_TRANSITIONS, MetaStateMachine

        self.sm = MetaStateMachine(META_TRANSITIONS)

    def test_M2_reduce_error(self):
        r = self.sm.evaluate(
            "post_state", {"reduce_status": "error", "current_phase_status": "ok"}
        )
        assert r.name == "error"
        assert r.params.get("reason") == "state_derivation_failed"
        assert r.params.get("source") == "reduce.py"

    def test_M2_current_phase_error(self):
        r = self.sm.evaluate(
            "post_state", {"reduce_status": "ok", "current_phase_status": "error"}
        )
        assert r.name == "error"
        assert r.params.get("source") == "current_phase.py"

    def test_M2_both_ok_proceeds(self):
        r = self.sm.evaluate(
            "post_state", {"reduce_status": "ok", "current_phase_status": "ok"}
        )
        assert r.name != "error"


class TestMetaRunStatusDerivation:
    """M3 — run_status derivation."""

    def setup_method(self):
        from orch_core import META_TRANSITIONS, MetaStateMachine

        self.sm = MetaStateMachine(META_TRANSITIONS)

    def test_M3_escalated_overrides(self):
        r = self.sm.evaluate(
            "derive_run_status",
            {
                "raw_run_status": "escalated",
                "phases": [{"required": True, "status": "completed"}],
            },
        )
        assert r.name == "set_run_status"
        assert r.params["run_status"] == "escalated"

    def test_M3_completed_when_all_required_done(self):
        r = self.sm.evaluate(
            "derive_run_status",
            {
                "raw_run_status": "active",
                "phases": [
                    {"required": True, "status": "completed"},
                    {"required": True, "status": "completed"},
                ],
            },
        )
        assert r.params["run_status"] == "completed"

    def test_M3_pending_when_phases_empty(self):
        r = self.sm.evaluate(
            "derive_run_status", {"raw_run_status": "active", "phases": []}
        )
        assert r.params["run_status"] == "pending"

    def test_M3_active_when_some_required_pending(self):
        r = self.sm.evaluate(
            "derive_run_status",
            {
                "raw_run_status": "active",
                "phases": [
                    {"required": True, "status": "completed"},
                    {"required": True, "status": "active"},
                ],
            },
        )
        assert r.params["run_status"] == "active"

    def test_M3_completed_ignores_non_required_pending(self):
        r = self.sm.evaluate(
            "derive_run_status",
            {
                "raw_run_status": "active",
                "phases": [
                    {"required": True, "status": "completed"},
                    {"required": False, "status": "active"},
                ],
            },
        )
        assert r.params["run_status"] == "completed"


class TestMetaE13RetryEscalation:
    """M9 — E13 retry escalation."""

    def setup_method(self):
        from orch_core import META_TRANSITIONS, MetaStateMachine

        self.sm = MetaStateMachine(META_TRANSITIONS)

    def test_M9_first_retry_uses_30s_backoff(self):
        r = self.sm.evaluate("subagent_invalid", {"e13_retry_count": 0})
        assert r.name == "retry_with_backoff"
        assert r.params["backoff_seconds"] == 30
        assert r.params["severity"] == "warning"
        assert r.params["code"] == "E13"

    def test_M9_second_retry_uses_60s_backoff(self):
        r = self.sm.evaluate("subagent_invalid", {"e13_retry_count": 1})
        assert r.name == "retry_with_backoff"
        assert r.params["backoff_seconds"] == 60
        assert r.params["severity"] == "warning"

    def test_M9_third_invalid_escalates_critical(self):
        r = self.sm.evaluate("subagent_invalid", {"e13_retry_count": 2})
        assert r.name == "escalate_critical"
        assert r.params["severity"] == "critical"
        assert r.params["code"] == "E13"

    def test_M9_higher_counts_still_escalate_critical(self):
        r = self.sm.evaluate("subagent_invalid", {"e13_retry_count": 5})
        assert r.name == "escalate_critical"


class TestMetaMachineRegistered:
    def test_meta_in_registered_machines(self):
        import json
        import subprocess

        result = subprocess.run(
            ["python3", str(DIST_LIB / "sm_runner.py"), "--list"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "meta" in data["registered_machines"]
