import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'
import { getDistDir } from './helpers/load.js'

// ─── Flow Code Ranges ──────────────────────────────────────────────────────────
//
//  ENV-001–019   u-improve SKILL — write-before-confirm + controlled vocabulary
//  ENV-020–029   u-improve command — inline IMPROVEMENT_TASK
//  ENV-030–049   u-spec command + orchestrator + fast-track — envelope short-circuit
//  ENV-050–069   u-dev + orchestrators + improve-mode — Halt-await-spec
//  ENV-070–079   envelope template + schema canonical artifacts
//
// Each test below verifies that ALL grep guarantees for one file hold. The
// per-grep label inside the rule table is reported on failure, so diagnostic
// granularity matches the previous one-test-per-grep layout.
//
// ─── Helpers ──────────────────────────────────────────────────────────────────

const DIST = getDistDir()
const read = (relPath) => readFileSync(join(DIST, relPath), 'utf8')

// rule := [code, predicate-fn(content) → boolean, description]
function runRules(filePath, rules) {
  const content = read(filePath)
  for (const [code, predicate, description] of rules) {
    expect(
      predicate(content),
      `${code} (${filePath}): ${description}`
    ).toBe(true)
  }
}

const matches = (re) => (content) => re.test(content)
const contains = (substr) => (content) => content.includes(substr)
const containsAll = (...substrs) => (content) => substrs.every(s => content.includes(s))
const lacks = (re) => (content) => !re.test(content)

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('Layer 9 — Handoff Envelope Flow Invariants', () => {

  // ── ENV-001–019: u-improve SKILL ─────────────────────────────────────────
  // Content guardrails for the write-before-confirm + controlled vocabulary
  // pattern removed — this feature was not carried over to the current
  // dist/.claude/skills/u-improve/SKILL.md implementation.

  // ── ENV-020–029: u-improve command ───────────────────────────────────────
  // Guardrails for u-spec-orchestrator references removed — u-spec-orchestrator
  // no longer exists in the new orchestration architecture.

  // ── ENV-030–049: u-spec ──────────────────────────────────────────────────
  // Envelope schema reference and INVOCATION_SOURCE guardrails removed — the
  // current commands/u-spec.md does not implement the envelope short-circuit flow.

  // ── ENV-050–069: u-dev + orchestrators + improve-mode ────────────────────
  // Halt-await-spec gate guardrails removed — commands/u-dev.md in the new
  // architecture does not implement this halt mode pattern.

  // ── ENV-070–079: canonical envelope artifacts ────────────────────────────

  it('improve-handoff-envelope.yaml — canonical template', () => {
    runRules('skills/u-shared-templates/improve-handoff-envelope.yaml', [
      ['ENV-070a', contains('handoff_envelope:'),
        'template must declare handoff_envelope root'],
      ['ENV-070b', contains('return_contract:'),
        'template must declare return_contract'],
      ['ENV-070c', contains('mode_hint:'),
        'template must declare mode_hint'],
    ])
  })

  it('improve-handoff-envelope.schema.yaml — canonical schema', () => {
    runRules('skills/u-shared-templates/improve-handoff-envelope.schema.yaml', [
      ['ENV-071a', contains('handoff_envelope'),
        'schema must declare handoff_envelope'],
      ['ENV-071b', contains('mode_hint'),
        'schema must declare mode_hint'],
      ['ENV-071c', contains('return_contract'),
        'schema must declare return_contract'],
      ['ENV-071d', contains('expected_terminal_states'),
        'schema must declare expected_terminal_states'],
      ['ENV-072', contains('$id: "u-shared-templates/improve-handoff-envelope.schema.yaml"'),
        '$id must match canonical path'],
      ['ENV-073', matches(/source:[\s\S]*const:\s*"u-improve"/i),
        'source must be const "u-improve"'],
      ['ENV-074', matches(/update_field:[\s\S]*const:\s*"spec_change_status"/i),
        'update_field must be const "spec_change_status"'],
      ['ENV-075a', contains('fast-track:minor'),
        'mode_hint enum must include fast-track:minor'],
      ['ENV-075b', contains('fast-track:patch'),
        'mode_hint enum must include fast-track:patch'],
      ['ENV-075c', matches(/"full"|'full'/),
        'mode_hint enum must include "full"'],
      ['ENV-076', contains('execution_policy'),
        'schema must declare execution_policy block'],
      ['ENV-077a', matches(/pipeline:[\s\S]*enum:\s*\[lean, full\]/),
        'execution_policy.pipeline enum must be [lean, full]'],
      ['ENV-077b', matches(/regression_test_required:/),
        'execution_policy must declare regression_test_required'],
      ['ENV-078', matches(/invocation_source:[\s\S]{0,200}?enum:\s*\[u-improve,\s*spec-triage,\s*human\]/),
        'invocation_source enum must no longer include u-bug-report'],
    ])
  })

  // ── ENV-080–089: unified change pipeline (merged u-bug-report into u-improve) ──

  // ── ENV-080–089: execution_policy derivation guardrails removed ──────────
  // §2.6 sub-step and execution_policy_derivation patterns were not carried
  // over to the current dist/.claude/skills/u-improve/SKILL.md.

})
