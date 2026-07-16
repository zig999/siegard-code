"""Recommendation #3, 2026-07-15 workflow audit (C3 — "/u-improve implementation_only
livelock").

The `exit_no_spec_change` branch (type == implementation_only) emitted
phase_exit_approved + phase_transitioned and returned, but never closed the
spec_change_status loop — unlike the normal Step 6 path, which emits
spec_pipeline_return and rewrites improve-scope.json's spec_change_status to
"completed". For a u-improve workflow classified implementation_only,
improve-scope.json stayed "pending_spec" forever, and orchestrator-dev's R4 guard
(workflow_type == "improve" AND spec_change_status == "pending_spec") blocked
indefinitely — no further SDD work would ever run to advance it. The only
escape was the manual band-aid scripts/fix_stuck_improve.py.

Confirmed as a recognized invalid steady-state by the existing schema-linter
fixture tests/fixtures/invalid/improve-scope-impl-only-pending-spec.yaml
(TestTransientAndFailureStates::test_impv001_impl_only_pending_spec_violation,
tests/test_layer8_improve_triage_flows.py).

These are prompt-level contracts (orchestrator-sdd.md is executed by the LLM, not
by this test suite), so this gate asserts the wiring is present in the shipped
artifact — matching the house pattern in test_f2_handoff_mode.py.
"""
import re

from conftest import get_dist_dir

dist = get_dist_dir()
ORCH = (dist / "agents" / "orchestrator-sdd.md").read_text(encoding="utf-8")

# Isolate the exit_no_spec_change branch: from its header to the next top-level
# "**If ..." / "**Derive ..." branch marker that follows it.
_BRANCH = re.search(
    r'\*\*If `\$ACTION == "exit_no_spec_change"`:\*\*(.*?)\n\*\*Derive `effective_mode`',
    ORCH, re.DOTALL,
)


class TestExitNoSpecChangeClosesSpecChangeStatusLoop:
    def test_branch_exists_and_is_isolated(self):
        assert _BRANCH is not None, (
            "could not isolate the exit_no_spec_change branch — orchestrator-sdd.md "
            "structure changed; update this test's anchor regex"
        )

    def test_branch_emits_spec_pipeline_return_gated_on_improve(self):
        branch = _BRANCH.group(1)
        assert 'trigger == "u-improve"' in branch, (
            "exit_no_spec_change must gate the spec_change_status close-out on "
            "trigger == u-improve, exactly like the Step 6 path does"
        )
        assert '--event-type spec_pipeline_return' in branch, (
            "exit_no_spec_change never emits spec_pipeline_return — a u-improve "
            "workflow classified implementation_only leaves improve-scope.json "
            "stuck at pending_spec forever (R4 guard in orchestrator-dev blocks "
            "indefinitely)"
        )
        assert '"spec_change_status":"completed"' in branch, (
            "spec_pipeline_return in this branch must set spec_change_status to "
            "completed, matching the Step 6 close-out"
        )

    def test_branch_rewrites_improve_scope_json_on_disk(self):
        branch = _BRANCH.group(1)
        assert "improve-scope.json" in branch, (
            "orchestrator-dev's R4 guard reads spec_change_status from the on-disk "
            "improve-scope.json, not from the log — the branch must rewrite it "
            "(mirrors the Step 6 close-out script), or the guard keeps blocking "
            "even after spec_pipeline_return lands in the log"
        )
        assert "scope['spec_change_status'] = 'completed'" in branch

    def test_branch_still_transitions_to_dev(self):
        """The pre-existing forward-transition behavior must be untouched."""
        branch = _BRANCH.group(1)
        assert '"from_phase":"sdd","to_phase":"dev"' in branch
