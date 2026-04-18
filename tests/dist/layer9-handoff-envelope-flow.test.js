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

  it('u-improve SKILL — write-before-confirm + controlled vocabulary', () => {
    runRules('skills/u-improve/SKILL.md', [
      ['ENV-001', matches(/Step 3a\b.*Write scope block/i),
        'Step 3a — Write scope block to session log (before confirmation)'],
      ['ENV-002', matches(/Step 3b\b.*handoff envelope/i),
        'Step 3b — Write handoff envelope to session log'],
      ['ENV-003', matches(/write-before-confirm/i),
        'must contain explicit write-before-confirm rule'],
      ['ENV-004', contains('pending_spec'),
        'must declare pending_spec as initial spec_change_status'],
      ['ENV-005', matches(/never print shell commands.*paste|do not print shell commands.*paste|spec_invocation:\s*agent_tool_direct/i),
        'must prohibit printing shell commands for human paste'],
      ['ENV-006', containsAll('confirm', 'skip-spec', 'abort'),
        'must define controlled-vocabulary tokens (confirm, skip-spec, abort)'],
      ['ENV-007', containsAll('skip-planner', 'keep-planner'),
        'must define skip-planner / keep-planner tokens for the planner gate'],
      ['ENV-008', matches(/scope_block_persistence[\s\S]*write-before-confirm/i),
        'behavioral rules table must include scope_block_persistence=write-before-confirm'],
      ['ENV-009', matches(/spec_invocation[\s\S]*agent_tool_direct/i),
        'behavioral rules table must include spec_invocation=agent_tool_direct'],
      ['ENV-010', matches(/confirmation_tokens/i),
        'behavioral rules table must include confirmation_tokens'],
      ['ENV-011', contains('improve-handoff-envelope.schema.yaml'),
        'must point to the canonical envelope schema'],
      ['ENV-012a', lacks(/Run \/u-spec.*\[S\/N\]/i),
        'forbid legacy [S/N] prompt for the spec gate'],
      ['ENV-012b', lacks(/Skip Planner and route directly to Developer\?\s*\[S\/N\]/i),
        'forbid legacy [S/N] prompt for the planner gate'],
      ['ENV-013', matches(/Step 4\b[\s\S]{0,400}?reserved/i),
        'Step 4 must be a reserved-marker (guards against drift back to old layout)'],
    ])
  })

  // ── ENV-020–029: u-improve command ───────────────────────────────────────

  it('u-improve command — inline IMPROVEMENT_TASK', () => {
    runRules('commands/u-improve.md', [
      ['ENV-020', contains('IMPROVEMENT_TASK'),
        'must declare IMPROVEMENT_TASK as a quoted-string variable'],
      ['ENV-021', matches(/Quoted string[\s\S]*IMPROVEMENT_TASK/i),
        'resolution order must document quoted-string handling'],
      ['ENV-022', matches(/invoking\s+`u-spec-orchestrator`|invokes?\s+`u-spec-orchestrator`/i),
        'must note SKILL invokes u-spec-orchestrator directly (no shell paste)'],
    ])
  })

  // ── ENV-030–049: u-spec ──────────────────────────────────────────────────

  it('u-spec command — INVOCATION_SOURCE + envelope short-circuit', () => {
    runRules('commands/u-spec.md', [
      ['ENV-030', contains('INVOCATION_SOURCE'),
        'must document INVOCATION_SOURCE variable'],
      ['ENV-031', matches(/human\s*\|\s*u-improve\s*\|\s*u-bug-report\s*\|\s*spec-triage/i),
        'must list allowed invocation_source values'],
      ['ENV-032', contains('improve-handoff-envelope.schema.yaml'),
        'must reference the envelope schema'],
      ['ENV-033', matches(/suppressed when INVOCATION_SOURCE\s*=\s*u-improve/i),
        'Y/N must be suppressed when invoked via u-improve'],
      ['ENV-034', matches(/Envelope short-circuit/i),
        'Mode Detection must have an explicit Envelope short-circuit section'],
    ])
  })

  it('u-spec orchestrator — envelope branch + return contract', () => {
    runRules('agents/spec/u-spec-orchestrator.md', [
      ['ENV-035', matches(/If invoked via handoff envelope from \/u-improve/i),
        'Step 0 must have an envelope branch'],
      ['ENV-036', contains('improve-handoff-envelope.schema.yaml'),
        'must validate envelope against canonical schema'],
      ['ENV-037a', contains('envelope_invalid'),
        'must emit envelope_invalid error'],
      ['ENV-037b', contains('envelope_mode_mismatch'),
        'must emit envelope_mode_mismatch error'],
      ['ENV-038', matches(/skip the.*Confirm\?.*\[Y\/N\]|except when.*invocation_source\s*=\s*u-improve/i),
        'must skip Y/N confirmation when invocation_source=u-improve'],
      ['ENV-039', matches(/Return contract.*envelope-driven handoffs/i),
        'Step 5 must declare Return contract section for envelope-driven handoffs'],
      ['ENV-040a', contains('spec_pipeline_return'),
        'Step 5 must emit spec_pipeline_return block'],
      ['ENV-040b', matches(/envelope_id:/),
        'spec_pipeline_return must reference envelope_id'],
      ['ENV-040c', matches(/spec_change_status:\s*completed/),
        'spec_pipeline_return must include spec_change_status: completed'],
      ['ENV-041', matches(/does NOT classify[\s\S]*mode_hint/i),
        'Step 1 must document envelope-driven validate-instead-of-classify rule'],
    ])
  })

  it('u-spec-fast-track protocol — envelope-aware', () => {
    runRules('agents/spec/protocols/u-spec-fast-track.md', [
      ['ENV-045', matches(/Envelope-driven invocation/i),
        'must have an Envelope-driven invocation section'],
      ['ENV-046', matches(/invocation_source/i),
        'record must require invocation_source field'],
      ['ENV-047a', matches(/improve_session/i),
        'record must require improve_session when envelope-driven'],
      ['ENV-047b', matches(/handoff_envelope\.id/i),
        'record must require handoff_envelope.id when envelope-driven'],
      ['ENV-048', contains('envelope_mode_mismatch'),
        'must mention envelope_mode_mismatch on incompatible mode_hint'],
    ])
  })

  // ── ENV-050–069: u-dev + orchestrators + improve-mode ────────────────────

  it('u-improve-mode protocol — pending_spec / failed handling', () => {
    runRules('agents/dev/protocols/u-improve-mode.md', [
      ['ENV-050', contains('pending_spec'),
        'schema must include pending_spec as a valid spec_change_status value'],
      ['ENV-051', contains('failed'),
        'schema must include failed as a valid spec_change_status value'],
      ['ENV-052', contains('handoff_manifest_id'),
        'schema must include handoff_manifest_id field'],
      ['ENV-053', matches(/pending_spec[\s\S]*NON-TERMINAL/i),
        'must declare pending_spec as non-terminal (no agent activation)'],
      ['ENV-054', matches(/Halt-await-spec/),
        'must define Halt-await-spec mode'],
      ['ENV-055', matches(/do not (prompt|ask) A\/B\/C|do NOT (ask|prompt) A\/B\/C|do NOT prompt A\/B\/C/i),
        'must explicitly forbid A/B/C-style prompts during halt'],
      ['ENV-056', contains('spec_pipeline_failed'),
        'must define failed as terminal failure with spec_pipeline_failed status'],
    ])
  })

  it('u-dev command — Halt-await-spec gate', () => {
    runRules('commands/u-dev.md', [
      ['ENV-060', matches(/Halt-await-spec/),
        'must surface Halt-await-spec gate in mode-based reading rules'],
      ['ENV-061', matches(/Failed-spec gate|spec_pipeline_failed/i),
        'must surface Failed-spec gate'],
      ['ENV-062', matches(/Source:.*handoff_manifest_id/),
        'estimate template must include Source line with handoff_manifest_id'],
    ])
  })

  it('FE orchestrator — pending_spec / failed in mode detection', () => {
    runRules('agents/dev/u-fe-orchestrator-core.md', [
      ['ENV-063', matches(/Halt-await-spec/),
        'mode-detection table must include Halt-await-spec'],
      ['ENV-064', matches(/Halt-spec-failed/),
        'mode-detection table must include Halt-spec-failed'],
      ['ENV-065', matches(/terminal state.*completed.*divergence_accepted.*not_required/i),
        'Quality gates must explicitly require terminal spec_change_status'],
    ])
  })

  it('BE orchestrator — pending_spec / failed in mode detection', () => {
    runRules('agents/dev/u-be-orchestrator-core.md', [
      ['ENV-066', matches(/Halt-await-spec/),
        'mode-detection table must include Halt-await-spec'],
      ['ENV-067', matches(/Halt-spec-failed/),
        'mode-detection table must include Halt-spec-failed'],
      ['ENV-068', matches(/terminal state.*completed.*divergence_accepted.*not_required/i),
        'Quality gates must explicitly require terminal spec_change_status'],
    ])
  })

  it('Fullstack meta-orchestrator — halt before Phase 1', () => {
    runRules('agents/dev/u-fullstack-orchestrator.md', [
      ['ENV-069', matches(/Halt before Phase 1[\s\S]*pending_spec[\s\S]*failed/i),
        'meta-orchestrator must halt before Phase 1 when spec_change_status=pending_spec or failed'],
    ])
  })

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

  it('u-improve SKILL — execution_policy derivation (Step 2.6)', () => {
    runRules('skills/u-improve/SKILL.md', [
      ['ENV-080', matches(/### 2\.6[\s\S]{0,100}?execution_policy/),
        'must declare §2.6 sub-step that derives execution_policy'],
      ['ENV-081', containsAll('pipeline: lean', 'pipeline: full'),
        'Step 2.6 must emit both pipeline values'],
      ['ENV-082', contains('regression_test_required'),
        'Step 2.6 must derive regression_test_required'],
      ['ENV-083', matches(/bug fix(es)?|bug fixes|bug-fix/i),
        'skill description must declare unified scope covering bug fixes'],
      ['ENV-084', matches(/execution_policy_derivation/),
        'behavioral rules table must include execution_policy_derivation'],
    ])
  })

  it('u-improve-mode protocol — lean pipeline and TDD discipline', () => {
    runRules('agents/dev/protocols/u-improve-mode.md', [
      ['ENV-085', matches(/execution_policy\.pipeline/),
        'must branch on execution_policy.pipeline'],
      ['ENV-086', matches(/PIPELINE-PROMOTION/),
        'must declare PIPELINE-PROMOTION boundary rule for lean pipeline'],
      ['ENV-087', matches(/regression_test_required: true[\s\S]*failing test/i),
        'must mandate a failing test when regression_test_required is true (TDD)'],
      ['ENV-088', matches(/SPEC-DIVERGENCE-ACCEPTED/),
        'must import the spec-divergence record flow from former u-bug-mode'],
      ['ENV-089', matches(/bug fix(es)?|merged|unified change/i),
        'must state that bug fixes are in scope (merged from former u-bug-mode)'],
    ])
  })

})
