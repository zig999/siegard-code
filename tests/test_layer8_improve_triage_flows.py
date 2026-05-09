"""Layer 8 — Improve & Triage Flow Invariants (IMPV-001 to IMPV-059)."""
import pytest
from conftest import load_fixture


def validate_improve_scope(data):
    errors = []
    scope = data.get("improve_scope")
    if not scope:
        errors.append("IMPV-000: improve_scope key missing from document root")
        return errors

    type_ = scope.get("type")
    spec_change_status = scope.get("spec_change_status")
    affected_specs = scope.get("affected_specs") or []
    estimated_task_contracts = scope.get("estimated_task_contracts")
    planner_required = scope.get("planner_required")
    planner_skip_reason = scope.get("planner_skip_reason")
    source = scope.get("source")
    generated_on = scope.get("generated_on")
    task_contracts = scope.get("task_contracts")

    if type_ == "implementation_only" and spec_change_status != "not_required":
        errors.append(
            f'IMPV-001: type=implementation_only requires spec_change_status=not_required, got "{spec_change_status}"'
        )

    if type_ == "spec_change_required" and spec_change_status not in (
        "completed", "divergence_accepted", "pending_spec", "failed"
    ):
        errors.append(
            f'IMPV-002: type=spec_change_required requires spec_change_status=completed|divergence_accepted|pending_spec|failed, got "{spec_change_status}"'
        )

    if type_ == "spec_change_required" and not affected_specs:
        errors.append("IMPV-003: type=spec_change_required requires at least one entry in affected_specs")

    if (
        planner_required is False
        and source != "spec-triage"
        and (not planner_skip_reason or not str(planner_skip_reason).strip())
    ):
        errors.append("IMPV-010: planner_required=false requires a non-empty planner_skip_reason")

    if planner_required is False and source != "spec-triage" and estimated_task_contracts != 1:
        errors.append(
            f"IMPV-011: planner_required=false requires estimated_task_contracts=1, got {estimated_task_contracts}"
        )

    if planner_required is True and planner_skip_reason not in (None, ""):
        errors.append("IMPV-012: planner_required=true must not include planner_skip_reason")

    if (
        estimated_task_contracts is not None
        and estimated_task_contracts > 1
        and source != "spec-triage"
        and planner_required is not True
    ):
        errors.append(
            f"IMPV-013: estimated_task_contracts={estimated_task_contracts} requires planner_required=true"
        )

    if source == "spec-triage":
        if spec_change_status != "completed":
            errors.append(
                f'IMPV-020: source=spec-triage requires spec_change_status=completed, got "{spec_change_status}"'
            )
        if not generated_on:
            errors.append("IMPV-021: source=spec-triage requires generated_on field")
        if task_contracts is not None:
            tc_count = len(task_contracts) if isinstance(task_contracts, list) else 0
            if estimated_task_contracts != tc_count:
                errors.append(
                    f"IMPV-022: source=spec-triage estimated_task_contracts ({estimated_task_contracts}) "
                    f"must equal len(task_contracts) ({tc_count})"
                )

    for i, spec in enumerate(affected_specs):
        if isinstance(spec, dict) and spec is not None:
            if not spec.get("path"):
                errors.append(f'IMPV-030: affected_specs[{i}] missing required field "path"')
            if not spec.get("sections") or not isinstance(spec["sections"], list) or len(spec["sections"]) == 0:
                errors.append(f'IMPV-031: affected_specs[{i}] missing or empty "sections" array')
            if not spec.get("change_summary"):
                errors.append(f'IMPV-030: affected_specs[{i}] missing required field "change_summary"')

    return errors


def resolves_pipeline_route(scope):
    improve_scope = scope["improve_scope"]
    planner_required = improve_scope.get("planner_required")
    source = improve_scope.get("source")
    spec_change_status = improve_scope.get("spec_change_status")

    blocked = spec_change_status in ("pending_spec", "failed")
    return {
        "lean": not blocked and planner_required is False,
        "full": not blocked and planner_required is True,
        "shortCircuit": source == "spec-triage" and spec_change_status == "completed",
        "blocked": blocked,
        "haltMode": (
            "Halt-await-spec" if spec_change_status == "pending_spec"
            else "Halt-spec-failed" if spec_change_status == "failed"
            else None
        ),
    }


class TestUimproveTypeSpecChangeStatusInvariants:
    def test_impv001_impl_only_status_completed_violation(self):
        data = load_fixture("invalid/improve-scope-impl-only-status-completed.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-001") for e in errors)

    def test_impv002_spec_change_required_status_not_required_violation(self):
        data = load_fixture("invalid/improve-scope-spec-required-status-not-required.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-002") for e in errors)

    def test_impv003_spec_change_required_empty_affected_violation(self):
        data = load_fixture("invalid/improve-scope-spec-required-empty-affected.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-003") for e in errors)


class TestUimprovePlannerRequiredInvariants:
    def test_impv010_planner_false_no_skip_reason_violation(self):
        data = load_fixture("invalid/improve-scope-lean-no-skip-reason.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-010") for e in errors)

    def test_impv011_planner_false_multi_tc_violation(self):
        data = load_fixture("invalid/improve-scope-lean-multi-tc.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-011") for e in errors)

    def test_impv012_planner_required_with_skip_reason_violation(self):
        data = load_fixture("invalid/improve-scope-planner-required-with-skip-reason.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-012") for e in errors)

    def test_impv013_multi_tc_planner_false_violation(self):
        data = load_fixture("invalid/improve-scope-multi-tc-planner-false.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-013") for e in errors)


class TestUspecTriageValidScopeBlocks:
    def test_spec_triage_always_has_completed_status(self):
        patch = load_fixture("valid/improve-scope-spec-triage-patch.yaml")
        structural = load_fixture("valid/improve-scope-spec-triage-structural.yaml")
        assert patch["improve_scope"]["spec_change_status"] == "completed"
        assert structural["improve_scope"]["spec_change_status"] == "completed"

    def test_spec_triage_estimated_tc_equals_task_contracts_length(self):
        data = load_fixture("valid/improve-scope-spec-triage-structural.yaml")
        scope = data["improve_scope"]
        assert scope["estimated_task_contracts"] == len(scope["task_contracts"])


class TestUspecTriageSpecificInvariants:
    def test_impv020_triage_divergence_accepted_violation(self):
        data = load_fixture("invalid/improve-scope-triage-divergence-accepted.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-020") for e in errors)

    def test_impv021_triage_no_generated_on_violation(self):
        data = load_fixture("invalid/improve-scope-triage-no-generated-on.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-021") for e in errors)

    def test_impv022_triage_tc_count_mismatch_violation(self):
        data = load_fixture("invalid/improve-scope-triage-tc-count-mismatch.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-022") for e in errors)

    def test_spec_triage_lean_no_impv010(self):
        data = load_fixture("valid/improve-scope-spec-triage-patch.yaml")
        scope = data["improve_scope"]
        assert scope["planner_required"] is False
        errors = validate_improve_scope(data)
        assert not any(e.startswith("IMPV-010") for e in errors)


class TestAffectedSpecsStructure:
    def test_impv030_missing_change_summary_violation(self):
        data = load_fixture("invalid/improve-scope-affected-spec-missing-summary.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-030") for e in errors)

    def test_valid_affected_specs_passes_impv030_and_031(self):
        data = load_fixture("valid/improve-scope-spec-change-completed.yaml")
        errors = [e for e in validate_improve_scope(data) if e.startswith(("IMPV-030", "IMPV-031"))]
        assert errors == []

    def test_spec_triage_string_paths_no_structure_required(self):
        data = load_fixture("valid/improve-scope-spec-triage-patch.yaml")
        errors = [e for e in validate_improve_scope(data) if e.startswith(("IMPV-030", "IMPV-031"))]
        assert errors == []


class TestPipelineRouting:
    def test_impl_only_planner_false_lean_pipeline(self):
        data = load_fixture("valid/improve-scope-implementation-only.yaml")
        route = resolves_pipeline_route(data)
        assert route["lean"] is True
        assert route["full"] is False

    def test_impl_only_planner_true_full_pipeline(self):
        data = load_fixture("valid/improve-scope-implementation-only-with-planner.yaml")
        route = resolves_pipeline_route(data)
        assert route["lean"] is False
        assert route["full"] is True

    def test_spec_change_completed_planner_true_full_pipeline(self):
        data = load_fixture("valid/improve-scope-spec-change-completed.yaml")
        route = resolves_pipeline_route(data)
        assert route["full"] is True

    def test_spec_change_completed_lean_pipeline(self):
        data = load_fixture("valid/improve-scope-spec-change-completed-lean.yaml")
        route = resolves_pipeline_route(data)
        assert route["lean"] is True

    def test_spec_triage_completed_short_circuits(self):
        data = load_fixture("valid/improve-scope-spec-triage-patch.yaml")
        route = resolves_pipeline_route(data)
        assert route["shortCircuit"] is True

    def test_non_triage_does_not_short_circuit(self):
        data = load_fixture("valid/improve-scope-spec-change-completed.yaml")
        route = resolves_pipeline_route(data)
        assert route["shortCircuit"] is False

    def test_divergence_accepted_no_short_circuit(self):
        data = load_fixture("valid/improve-scope-divergence-accepted.yaml")
        route = resolves_pipeline_route(data)
        assert route["shortCircuit"] is False

    def test_pending_spec_blocked_halt_await_spec(self):
        data = load_fixture("valid/improve-scope-pending-spec.yaml")
        route = resolves_pipeline_route(data)
        assert route["blocked"] is True
        assert route["lean"] is False
        assert route["full"] is False
        assert route["haltMode"] == "Halt-await-spec"

    def test_failed_blocked_halt_spec_failed(self):
        data = load_fixture("valid/improve-scope-spec-failed.yaml")
        route = resolves_pipeline_route(data)
        assert route["blocked"] is True
        assert route["lean"] is False
        assert route["full"] is False
        assert route["haltMode"] == "Halt-spec-failed"

    def test_completed_not_blocked_no_halt(self):
        data = load_fixture("valid/improve-scope-spec-change-completed.yaml")
        route = resolves_pipeline_route(data)
        assert route["blocked"] is False
        assert route["haltMode"] is None


class TestTransientAndFailureStates:
    def test_impv001_impl_only_pending_spec_violation(self):
        data = load_fixture("invalid/improve-scope-impl-only-pending-spec.yaml")
        errors = validate_improve_scope(data)
        assert any(e.startswith("IMPV-001") for e in errors)


VALID_FIXTURES = [
    "valid/improve-scope-implementation-only.yaml",
    "valid/improve-scope-implementation-only-with-planner.yaml",
    "valid/improve-scope-spec-change-completed.yaml",
    "valid/improve-scope-spec-change-completed-lean.yaml",
    "valid/improve-scope-divergence-accepted.yaml",
    "valid/improve-scope-spec-triage-patch.yaml",
    "valid/improve-scope-spec-triage-structural.yaml",
    "valid/improve-scope-pending-spec.yaml",
    "valid/improve-scope-spec-failed.yaml",
]

INVALID_FIXTURES = [
    "invalid/improve-scope-impl-only-status-completed.yaml",
    "invalid/improve-scope-spec-required-status-not-required.yaml",
    "invalid/improve-scope-spec-required-empty-affected.yaml",
    "invalid/improve-scope-lean-no-skip-reason.yaml",
    "invalid/improve-scope-lean-multi-tc.yaml",
    "invalid/improve-scope-planner-required-with-skip-reason.yaml",
    "invalid/improve-scope-multi-tc-planner-false.yaml",
    "invalid/improve-scope-triage-divergence-accepted.yaml",
    "invalid/improve-scope-triage-no-generated-on.yaml",
    "invalid/improve-scope-triage-tc-count-mismatch.yaml",
    "invalid/improve-scope-affected-spec-missing-summary.yaml",
    "invalid/improve-scope-impl-only-pending-spec.yaml",
]


class TestSchemaCompleteness:
    @pytest.mark.parametrize("fixture_path", VALID_FIXTURES)
    def test_valid_fixture_no_violations(self, fixture_path):
        data = load_fixture(fixture_path)
        assert validate_improve_scope(data) == []

    @pytest.mark.parametrize("fixture_path", INVALID_FIXTURES)
    def test_invalid_fixture_at_least_one_violation(self, fixture_path):
        data = load_fixture(fixture_path)
        assert len(validate_improve_scope(data)) > 0
