import { describe, it, expect } from 'vitest'
import { loadFixture } from './helpers/load.js'

// ─── FLOW Code Ranges ─────────────────────────────────────────────────────────
//
//  001–009  validation-result: handoff gate invariants
//  010–019  blocked-report: status/escalation routing
//  020–029  change-request: timestamp/resolution invariants + FLOW-025 handoff gate
//  030–039  handoff-manifest: structure/type/artifact invariants
//  040–049  task-contract: dependency readiness
//  051–059  validation-result: ID uniqueness (blocking + warnings)
//  060–069  spec-to-dev chain: cross-artifact consistency
//  070–079  be-to-fe-handoff: deviation consistency invariants
//
// ─── Business Rule Validators ─────────────────────────────────────────────────

function validateValidationResult(data) {
  const errors = []
  const { status, blocking_count, warning_count, handoff_allowed, blocking_issues, warnings, validation } = data

  if (status === 'VALID' && blocking_count === 0 && handoff_allowed !== true) {
    errors.push('FLOW-001: status=VALID + blocking_count=0 requires handoff_allowed=true')
  }
  if ((status === 'INVALID' || blocking_count > 0) && handoff_allowed !== false) {
    errors.push('FLOW-002: status=INVALID or blocking_count>0 requires handoff_allowed=false')
  }
  if (blocking_count !== blocking_issues.length) {
    errors.push(
      `FLOW-003: blocking_count (${blocking_count}) != blocking_issues.length (${blocking_issues.length})`
    )
  }
  if (warning_count !== warnings.length) {
    errors.push(
      `FLOW-004: warning_count (${warning_count}) != warnings.length (${warnings.length})`
    )
  }
  // incremental_back is a mid-pipeline check — handoff never allowed at this stage
  if (validation.mode === 'incremental_back' && handoff_allowed === true) {
    errors.push('FLOW-005: incremental_back mode cannot have handoff_allowed=true')
  }
  // blocking_issue IDs must be unique within a report
  const blockingIds = blocking_issues.map(i => i.id)
  const duplicateBlockingIds = blockingIds.filter((id, idx) => blockingIds.indexOf(id) !== idx)
  if (duplicateBlockingIds.length > 0) {
    errors.push(`FLOW-051: duplicate blocking_issue IDs: ${[...new Set(duplicateBlockingIds)].join(', ')}`)
  }
  // warning IDs must be unique within a report
  const warningIds = warnings.map(w => w.id)
  const duplicateWarningIds = warningIds.filter((id, idx) => warningIds.indexOf(id) !== idx)
  if (duplicateWarningIds.length > 0) {
    errors.push(`FLOW-052: duplicate warning IDs: ${[...new Set(duplicateWarningIds)].join(', ')}`)
  }

  return errors
}

// TC readiness — all declared dependencies must be in completedIds
function validateTaskContractReadiness(tc, completedIds = []) {
  const errors = []
  const deps = tc.task_contract.dependencies || []
  const unmet = deps.filter(id => !completedIds.includes(id))
  if (unmet.length > 0) {
    errors.push(`FLOW-040: TC blocked — unmet dependencies: ${unmet.join(', ')}`)
  }
  return errors
}

function validateBlockedReport(data) {
  const errors = []
  const { status, missing_inputs, conflicts, resolution } = data

  if (status === 'blocked') {
    if (!missing_inputs || missing_inputs.length === 0) {
      errors.push('FLOW-010: status=blocked requires missing_inputs with at least one entry')
    }
    if (conflicts && conflicts.length > 0) {
      errors.push('FLOW-011: status=blocked must not populate conflicts — use missing_inputs')
    }
    // blocked → recoverable by orchestrator
    if (resolution.escalate_to !== 'orchestrator') {
      errors.push('FLOW-014: status=blocked must escalate_to orchestrator')
    }
  }

  if (status === 'failed') {
    if (!conflicts || conflicts.length === 0) {
      errors.push('FLOW-012: status=failed requires conflicts with at least one entry')
    }
    if (missing_inputs && missing_inputs.length > 0) {
      errors.push('FLOW-013: status=failed must not populate missing_inputs — use conflicts')
    }
    // failed → unrecoverable by orchestrator, needs human
    if (resolution.escalate_to !== 'human') {
      errors.push('FLOW-015: status=failed must escalate_to human')
    }
  }

  return errors
}

function validateCR(data) {
  const errors = []
  const { resolution } = data

  if (resolution.status === 'open' && resolution.timestamp !== '') {
    errors.push('FLOW-020: resolution.status=open requires timestamp to be empty string')
  }
  if (['accepted', 'rejected', 'deferred'].includes(resolution.status) && !resolution.timestamp) {
    errors.push('FLOW-021: resolved CR requires a non-empty resolution.timestamp')
  }

  return errors
}

// CR → handoff gate: open CR with dev_blocked=true must prevent handoff delivery
// Business rule: u-spec-to-dev-handoff.md §Preconditions — "No open CRs blocking delivery"
function validateCRHandoffGate(cr) {
  const errors = []
  const isBlocking = cr.resolution.status === 'open' && cr.impact.dev_blocked === true
  if (isBlocking) {
    errors.push(
      `FLOW-025: CR ${cr.id} is open and dev_blocked=true — handoff delivery must be halted until resolved`
    )
  }
  return errors
}

// Maps each handoff type to the allowed change_summary.type values
const HANDOFF_SUMMARY_TYPE_MAP = {
  major_evolution: ['major'],
  fast_track: ['patch', 'minor'],
  reverse_eng: ['patch', 'minor', 'major'],
}

// Minimum required artifact types in backend_package per the spec-to-dev handoff protocol
const REQUIRED_BACKEND_ARTIFACTS = ['openapi', 'back-spec']

function validateHandoffManifest(data) {
  const errors = []
  const { handoff, domains, backend_package, change_summary } = data

  if (handoff.delivered_by !== 'u-spec-orchestrator') {
    errors.push(`FLOW-030: delivered_by must be "u-spec-orchestrator", got "${handoff.delivered_by}"`)
  }
  if (!domains || domains.length === 0) {
    errors.push('FLOW-031: handoff must contain at least one domain')
  }
  if (!backend_package || backend_package.length === 0) {
    errors.push('FLOW-032: handoff must include at least one backend_package entry')
  }
  if (handoff.type === 'new_domain' && change_summary !== undefined) {
    errors.push('FLOW-033: new_domain handoff must not include change_summary')
  }
  if (['major_evolution', 'fast_track', 'reverse_eng'].includes(handoff.type) && !change_summary) {
    errors.push(`FLOW-034: ${handoff.type} handoff requires change_summary`)
  }
  if (change_summary && !['no_action', 'reevaluate_task_contracts', 'stop_domain_task_contracts'].includes(change_summary.dev_impact)) {
    errors.push(`FLOW-035: change_summary.dev_impact "${change_summary.dev_impact}" is not valid`)
  }
  // change_summary.type must match allowed values for the handoff type
  if (change_summary && HANDOFF_SUMMARY_TYPE_MAP[handoff.type]) {
    const allowed = HANDOFF_SUMMARY_TYPE_MAP[handoff.type]
    if (!allowed.includes(change_summary.type)) {
      errors.push(`FLOW-036: ${handoff.type} requires change_summary.type in [${allowed.join(', ')}], got "${change_summary.type}"`)
    }
  }
  // full deliveries (new_domain, major_evolution) must include all required artifacts
  // fast_track and reverse_eng deliver only changed files — full package not required
  if (backend_package && backend_package.length > 0 &&
      ['new_domain', 'major_evolution'].includes(handoff.type)) {
    const present = backend_package.map(p => p.artifact)
    for (const required of REQUIRED_BACKEND_ARTIFACTS) {
      if (!present.includes(required)) {
        errors.push(`FLOW-037: backend_package missing required artifact "${required}" for ${handoff.type}`)
      }
    }
  }

  return errors
}

// cross-artifact chain — validation_result must be consistent with handoff-manifest
function validateChain(validationResult, handoffManifest) {
  const errors = []
  const { validation, status, handoff_allowed } = validationResult
  const { domains } = handoffManifest

  // FLOW-060: only final_complete validation can gate a handoff
  if (validation.mode !== 'final_complete') {
    errors.push(`FLOW-060: handoff requires final_complete validation, got "${validation.mode}"`)
  }
  // FLOW-061: validation must be VALID and handoff_allowed=true
  if (status !== 'VALID' || !handoff_allowed) {
    errors.push('FLOW-061: handoff-manifest cannot derive from non-VALID or handoff_allowed=false validation')
  }
  // FLOW-062: domain in validation_result must exist in handoff-manifest
  const matchingDomain = domains?.find(d => d.name === validation.domain)
  if (!matchingDomain) {
    errors.push(`FLOW-062: domain "${validation.domain}" from validation_result not found in handoff-manifest`)
  }
  // FLOW-063: spec version must be consistent between both artifacts
  if (matchingDomain && matchingDomain.spec_version !== validation.artifact_version) {
    errors.push(
      `FLOW-063: version mismatch — validation_result v${validation.artifact_version} != handoff-manifest v${matchingDomain.spec_version}`
    )
  }

  return errors
}

function validateBeToFeHandoff(data) {
  const errors = []
  const { be_phase_status, known_deviations_count, api_contract_status, endpoints } = data

  // FLOW-070: complete status requires 0 deviations
  if (be_phase_status === 'complete' && known_deviations_count !== 0) {
    errors.push(`FLOW-070: be_phase_status=complete requires known_deviations_count=0, got ${known_deviations_count}`)
  }
  // FLOW-071: complete_with_deviations requires at least 1 deviation
  if (be_phase_status === 'complete_with_deviations' && known_deviations_count === 0) {
    errors.push('FLOW-071: be_phase_status=complete_with_deviations requires known_deviations_count>0')
  }
  // FLOW-072: api_contract_status=has_deviations only when at least one endpoint is done_with_deviations
  const hasEndpointDeviation = (endpoints || []).some(e => e.status === 'done_with_deviations')
  if (api_contract_status === 'has_deviations' && !hasEndpointDeviation) {
    errors.push('FLOW-072: api_contract_status=has_deviations requires at least one endpoint with status=done_with_deviations')
  }
  // FLOW-073: api_contract_status=up_to_date only when no endpoint is done_with_deviations
  if (api_contract_status === 'up_to_date' && hasEndpointDeviation) {
    errors.push('FLOW-073: api_contract_status=up_to_date cannot have endpoints with status=done_with_deviations')
  }

  return errors
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('Layer 5 — Flow Invariants', () => {

  describe('validation-result', () => {
    it('VALID + blocking_count=0 → handoff_allowed=true', () => {
      const data = loadFixture('valid/validation-result.yaml')
      expect(validateValidationResult(data)).toHaveLength(0)
    })

    // Per-rule passes (FLOW-003 / FLOW-004 on the same valid fixture) are
    // strict subsets of the "no violations at all" assertion above.

    it('INVALID + handoff_allowed=true → FLOW-002 violation', () => {
      const data = loadFixture('invalid/validation-result-invalid-handoff-true.yaml')
      const errors = validateValidationResult(data)
      expect(errors.some(e => e.startsWith('FLOW-002'))).toBe(true)
    })

    it('VALID + blocking_count>0 → FLOW-002/FLOW-003 violation', () => {
      const data = loadFixture('invalid/validation-result-valid-blocking.yaml')
      const errors = validateValidationResult(data)
      expect(errors.some(e => e.startsWith('FLOW-002') || e.startsWith('FLOW-003'))).toBe(true)
    })

    // warnings do not block handoff
    it('warnings present without blocking issues → handoff_allowed=true (warnings do not block)', () => {
      const data = loadFixture('valid/validation-result-with-warnings.yaml')
      expect(validateValidationResult(data)).toHaveLength(0)
      expect(data.handoff_allowed).toBe(true)
      expect(data.warning_count).toBeGreaterThan(0)
      expect(data.blocking_count).toBe(0)
    })

    // incremental_back never allows handoff
    it('mode=incremental_back + handoff_allowed=true → FLOW-005 violation', () => {
      const data = loadFixture('invalid/validation-result-incremental-handoff-true.yaml')
      const errors = validateValidationResult(data)
      expect(errors.some(e => e.startsWith('FLOW-005'))).toBe(true)
    })

    it('duplicate blocking_issue IDs → FLOW-051 violation', () => {
      const data = loadFixture('invalid/validation-result-duplicate-issue-ids.yaml')
      const errors = validateValidationResult(data)
      expect(errors.some(e => e.startsWith('FLOW-051'))).toBe(true)
    })

    // FLOW-051 / FLOW-052 "absent on valid fixture" assertions are subsumed by
    // the "passes all rules" tests on those same fixtures (lines 240–276).
  })

  describe('blocked-report', () => {
    it('valid blocked report passes all flow rules', () => {
      const data = loadFixture('valid/blocked-report.yaml')
      expect(validateBlockedReport(data)).toHaveLength(0)
    })

    // escalation routing by status
    it('status=blocked escalates to orchestrator', () => {
      const data = loadFixture('valid/blocked-report.yaml')
      expect(data.resolution.escalate_to).toBe('orchestrator')
    })

    it('status=failed must escalate to human, not orchestrator → FLOW-015 violation', () => {
      const data = loadFixture('invalid/blocked-failed-escalate-to-orchestrator.yaml')
      const errors = validateBlockedReport(data)
      expect(errors.some(e => e.startsWith('FLOW-015'))).toBe(true)
    })

    it('status=blocked without missing_inputs → FLOW-010 violation', () => {
      const data = loadFixture('invalid/blocked-status-blocked-no-missing.yaml')
      const errors = validateBlockedReport(data)
      expect(errors.some(e => e.startsWith('FLOW-010'))).toBe(true)
    })

    it('status=blocked with conflicts populated → FLOW-011 violation', () => {
      const data = loadFixture('invalid/blocked-status-blocked-with-conflicts.yaml')
      const errors = validateBlockedReport(data)
      expect(errors.some(e => e.startsWith('FLOW-011'))).toBe(true)
    })

    it('status=failed without conflicts → FLOW-012 violation', () => {
      const data = loadFixture('invalid/blocked-status-failed-no-conflicts.yaml')
      const errors = validateBlockedReport(data)
      expect(errors.some(e => e.startsWith('FLOW-012'))).toBe(true)
    })

    it('status=failed with missing_inputs populated → FLOW-013 violation', () => {
      const data = loadFixture('invalid/blocked-status-failed-with-missing-inputs.yaml')
      const errors = validateBlockedReport(data)
      expect(errors.some(e => e.startsWith('FLOW-013'))).toBe(true)
    })
  })

  describe('change-request', () => {
    it('open CR with empty timestamp passes flow rules', () => {
      const data = loadFixture('valid/cr.yaml')
      expect(validateCR(data)).toHaveLength(0)
    })

    it('accepted CR with non-empty timestamp passes flow rules', () => {
      const data = loadFixture('valid/cr-accepted.yaml')
      expect(validateCR(data)).toHaveLength(0)
    })

    // dev_blocked=false does not halt task execution
    it('CR with dev_blocked=false does not block task', () => {
      const data = loadFixture('valid/cr-dev-not-blocked.yaml')
      const taskBlocked = data.resolution.status === 'open' && data.impact.dev_blocked === true
      expect(taskBlocked).toBe(false)
    })

    it('open CR with non-empty timestamp → FLOW-020 violation', () => {
      const data = loadFixture('invalid/cr-open-with-timestamp.yaml')
      const errors = validateCR(data)
      expect(errors.some(e => e.startsWith('FLOW-020'))).toBe(true)
    })

    it('rejected CR with empty timestamp → FLOW-021 violation', () => {
      const data = loadFixture('invalid/cr-rejected-no-timestamp.yaml')
      const errors = validateCR(data)
      expect(errors.some(e => e.startsWith('FLOW-021'))).toBe(true)
    })

    it('deferred CR with empty timestamp → FLOW-021 violation', () => {
      const data = loadFixture('invalid/cr-deferred-no-timestamp.yaml')
      const errors = validateCR(data)
      expect(errors.some(e => e.startsWith('FLOW-021'))).toBe(true)
    })

    // CR → handoff gate (FLOW-025)
    it('open CR with dev_blocked=true → FLOW-025 handoff gate violation', () => {
      const data = loadFixture('invalid/cr-blocking-handoff.yaml')
      const errors = validateCRHandoffGate(data)
      expect(errors.some(e => e.startsWith('FLOW-025'))).toBe(true)
    })

    it('open CR with dev_blocked=false does not trigger handoff gate', () => {
      const data = loadFixture('valid/cr-dev-not-blocked.yaml')
      expect(validateCRHandoffGate(data)).toHaveLength(0)
    })

    it('accepted CR with dev_blocked=true does not trigger handoff gate', () => {
      // resolved CRs (accepted/rejected/deferred) never block handoff regardless of dev_blocked
      const data = loadFixture('valid/cr-accepted.yaml')
      expect(validateCRHandoffGate(data)).toHaveLength(0)
    })
  })

  describe('handoff-manifest', () => {
    it('new_domain manifest passes all flow rules', () => {
      const data = loadFixture('valid/handoff-manifest.yaml')
      expect(validateHandoffManifest(data)).toHaveLength(0)
    })

    it('empty domains → FLOW-031 violation', () => {
      const data = loadFixture('invalid/handoff-manifest-empty-domains.yaml')
      const errors = validateHandoffManifest(data)
      expect(errors.some(e => e.startsWith('FLOW-031'))).toBe(true)
    })

    it('empty backend_package → FLOW-032 violation', () => {
      const data = loadFixture('invalid/handoff-manifest-no-backend-package.yaml')
      const errors = validateHandoffManifest(data)
      expect(errors.some(e => e.startsWith('FLOW-032'))).toBe(true)
    })

    it('delivered_by != u-spec-orchestrator → FLOW-030 violation', () => {
      const data = loadFixture('invalid/handoff-manifest-wrong-sender.yaml')
      const errors = validateHandoffManifest(data)
      expect(errors.some(e => e.startsWith('FLOW-030'))).toBe(true)
    })

    // change_summary rules by handoff type
    it('major_evolution with change_summary passes flow rules', () => {
      const data = loadFixture('valid/handoff-manifest-major-evolution.yaml')
      expect(validateHandoffManifest(data)).toHaveLength(0)
    })

    it('fast_track with change_summary passes flow rules', () => {
      const data = loadFixture('valid/handoff-manifest-fast-track.yaml')
      expect(validateHandoffManifest(data)).toHaveLength(0)
    })

    it('major_evolution without change_summary → FLOW-034 violation', () => {
      const data = loadFixture('invalid/handoff-manifest-major-evolution-no-change-summary.yaml')
      const errors = validateHandoffManifest(data)
      expect(errors.some(e => e.startsWith('FLOW-034'))).toBe(true)
    })

    it('new_domain with change_summary → FLOW-033 violation', () => {
      const data = loadFixture('invalid/handoff-manifest-new-domain-with-change-summary.yaml')
      const errors = validateHandoffManifest(data)
      expect(errors.some(e => e.startsWith('FLOW-033'))).toBe(true)
    })

    // dev_impact outcomes
    it('major_evolution dev_impact=stop_domain_task_contracts halts all domain TCs', () => {
      const data = loadFixture('valid/handoff-manifest-major-evolution.yaml')
      expect(data.change_summary.dev_impact).toBe('stop_domain_task_contracts')
    })

    it('fast_track dev_impact=reevaluate_task_contracts triggers TC reassessment', () => {
      const data = loadFixture('valid/handoff-manifest-fast-track.yaml')
      expect(data.change_summary.dev_impact).toBe('reevaluate_task_contracts')
    })

    // handoff with frontend_artifacts passes flow rules
    it('new_domain with frontend_artifacts passes flow rules', () => {
      const data = loadFixture('valid/handoff-manifest-with-frontend.yaml')
      expect(validateHandoffManifest(data)).toHaveLength(0)
      expect(data.frontend_artifacts).toBeDefined()
      expect(data.frontend_package).toBeDefined()
    })

    // dev_impact=no_action: patch fast_track — Dev proceeds without interruption
    it('fast_track + patch + dev_impact=no_action passes flow rules', () => {
      const data = loadFixture('valid/handoff-manifest-fast-track-patch.yaml')
      expect(validateHandoffManifest(data)).toHaveLength(0)
      expect(data.change_summary.dev_impact).toBe('no_action')
      expect(data.change_summary.type).toBe('patch')
    })

    // change_summary.type correlation with handoff.type
    it('major_evolution + change_summary.type=patch → FLOW-036 violation', () => {
      const data = loadFixture('invalid/handoff-manifest-major-wrong-type.yaml')
      const errors = validateHandoffManifest(data)
      expect(errors.some(e => e.startsWith('FLOW-036'))).toBe(true)
    })

    it('fast_track + change_summary.type=major → FLOW-036 violation', () => {
      const data = loadFixture('invalid/handoff-manifest-fast-track-wrong-type.yaml')
      const errors = validateHandoffManifest(data)
      expect(errors.some(e => e.startsWith('FLOW-036'))).toBe(true)
    })

    // backend_package completeness
    it('backend_package missing required artifact → FLOW-037 violation', () => {
      const data = loadFixture('invalid/handoff-manifest-incomplete-backend.yaml')
      const errors = validateHandoffManifest(data)
      expect(errors.some(e => e.startsWith('FLOW-037'))).toBe(true)
    })

    // The "valid manifest has no FLOW-037" assertion is subsumed by the
    // "new_domain manifest passes all flow rules" test above.
  })

  describe('spec-to-dev chain (validation_result → handoff-manifest)', () => {
    // cross-artifact chain validation

    it('matching validation_result and handoff-manifest pass chain rules', () => {
      const vr = loadFixture('valid/validation-result.yaml')
      const hm = loadFixture('valid/handoff-manifest.yaml')
      expect(validateChain(vr, hm)).toHaveLength(0)
    })

    it('version mismatch between validation_result and handoff-manifest → FLOW-063 violation', () => {
      const vr = loadFixture('valid/validation-result.yaml')       // auth v1.0.0
      const hm = loadFixture('invalid/handoff-manifest-version-mismatch.yaml') // auth v2.0.0
      const errors = validateChain(vr, hm)
      expect(errors.some(e => e.startsWith('FLOW-063'))).toBe(true)
    })

    it('incremental_back validation_result cannot gate a handoff → FLOW-060 violation', () => {
      const vr = loadFixture('invalid/validation-result-incremental-handoff-true.yaml')
      const hm = loadFixture('valid/handoff-manifest.yaml')
      const errors = validateChain(vr, hm)
      expect(errors.some(e => e.startsWith('FLOW-060'))).toBe(true)
    })

    it('INVALID validation_result cannot gate a handoff → FLOW-061 violation', () => {
      const vr = loadFixture('invalid/validation-result-invalid-handoff-true.yaml')
      const hm = loadFixture('valid/handoff-manifest.yaml')
      const errors = validateChain(vr, hm)
      expect(errors.some(e => e.startsWith('FLOW-061'))).toBe(true)
    })

    it('domain in validation_result absent from handoff-manifest → FLOW-062 violation', () => {
      const vr = loadFixture('valid/validation-result.yaml')  // domain: auth
      // handoff-manifest-fast-track-patch has domain: auth — swap to one with different domain
      const hm = loadFixture('valid/handoff-manifest-with-frontend.yaml') // also auth — reuse
      // Simulate a mismatch by using a validation result for a domain not in the manifest
      const vrMismatch = {
        ...vr,
        validation: { ...vr.validation, domain: 'payments' },
      }
      const errors = validateChain(vrMismatch, hm)
      expect(errors.some(e => e.startsWith('FLOW-062'))).toBe(true)
    })
  })

  describe('task-contract readiness', () => {
    // dependency chain enforcement
    it('TC with no dependencies is immediately ready', () => {
      const data = loadFixture('valid/task-contract.yaml')
      const errors = validateTaskContractReadiness(data, [])
      expect(errors).toHaveLength(0)
    })

    it('TC with dependencies all Done is ready', () => {
      const data = loadFixture('valid/task-contract-with-dependency.yaml')
      const errors = validateTaskContractReadiness(data, ['TC-01'])
      expect(errors).toHaveLength(0)
    })

    it('TC with unmet dependency is blocked → FLOW-040 violation', () => {
      const data = loadFixture('valid/task-contract-with-dependency.yaml')
      const errors = validateTaskContractReadiness(data, [])
      expect(errors.some(e => e.startsWith('FLOW-040'))).toBe(true)
    })

    it('TC with partially met dependencies remains blocked', () => {
      const data = loadFixture('valid/task-contract-with-dependency.yaml')
      // TC-02 depends on TC-01; completed set is empty
      const errors = validateTaskContractReadiness(data, ['TC-03'])
      expect(errors.some(e => e.startsWith('FLOW-040'))).toBe(true)
    })
  })

  describe('be-to-fe-handoff', () => {
    it('complete handoff with 0 deviations passes all flow rules', () => {
      const data = loadFixture('valid/be-to-fe-handoff.yaml')
      expect(validateBeToFeHandoff(data)).toHaveLength(0)
    })

    it('complete_with_deviations handoff with 1 deviation passes all flow rules', () => {
      const data = loadFixture('valid/be-to-fe-handoff-with-deviations.yaml')
      expect(validateBeToFeHandoff(data)).toHaveLength(0)
    })

    it('complete + known_deviations_count > 0 → FLOW-070 violation', () => {
      const data = loadFixture('valid/be-to-fe-handoff.yaml')
      const mutated = { ...data, known_deviations_count: 2 }
      const errors = validateBeToFeHandoff(mutated)
      expect(errors.some(e => e.startsWith('FLOW-070'))).toBe(true)
    })

    it('complete_with_deviations + known_deviations_count = 0 → FLOW-071 violation', () => {
      const data = loadFixture('valid/be-to-fe-handoff-with-deviations.yaml')
      const mutated = { ...data, known_deviations_count: 0 }
      const errors = validateBeToFeHandoff(mutated)
      expect(errors.some(e => e.startsWith('FLOW-071'))).toBe(true)
    })

    it('api_contract_status=has_deviations with no endpoint deviations → FLOW-072 violation', () => {
      const data = loadFixture('valid/be-to-fe-handoff.yaml')
      const mutated = { ...data, api_contract_status: 'has_deviations' }
      const errors = validateBeToFeHandoff(mutated)
      expect(errors.some(e => e.startsWith('FLOW-072'))).toBe(true)
    })

    it('api_contract_status=up_to_date with endpoint done_with_deviations → FLOW-073 violation', () => {
      const data = loadFixture('valid/be-to-fe-handoff-with-deviations.yaml')
      const mutated = { ...data, api_contract_status: 'up_to_date' }
      const errors = validateBeToFeHandoff(mutated)
      expect(errors.some(e => e.startsWith('FLOW-073'))).toBe(true)
    })
  })

})
