import { describe, it, expect } from 'vitest'
import { loadFixture } from './helpers/load.js'

// ─── Flow Code Ranges ──────────────────────────────────────────────────────────
//
//  IMPV-001–009   type / spec_change_status consistency
//  IMPV-010–019   planner_required consistency
//  IMPV-020–029   spec-triage-specific invariants
//  IMPV-030–039   affected_specs structure
//  IMPV-040–049   pipeline routing (lean vs full)
//  IMPV-050–059   session-log consumption (scope_consumed marker)
//
// ─── Validator ────────────────────────────────────────────────────────────────

function validateImproveScope(data) {
  const errors = []
  const scope = data.improve_scope
  if (!scope) {
    errors.push('IMPV-000: improve_scope key missing from document root')
    return errors
  }

  const {
    type,
    spec_change_status,
    affected_specs = [],
    estimated_task_contracts,
    planner_required,
    planner_skip_reason,
    source,
    generated_on,
    task_contracts,
  } = scope

  // ── type / spec_change_status consistency ──────────────────────────────────

  // IMPV-001: implementation_only → spec_change_status must be not_required
  if (type === 'implementation_only' && spec_change_status !== 'not_required') {
    errors.push(
      `IMPV-001: type=implementation_only requires spec_change_status=not_required, got "${spec_change_status}"`
    )
  }

  // IMPV-002: spec_change_required → spec_change_status must be one of the allowed values.
  //   - pending_spec / failed are valid transient/failure states written by /u-improve
  //     (Step 3a write-before-confirm) or by the spec orchestrator return contract.
  //   - completed / divergence_accepted are terminal states that allow /u-dev to proceed.
  if (
    type === 'spec_change_required' &&
    !['completed', 'divergence_accepted', 'pending_spec', 'failed'].includes(spec_change_status)
  ) {
    errors.push(
      `IMPV-002: type=spec_change_required requires spec_change_status=completed|divergence_accepted|pending_spec|failed, got "${spec_change_status}"`
    )
  }

  // IMPV-003: spec_change_required → affected_specs must be non-empty
  if (type === 'spec_change_required' && (!affected_specs || affected_specs.length === 0)) {
    errors.push('IMPV-003: type=spec_change_required requires at least one entry in affected_specs')
  }

  // ── planner_required consistency ───────────────────────────────────────────

  // IMPV-010: planner_required=false → planner_skip_reason must be present (except spec-triage blocks)
  // spec-triage blocks use task_contracts[].type to imply skip reason — no planner_skip_reason required
  if (
    planner_required === false &&
    source !== 'spec-triage' &&
    (!planner_skip_reason || planner_skip_reason.trim() === '')
  ) {
    errors.push('IMPV-010: planner_required=false requires a non-empty planner_skip_reason')
  }

  // IMPV-011: planner_required=false → estimated_task_contracts must be 1 (u-improve only)
  // spec-triage may batch multiple independent patch corrections as lean (no Planner needed)
  if (planner_required === false && source !== 'spec-triage' && estimated_task_contracts !== 1) {
    errors.push(
      `IMPV-011: planner_required=false requires estimated_task_contracts=1, got ${estimated_task_contracts}`
    )
  }

  // IMPV-012: planner_required=true → planner_skip_reason must be absent
  if (planner_required === true && planner_skip_reason !== undefined && planner_skip_reason !== null && planner_skip_reason !== '') {
    errors.push('IMPV-012: planner_required=true must not include planner_skip_reason')
  }

  // IMPV-013: estimated_task_contracts > 1 → planner_required must be true (u-improve only)
  // spec-triage patch batches are exempt: multiple patch TCs with planner_required=false is valid
  if (estimated_task_contracts > 1 && source !== 'spec-triage' && planner_required !== true) {
    errors.push(
      `IMPV-013: estimated_task_contracts=${estimated_task_contracts} requires planner_required=true`
    )
  }

  // ── spec-triage-specific invariants ───────────────────────────────────────

  if (source === 'spec-triage') {
    // IMPV-020: source=spec-triage → spec_change_status must be completed
    if (spec_change_status !== 'completed') {
      errors.push(
        `IMPV-020: source=spec-triage requires spec_change_status=completed, got "${spec_change_status}"`
      )
    }

    // IMPV-021: source=spec-triage → generated_on must be present
    if (!generated_on) {
      errors.push('IMPV-021: source=spec-triage requires generated_on field')
    }

    // IMPV-022: source=spec-triage → estimated_task_contracts must equal len(task_contracts)
    if (task_contracts !== undefined) {
      const tcCount = Array.isArray(task_contracts) ? task_contracts.length : 0
      if (estimated_task_contracts !== tcCount) {
        errors.push(
          `IMPV-022: source=spec-triage estimated_task_contracts (${estimated_task_contracts}) must equal len(task_contracts) (${tcCount})`
        )
      }
    }
  }

  // ── affected_specs structure ───────────────────────────────────────────────

  // IMPV-030/031: object entries (from /u-improve) must have path, sections, change_summary
  // String entries (from spec-triage) are plain paths — no nested structure required
  for (const [i, spec] of (affected_specs || []).entries()) {
    if (typeof spec === 'object' && spec !== null) {
      if (!spec.path) {
        errors.push(`IMPV-030: affected_specs[${i}] missing required field "path"`)
      }
      if (!spec.sections || !Array.isArray(spec.sections) || spec.sections.length === 0) {
        errors.push(`IMPV-031: affected_specs[${i}] missing or empty "sections" array`)
      }
      if (!spec.change_summary) {
        errors.push(`IMPV-030: affected_specs[${i}] missing required field "change_summary"`)
      }
    }
    // typeof spec === 'string': plain path from spec-triage — no structure validation needed
  }

  return errors
}

// Pipeline routing decision derived from scope block
function resolvesPipelineRoute(scope) {
  const { planner_required, source, spec_change_status } = scope.improve_scope
  const blocked = spec_change_status === 'pending_spec' || spec_change_status === 'failed'
  return {
    lean: !blocked && planner_required === false,
    full: !blocked && planner_required === true,
    shortCircuit: source === 'spec-triage' && spec_change_status === 'completed',
    blocked,
    haltMode:
      spec_change_status === 'pending_spec'
        ? 'Halt-await-spec'
        : spec_change_status === 'failed'
        ? 'Halt-spec-failed'
        : null,
  }
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('Layer 8 — Improve & Triage Flow Invariants', () => {

  // ── /u-improve: valid scope blocks ──────────────────────────────────────────
  //
  // Per-fixture "passes all rules" tests live in the parameterized
  // "schema completeness — all valid fixtures pass all rules" describe at the
  // bottom of this file. Adding them again here is duplicate coverage — Vitest
  // already reports the failing fixture name from the it.each.
  //
  // ── /u-improve: type / spec_change_status consistency ──────────────────────

  describe('/u-improve — type/spec_change_status invariants', () => {

    it('IMPV-001: implementation_only + spec_change_status=completed → violation', () => {
      const data = loadFixture('invalid/improve-scope-impl-only-status-completed.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-001'))).toBe(true)
    })

    it('IMPV-002: spec_change_required + spec_change_status=not_required → violation', () => {
      const data = loadFixture('invalid/improve-scope-spec-required-status-not-required.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-002'))).toBe(true)
    })

    it('IMPV-003: spec_change_required + empty affected_specs → violation', () => {
      const data = loadFixture('invalid/improve-scope-spec-required-empty-affected.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-003'))).toBe(true)
    })

    // Subset checks against valid fixtures (e.g. "no IMPV-003 violation on
    // implementation_only", "no IMPV-002 on divergence_accepted") are strict
    // subsets of the parameterized "all valid fixtures pass all rules" block —
    // omitted to avoid duplicate coverage.

  })

  // ── /u-improve: planner_required consistency ────────────────────────────────

  describe('/u-improve — planner_required invariants', () => {

    it('IMPV-010: planner_required=false without planner_skip_reason → violation', () => {
      const data = loadFixture('invalid/improve-scope-lean-no-skip-reason.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-010'))).toBe(true)
    })

    it('IMPV-011: planner_required=false with estimated_task_contracts=2 → violation', () => {
      const data = loadFixture('invalid/improve-scope-lean-multi-tc.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-011'))).toBe(true)
    })

    it('IMPV-012: planner_required=true with planner_skip_reason → violation', () => {
      const data = loadFixture('invalid/improve-scope-planner-required-with-skip-reason.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-012'))).toBe(true)
    })

    it('IMPV-013: estimated_task_contracts=3 + planner_required=false → violation', () => {
      const data = loadFixture('invalid/improve-scope-multi-tc-planner-false.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-013'))).toBe(true)
    })

    // Subset checks against valid fixtures (no IMPV-010 / IMPV-012 violation)
    // are subsumed by the parameterized "all valid fixtures pass all rules" block.

  })

  // ── /u-spec-triage: valid scope blocks ──────────────────────────────────────

  describe('/u-spec-triage — valid scope blocks', () => {

    // "patch corrections" and "structural corrections" passing all rules are
    // subsumed by the parameterized "schema completeness — all valid fixtures"
    // block at the bottom of this file. Only the assertions that check
    // properties NOT covered by validateImproveScope remain here.

    it('spec-triage block always has spec_change_status=completed', () => {
      const patch = loadFixture('valid/improve-scope-spec-triage-patch.yaml')
      const structural = loadFixture('valid/improve-scope-spec-triage-structural.yaml')
      expect(patch.improve_scope.spec_change_status).toBe('completed')
      expect(structural.improve_scope.spec_change_status).toBe('completed')
    })

    it('spec-triage block estimated_task_contracts equals len(task_contracts)', () => {
      const data = loadFixture('valid/improve-scope-spec-triage-structural.yaml')
      const { estimated_task_contracts, task_contracts } = data.improve_scope
      expect(estimated_task_contracts).toBe(task_contracts.length)
    })

  })

  // ── /u-spec-triage: triage-specific invariants ──────────────────────────────

  describe('/u-spec-triage — triage-specific invariants', () => {

    it('IMPV-020: source=spec-triage + spec_change_status=divergence_accepted → violation', () => {
      const data = loadFixture('invalid/improve-scope-triage-divergence-accepted.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-020'))).toBe(true)
    })

    it('IMPV-021: source=spec-triage without generated_on → violation', () => {
      const data = loadFixture('invalid/improve-scope-triage-no-generated-on.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-021'))).toBe(true)
    })

    it('IMPV-022: source=spec-triage estimated_task_contracts mismatch with task_contracts length → violation', () => {
      const data = loadFixture('invalid/improve-scope-triage-tc-count-mismatch.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-022'))).toBe(true)
    })

    it('spec-triage source does not require planner_skip_reason when planner_required=false (lean triage)', () => {
      const data = loadFixture('valid/improve-scope-spec-triage-patch.yaml')
      // planner_required=false but source=spec-triage — skip reason not required for triage blocks
      // Triage blocks don't have planner_skip_reason by design; IMPV-010 does not apply
      const scope = data.improve_scope
      expect(scope.planner_required).toBe(false)
      // We intentionally do not enforce IMPV-010 for spec-triage source blocks
      const errors = validateImproveScope(data)
      // No IMPV-010 violation should be raised for triage-originated lean blocks
      const impv010 = errors.filter(e => e.startsWith('IMPV-010'))
      expect(impv010).toHaveLength(0)
    })

  })

  // ── affected_specs structure ─────────────────────────────────────────────────

  describe('affected_specs structure invariants', () => {

    it('IMPV-030: affected_specs entry missing change_summary → violation', () => {
      const data = loadFixture('invalid/improve-scope-affected-spec-missing-summary.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-030'))).toBe(true)
    })

    it('valid affected_specs entry passes IMPV-030 and IMPV-031', () => {
      const data = loadFixture('valid/improve-scope-spec-change-completed.yaml')
      const errors = validateImproveScope(data).filter(
        e => e.startsWith('IMPV-030') || e.startsWith('IMPV-031')
      )
      expect(errors).toHaveLength(0)
    })

    it('spec-triage affected_specs (string paths) do not require object structure', () => {
      // spec-triage uses plain string paths in affected_specs, not {path, sections, change_summary}
      const data = loadFixture('valid/improve-scope-spec-triage-patch.yaml')
      const errors = validateImproveScope(data).filter(
        e => e.startsWith('IMPV-030') || e.startsWith('IMPV-031')
      )
      expect(errors).toHaveLength(0)
    })

  })

  // ── Pipeline routing ─────────────────────────────────────────────────────────

  describe('pipeline routing decisions', () => {

    it('implementation_only + planner_required=false → lean pipeline', () => {
      const data = loadFixture('valid/improve-scope-implementation-only.yaml')
      const route = resolvesPipelineRoute(data)
      expect(route.lean).toBe(true)
      expect(route.full).toBe(false)
    })

    it('implementation_only + planner_required=true → full pipeline', () => {
      const data = loadFixture('valid/improve-scope-implementation-only-with-planner.yaml')
      const route = resolvesPipelineRoute(data)
      expect(route.lean).toBe(false)
      expect(route.full).toBe(true)
    })

    it('spec_change_required + completed + planner_required=true → full pipeline', () => {
      const data = loadFixture('valid/improve-scope-spec-change-completed.yaml')
      const route = resolvesPipelineRoute(data)
      expect(route.full).toBe(true)
    })

    it('spec_change_required + completed + planner_required=false → lean pipeline', () => {
      const data = loadFixture('valid/improve-scope-spec-change-completed-lean.yaml')
      const route = resolvesPipelineRoute(data)
      expect(route.lean).toBe(true)
    })

    it('spec-triage + completed → short-circuits spec-orchestrator re-run', () => {
      const data = loadFixture('valid/improve-scope-spec-triage-patch.yaml')
      const route = resolvesPipelineRoute(data)
      expect(route.shortCircuit).toBe(true)
    })

    it('non-triage source does not trigger short-circuit', () => {
      const data = loadFixture('valid/improve-scope-spec-change-completed.yaml')
      const route = resolvesPipelineRoute(data)
      expect(route.shortCircuit).toBe(false)
    })

    it('divergence_accepted does not trigger short-circuit (no source=spec-triage)', () => {
      const data = loadFixture('valid/improve-scope-divergence-accepted.yaml')
      const route = resolvesPipelineRoute(data)
      expect(route.shortCircuit).toBe(false)
    })

    it('pending_spec → blocked + Halt-await-spec mode (neither lean nor full)', () => {
      const data = loadFixture('valid/improve-scope-pending-spec.yaml')
      const route = resolvesPipelineRoute(data)
      expect(route.blocked).toBe(true)
      expect(route.lean).toBe(false)
      expect(route.full).toBe(false)
      expect(route.haltMode).toBe('Halt-await-spec')
    })

    it('failed → blocked + Halt-spec-failed mode (neither lean nor full)', () => {
      const data = loadFixture('valid/improve-scope-spec-failed.yaml')
      const route = resolvesPipelineRoute(data)
      expect(route.blocked).toBe(true)
      expect(route.lean).toBe(false)
      expect(route.full).toBe(false)
      expect(route.haltMode).toBe('Halt-spec-failed')
    })

    it('completed → not blocked, no halt mode', () => {
      const data = loadFixture('valid/improve-scope-spec-change-completed.yaml')
      const route = resolvesPipelineRoute(data)
      expect(route.blocked).toBe(false)
      expect(route.haltMode).toBeNull()
    })

  })

  // ── pending_spec / failed transient & failure states ────────────────────────
  //
  // The "valid pending_spec" / "valid failed" passes are subsumed by the
  // parameterized "schema completeness" block below. Only the IMPV-001 negative
  // case (implementation_only + pending_spec) remains here as it asserts the
  // specific violation code rather than just "any violation".

  describe('transient and failure states (pending_spec / failed)', () => {

    it('IMPV-001: implementation_only + pending_spec → violation', () => {
      const data = loadFixture('invalid/improve-scope-impl-only-pending-spec.yaml')
      const errors = validateImproveScope(data)
      expect(errors.some(e => e.startsWith('IMPV-001'))).toBe(true)
    })

  })

  // ── Schema-level completeness ────────────────────────────────────────────────

  describe('schema completeness — all valid fixtures pass all rules', () => {

    const validFixtures = [
      'valid/improve-scope-implementation-only.yaml',
      'valid/improve-scope-implementation-only-with-planner.yaml',
      'valid/improve-scope-spec-change-completed.yaml',
      'valid/improve-scope-spec-change-completed-lean.yaml',
      'valid/improve-scope-divergence-accepted.yaml',
      'valid/improve-scope-spec-triage-patch.yaml',
      'valid/improve-scope-spec-triage-structural.yaml',
      'valid/improve-scope-pending-spec.yaml',
      'valid/improve-scope-spec-failed.yaml',
    ]

    it.each(validFixtures)('%s — no violations', (fixturePath) => {
      const data = loadFixture(fixturePath)
      expect(validateImproveScope(data)).toHaveLength(0)
    })

  })

  describe('schema completeness — all invalid fixtures trigger at least one violation', () => {

    const invalidFixtures = [
      'invalid/improve-scope-impl-only-status-completed.yaml',
      'invalid/improve-scope-spec-required-status-not-required.yaml',
      'invalid/improve-scope-spec-required-empty-affected.yaml',
      'invalid/improve-scope-lean-no-skip-reason.yaml',
      'invalid/improve-scope-lean-multi-tc.yaml',
      'invalid/improve-scope-planner-required-with-skip-reason.yaml',
      'invalid/improve-scope-multi-tc-planner-false.yaml',
      'invalid/improve-scope-triage-divergence-accepted.yaml',
      'invalid/improve-scope-triage-no-generated-on.yaml',
      'invalid/improve-scope-triage-tc-count-mismatch.yaml',
      'invalid/improve-scope-affected-spec-missing-summary.yaml',
      'invalid/improve-scope-impl-only-pending-spec.yaml',
    ]

    it.each(invalidFixtures)('%s — at least one violation detected', (fixturePath) => {
      const data = loadFixture(fixturePath)
      expect(validateImproveScope(data).length).toBeGreaterThan(0)
    })

  })

})
