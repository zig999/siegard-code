"""Layer 5 — Flow Invariants: business rule validators for artifact cross-consistency."""
import pytest
from conftest import load_fixture


# ─── Business Rule Validators ─────────────────────────────────────────────────

def validate_validation_result(data):
    errors = []
    status = data["status"]
    blocking_count = data["blocking_count"]
    warning_count = data["warning_count"]
    handoff_allowed = data["handoff_allowed"]
    blocking_issues = data["blocking_issues"]
    warnings = data["warnings"]
    validation = data["validation"]

    if status == "VALID" and blocking_count == 0 and handoff_allowed is not True:
        errors.append("FLOW-001: status=VALID + blocking_count=0 requires handoff_allowed=true")
    if (status == "INVALID" or blocking_count > 0) and handoff_allowed is not False:
        errors.append("FLOW-002: status=INVALID or blocking_count>0 requires handoff_allowed=false")
    if blocking_count != len(blocking_issues):
        errors.append(
            f"FLOW-003: blocking_count ({blocking_count}) != blocking_issues.length ({len(blocking_issues)})"
        )
    if warning_count != len(warnings):
        errors.append(
            f"FLOW-004: warning_count ({warning_count}) != warnings.length ({len(warnings)})"
        )
    if validation.get("mode") == "incremental_back" and handoff_allowed is True:
        errors.append("FLOW-005: incremental_back mode cannot have handoff_allowed=true")

    blocking_ids = [i["id"] for i in blocking_issues]
    duplicates = {x for x in blocking_ids if blocking_ids.count(x) > 1}
    if duplicates:
        errors.append(f"FLOW-051: duplicate blocking_issue IDs: {', '.join(sorted(duplicates))}")

    warning_ids = [w["id"] for w in warnings]
    dup_warnings = {x for x in warning_ids if warning_ids.count(x) > 1}
    if dup_warnings:
        errors.append(f"FLOW-052: duplicate warning IDs: {', '.join(sorted(dup_warnings))}")

    return errors


def validate_task_contract_readiness(tc, completed_ids=None):
    errors = []
    completed_ids = completed_ids or []
    deps = tc["task_contract"].get("dependencies") or []
    unmet = [d for d in deps if d not in completed_ids]
    if unmet:
        errors.append(f"FLOW-040: TC blocked — unmet dependencies: {', '.join(unmet)}")
    return errors


def validate_blocked_report(data):
    errors = []
    status = data["status"]
    missing_inputs = data.get("missing_inputs") or []
    conflicts = data.get("conflicts") or []
    resolution = data["resolution"]

    if status == "blocked":
        if not missing_inputs:
            errors.append("FLOW-010: status=blocked requires missing_inputs with at least one entry")
        if conflicts:
            errors.append("FLOW-011: status=blocked must not populate conflicts — use missing_inputs")
        if resolution.get("escalate_to") != "orchestrator":
            errors.append("FLOW-014: status=blocked must escalate_to orchestrator")

    if status == "failed":
        if not conflicts:
            errors.append("FLOW-012: status=failed requires conflicts with at least one entry")
        if missing_inputs:
            errors.append("FLOW-013: status=failed must not populate missing_inputs — use conflicts")
        if resolution.get("escalate_to") != "human":
            errors.append("FLOW-015: status=failed must escalate_to human")

    return errors


def validate_cr(data):
    errors = []
    resolution = data["resolution"]
    if resolution["status"] == "open" and resolution.get("timestamp") != "":
        errors.append("FLOW-020: resolution.status=open requires timestamp to be empty string")
    if resolution["status"] in ("accepted", "rejected", "deferred") and not resolution.get("timestamp"):
        errors.append("FLOW-021: resolved CR requires a non-empty resolution.timestamp")
    return errors


def validate_cr_handoff_gate(cr):
    errors = []
    is_blocking = cr["resolution"]["status"] == "open" and cr["impact"].get("dev_blocked") is True
    if is_blocking:
        errors.append(
            f"FLOW-025: CR {cr['id']} is open and dev_blocked=true — handoff delivery must be halted"
        )
    return errors


HANDOFF_SUMMARY_TYPE_MAP = {
    "major_evolution": ["major"],
    "fast_track": ["patch", "minor"],
    "reverse_eng": ["patch", "minor", "major"],
}
REQUIRED_BACKEND_ARTIFACTS = ["openapi", "back-spec"]


def validate_handoff_manifest(data):
    errors = []
    handoff = data["handoff"]
    domains = data.get("domains") or []
    backend_package = data.get("backend_package") or []
    change_summary = data.get("change_summary")

    if handoff.get("delivered_by") != "u-spec-orchestrator":
        errors.append(f'FLOW-030: delivered_by must be "u-spec-orchestrator", got "{handoff.get("delivered_by")}"')
    if not domains:
        errors.append("FLOW-031: handoff must contain at least one domain")
    if not backend_package:
        errors.append("FLOW-032: handoff must include at least one backend_package entry")
    if handoff.get("type") == "new_domain" and change_summary is not None:
        errors.append("FLOW-033: new_domain handoff must not include change_summary")
    if handoff.get("type") in ("major_evolution", "fast_track", "reverse_eng") and not change_summary:
        errors.append(f"FLOW-034: {handoff.get('type')} handoff requires change_summary")
    if change_summary and change_summary.get("dev_impact") not in (
        None, "no_action", "reevaluate_task_contracts", "stop_domain_task_contracts"
    ):
        errors.append(f'FLOW-035: change_summary.dev_impact "{change_summary.get("dev_impact")}" is not valid')
    if change_summary and handoff.get("type") in HANDOFF_SUMMARY_TYPE_MAP:
        allowed = HANDOFF_SUMMARY_TYPE_MAP[handoff["type"]]
        if change_summary.get("type") not in allowed:
            errors.append(
                f'FLOW-036: {handoff["type"]} requires change_summary.type in [{", ".join(allowed)}], '
                f'got "{change_summary.get("type")}"'
            )
    if backend_package and handoff.get("type") in ("new_domain", "major_evolution"):
        present = [p["artifact"] for p in backend_package]
        for required in REQUIRED_BACKEND_ARTIFACTS:
            if required not in present:
                errors.append(
                    f'FLOW-037: backend_package missing required artifact "{required}" for {handoff.get("type")}'
                )

    return errors


def validate_chain(validation_result, handoff_manifest):
    errors = []
    validation = validation_result["validation"]
    status = validation_result["status"]
    handoff_allowed = validation_result["handoff_allowed"]
    domains = handoff_manifest.get("domains") or []

    if validation.get("mode") != "final_complete":
        errors.append(f'FLOW-060: handoff requires final_complete validation, got "{validation.get("mode")}"')
    if status != "VALID" or not handoff_allowed:
        errors.append("FLOW-061: handoff-manifest cannot derive from non-VALID or handoff_allowed=false validation")
    matching_domain = next((d for d in domains if d["name"] == validation.get("domain")), None)
    if not matching_domain:
        errors.append(f'FLOW-062: domain "{validation.get("domain")}" from validation_result not found in handoff-manifest')
    if matching_domain and matching_domain.get("spec_version") != validation.get("artifact_version"):
        errors.append(
            f'FLOW-063: version mismatch — validation_result v{validation.get("artifact_version")} '
            f'!= handoff-manifest v{matching_domain.get("spec_version")}'
        )
    return errors


def validate_be_to_fe_handoff(data):
    errors = []
    be_phase_status = data["be_phase_status"]
    known_deviations_count = data["known_deviations_count"]
    api_contract_status = data["api_contract_status"]
    endpoints = data.get("endpoints") or []

    if be_phase_status == "complete" and known_deviations_count != 0:
        errors.append(
            f"FLOW-070: be_phase_status=complete requires known_deviations_count=0, got {known_deviations_count}"
        )
    if be_phase_status == "complete_with_deviations" and known_deviations_count == 0:
        errors.append("FLOW-071: be_phase_status=complete_with_deviations requires known_deviations_count>0")

    has_endpoint_deviation = any(e.get("status") == "done_with_deviations" for e in endpoints)
    if api_contract_status == "has_deviations" and not has_endpoint_deviation:
        errors.append(
            "FLOW-072: api_contract_status=has_deviations requires at least one endpoint with status=done_with_deviations"
        )
    if api_contract_status == "up_to_date" and has_endpoint_deviation:
        errors.append(
            "FLOW-073: api_contract_status=up_to_date cannot have endpoints with status=done_with_deviations"
        )

    return errors


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestValidationResult:
    def test_valid_passes_all_flow_rules(self):
        data = load_fixture("valid/validation-result.yaml")
        assert validate_validation_result(data) == []

    def test_invalid_handoff_true_triggers_flow002(self):
        data = load_fixture("invalid/validation-result-invalid-handoff-true.yaml")
        errors = validate_validation_result(data)
        assert any(e.startswith("FLOW-002") for e in errors)

    def test_valid_blocking_count_triggers_flow002_or_003(self):
        data = load_fixture("invalid/validation-result-valid-blocking.yaml")
        errors = validate_validation_result(data)
        assert any(e.startswith("FLOW-002") or e.startswith("FLOW-003") for e in errors)

    def test_warnings_do_not_block_handoff(self):
        data = load_fixture("valid/validation-result-with-warnings.yaml")
        assert validate_validation_result(data) == []
        assert data["handoff_allowed"] is True
        assert data["warning_count"] > 0
        assert data["blocking_count"] == 0

    def test_incremental_back_handoff_true_triggers_flow005(self):
        data = load_fixture("invalid/validation-result-incremental-handoff-true.yaml")
        errors = validate_validation_result(data)
        assert any(e.startswith("FLOW-005") for e in errors)

    def test_duplicate_blocking_ids_triggers_flow051(self):
        data = load_fixture("invalid/validation-result-duplicate-issue-ids.yaml")
        errors = validate_validation_result(data)
        assert any(e.startswith("FLOW-051") for e in errors)


class TestBlockedReport:
    def test_valid_blocked_report_passes_all_rules(self):
        data = load_fixture("valid/blocked-report.yaml")
        assert validate_blocked_report(data) == []

    def test_blocked_escalates_to_orchestrator(self):
        data = load_fixture("valid/blocked-report.yaml")
        assert data["resolution"]["escalate_to"] == "orchestrator"

    def test_failed_escalates_to_human_violation_flow015(self):
        data = load_fixture("invalid/blocked-failed-escalate-to-orchestrator.yaml")
        errors = validate_blocked_report(data)
        assert any(e.startswith("FLOW-015") for e in errors)

    def test_blocked_without_missing_inputs_flow010(self):
        data = load_fixture("invalid/blocked-status-blocked-no-missing.yaml")
        errors = validate_blocked_report(data)
        assert any(e.startswith("FLOW-010") for e in errors)

    def test_blocked_with_conflicts_flow011(self):
        data = load_fixture("invalid/blocked-status-blocked-with-conflicts.yaml")
        errors = validate_blocked_report(data)
        assert any(e.startswith("FLOW-011") for e in errors)

    def test_failed_without_conflicts_flow012(self):
        data = load_fixture("invalid/blocked-status-failed-no-conflicts.yaml")
        errors = validate_blocked_report(data)
        assert any(e.startswith("FLOW-012") for e in errors)

    def test_failed_with_missing_inputs_flow013(self):
        data = load_fixture("invalid/blocked-status-failed-with-missing-inputs.yaml")
        errors = validate_blocked_report(data)
        assert any(e.startswith("FLOW-013") for e in errors)


class TestChangeRequest:
    def test_open_cr_with_empty_timestamp_passes(self):
        data = load_fixture("valid/cr.yaml")
        assert validate_cr(data) == []

    def test_accepted_cr_with_timestamp_passes(self):
        data = load_fixture("valid/cr-accepted.yaml")
        assert validate_cr(data) == []

    def test_cr_dev_not_blocked_does_not_block_task(self):
        data = load_fixture("valid/cr-dev-not-blocked.yaml")
        task_blocked = data["resolution"]["status"] == "open" and data["impact"].get("dev_blocked") is True
        assert task_blocked is False

    def test_open_cr_with_timestamp_flow020(self):
        data = load_fixture("invalid/cr-open-with-timestamp.yaml")
        errors = validate_cr(data)
        assert any(e.startswith("FLOW-020") for e in errors)

    def test_rejected_cr_no_timestamp_flow021(self):
        data = load_fixture("invalid/cr-rejected-no-timestamp.yaml")
        errors = validate_cr(data)
        assert any(e.startswith("FLOW-021") for e in errors)

    def test_deferred_cr_no_timestamp_flow021(self):
        data = load_fixture("invalid/cr-deferred-no-timestamp.yaml")
        errors = validate_cr(data)
        assert any(e.startswith("FLOW-021") for e in errors)

    def test_open_cr_dev_blocked_triggers_flow025(self):
        data = load_fixture("invalid/cr-blocking-handoff.yaml")
        errors = validate_cr_handoff_gate(data)
        assert any(e.startswith("FLOW-025") for e in errors)

    def test_open_cr_dev_not_blocked_no_flow025(self):
        data = load_fixture("valid/cr-dev-not-blocked.yaml")
        assert validate_cr_handoff_gate(data) == []

    def test_accepted_cr_dev_blocked_no_flow025(self):
        data = load_fixture("valid/cr-accepted.yaml")
        assert validate_cr_handoff_gate(data) == []


class TestHandoffManifest:
    def test_new_domain_manifest_passes_all_rules(self):
        data = load_fixture("valid/handoff-manifest.yaml")
        assert validate_handoff_manifest(data) == []

    def test_empty_domains_flow031(self):
        data = load_fixture("invalid/handoff-manifest-empty-domains.yaml")
        errors = validate_handoff_manifest(data)
        assert any(e.startswith("FLOW-031") for e in errors)

    def test_empty_backend_package_flow032(self):
        data = load_fixture("invalid/handoff-manifest-no-backend-package.yaml")
        errors = validate_handoff_manifest(data)
        assert any(e.startswith("FLOW-032") for e in errors)

    def test_wrong_delivered_by_flow030(self):
        data = load_fixture("invalid/handoff-manifest-wrong-sender.yaml")
        errors = validate_handoff_manifest(data)
        assert any(e.startswith("FLOW-030") for e in errors)

    def test_major_evolution_with_change_summary_passes(self):
        data = load_fixture("valid/handoff-manifest-major-evolution.yaml")
        assert validate_handoff_manifest(data) == []

    def test_fast_track_with_change_summary_passes(self):
        data = load_fixture("valid/handoff-manifest-fast-track.yaml")
        assert validate_handoff_manifest(data) == []

    def test_major_evolution_without_change_summary_flow034(self):
        data = load_fixture("invalid/handoff-manifest-major-evolution-no-change-summary.yaml")
        errors = validate_handoff_manifest(data)
        assert any(e.startswith("FLOW-034") for e in errors)

    def test_new_domain_with_change_summary_flow033(self):
        data = load_fixture("invalid/handoff-manifest-new-domain-with-change-summary.yaml")
        errors = validate_handoff_manifest(data)
        assert any(e.startswith("FLOW-033") for e in errors)

    def test_major_evolution_dev_impact_stop(self):
        data = load_fixture("valid/handoff-manifest-major-evolution.yaml")
        assert data["change_summary"]["dev_impact"] == "stop_domain_task_contracts"

    def test_fast_track_dev_impact_reevaluate(self):
        data = load_fixture("valid/handoff-manifest-fast-track.yaml")
        assert data["change_summary"]["dev_impact"] == "reevaluate_task_contracts"

    def test_new_domain_with_frontend_passes(self):
        data = load_fixture("valid/handoff-manifest-with-frontend.yaml")
        assert validate_handoff_manifest(data) == []
        assert data.get("frontend_artifacts") is not None
        assert data.get("frontend_package") is not None

    def test_fast_track_patch_no_action_passes(self):
        data = load_fixture("valid/handoff-manifest-fast-track-patch.yaml")
        assert validate_handoff_manifest(data) == []
        assert data["change_summary"]["dev_impact"] == "no_action"
        assert data["change_summary"]["type"] == "patch"

    def test_major_evolution_wrong_type_flow036(self):
        data = load_fixture("invalid/handoff-manifest-major-wrong-type.yaml")
        errors = validate_handoff_manifest(data)
        assert any(e.startswith("FLOW-036") for e in errors)

    def test_fast_track_wrong_type_flow036(self):
        data = load_fixture("invalid/handoff-manifest-fast-track-wrong-type.yaml")
        errors = validate_handoff_manifest(data)
        assert any(e.startswith("FLOW-036") for e in errors)

    def test_missing_backend_artifact_flow037(self):
        data = load_fixture("invalid/handoff-manifest-incomplete-backend.yaml")
        errors = validate_handoff_manifest(data)
        assert any(e.startswith("FLOW-037") for e in errors)


class TestSpecToDevChain:
    def test_matching_vr_and_hm_pass_chain_rules(self):
        vr = load_fixture("valid/validation-result.yaml")
        hm = load_fixture("valid/handoff-manifest.yaml")
        assert validate_chain(vr, hm) == []

    def test_version_mismatch_flow063(self):
        vr = load_fixture("valid/validation-result.yaml")
        hm = load_fixture("invalid/handoff-manifest-version-mismatch.yaml")
        errors = validate_chain(vr, hm)
        assert any(e.startswith("FLOW-063") for e in errors)

    def test_incremental_back_cannot_gate_handoff_flow060(self):
        vr = load_fixture("invalid/validation-result-incremental-handoff-true.yaml")
        hm = load_fixture("valid/handoff-manifest.yaml")
        errors = validate_chain(vr, hm)
        assert any(e.startswith("FLOW-060") for e in errors)

    def test_invalid_vr_cannot_gate_handoff_flow061(self):
        vr = load_fixture("invalid/validation-result-invalid-handoff-true.yaml")
        hm = load_fixture("valid/handoff-manifest.yaml")
        errors = validate_chain(vr, hm)
        assert any(e.startswith("FLOW-061") for e in errors)

    def test_domain_absent_from_manifest_flow062(self):
        vr = load_fixture("valid/validation-result.yaml")
        hm = load_fixture("valid/handoff-manifest-with-frontend.yaml")
        vr_mismatch = {**vr, "validation": {**vr["validation"], "domain": "payments"}}
        errors = validate_chain(vr_mismatch, hm)
        assert any(e.startswith("FLOW-062") for e in errors)


class TestTaskContractReadiness:
    def test_tc_with_no_deps_is_ready(self):
        data = load_fixture("valid/task-contract.yaml")
        assert validate_task_contract_readiness(data, []) == []

    def test_tc_with_all_deps_done_is_ready(self):
        data = load_fixture("valid/task-contract-with-dependency.yaml")
        assert validate_task_contract_readiness(data, ["TC-01"]) == []

    def test_tc_with_unmet_dep_flow040(self):
        data = load_fixture("valid/task-contract-with-dependency.yaml")
        errors = validate_task_contract_readiness(data, [])
        assert any(e.startswith("FLOW-040") for e in errors)

    def test_tc_with_partially_met_deps_still_blocked(self):
        data = load_fixture("valid/task-contract-with-dependency.yaml")
        errors = validate_task_contract_readiness(data, ["TC-03"])
        assert any(e.startswith("FLOW-040") for e in errors)


class TestBeToFeHandoff:
    def test_complete_with_zero_deviations_passes(self):
        data = load_fixture("valid/be-to-fe-handoff.yaml")
        assert validate_be_to_fe_handoff(data) == []

    def test_complete_with_deviations_passes(self):
        data = load_fixture("valid/be-to-fe-handoff-with-deviations.yaml")
        assert validate_be_to_fe_handoff(data) == []

    def test_complete_with_nonzero_deviations_flow070(self):
        data = {**load_fixture("valid/be-to-fe-handoff.yaml"), "known_deviations_count": 2}
        errors = validate_be_to_fe_handoff(data)
        assert any(e.startswith("FLOW-070") for e in errors)

    def test_complete_with_deviations_zero_count_flow071(self):
        data = {**load_fixture("valid/be-to-fe-handoff-with-deviations.yaml"), "known_deviations_count": 0}
        errors = validate_be_to_fe_handoff(data)
        assert any(e.startswith("FLOW-071") for e in errors)

    def test_has_deviations_no_endpoint_deviation_flow072(self):
        data = {**load_fixture("valid/be-to-fe-handoff.yaml"), "api_contract_status": "has_deviations"}
        errors = validate_be_to_fe_handoff(data)
        assert any(e.startswith("FLOW-072") for e in errors)

    def test_up_to_date_with_endpoint_deviation_flow073(self):
        data = {**load_fixture("valid/be-to-fe-handoff-with-deviations.yaml"), "api_contract_status": "up_to_date"}
        errors = validate_be_to_fe_handoff(data)
        assert any(e.startswith("FLOW-073") for e in errors)
