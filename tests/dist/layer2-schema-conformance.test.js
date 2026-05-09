import { describe, it, expect } from 'vitest'
import { join, basename, resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { getAllSchemaFiles, loadFixture } from './helpers/load.js'
import { loadAndCompile, validate, compileAllSchemas } from './helpers/schema.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SCHEMA_DIR = resolve(__dirname, '../../dist/.claude/skills/u-shared-templates')

// Maps each schema to its valid fixture and any invalid fixtures that must fail it
const SCHEMA_FIXTURE_MAP = {
  'task_contract.schema.yaml': {
    valid: 'valid/task-contract.yaml',
    invalid: [
      'invalid/task-contract-scope-both.yaml',
      'invalid/task-contract-estimate-l.yaml',
    ],
    extraValid: ['valid/task-contract-no-constraints.yaml'],
  },
  'handoff-manifest.schema.yaml': {
    valid: 'valid/handoff-manifest.yaml',
    invalid: ['invalid/handoff-manifest-empty-domains.yaml'],
  },
  'validation-result.schema.yaml': {
    valid: 'valid/validation-result.yaml',
    invalid: [],
  },
  'blocked-report.schema.yaml': {
    valid: 'valid/blocked-report.yaml',
    invalid: [],
  },
  'cr.schema.yaml': {
    valid: 'valid/cr.yaml',
    invalid: [],
  },
  'be-to-fe-handoff.schema.yaml': {
    valid: 'valid/be-to-fe-handoff.yaml',
    invalid: [
      'invalid/be-to-fe-handoff-empty-endpoints.yaml',
      'invalid/be-to-fe-handoff-wrong-status.yaml',
    ],
    extraValid: ['valid/be-to-fe-handoff-with-deviations.yaml'],
  },
  'ui-agent-output.schema.yaml': {
    valid: 'valid/ui-agent-output.yaml',
    invalid: ['invalid/ui-agent-output-no-tasks.yaml'],
  },
  'security-finding.schema.yaml': {
    valid: 'valid/security-finding.yaml',
    invalid: ['invalid/security-finding-wrong-verdict.yaml'],
    extraValid: ['valid/security-finding-blocked.yaml'],
  },
  'architecture-finding.schema.yaml': {
    valid: 'valid/architecture-finding.yaml',
    invalid: ['invalid/architecture-finding-empty-deliveries.yaml'],
    extraValid: ['valid/architecture-finding-with-findings.yaml'],
  },
  'improve-handoff-envelope.schema.yaml': {
    valid: 'valid/improve-handoff-envelope.yaml',
    invalid: [
      'invalid/improve-handoff-envelope-bad-id.yaml',
      'invalid/improve-handoff-envelope-missing-return-contract.yaml',
      'invalid/improve-handoff-envelope-bad-mode-hint.yaml',
      'invalid/improve-handoff-envelope-bad-source.yaml',
      'invalid/improve-handoff-envelope-empty-improve-session.yaml',
      'invalid/improve-handoff-envelope-update-field-wrong.yaml',
      'invalid/improve-handoff-envelope-missing-execution-policy.yaml',
      'invalid/improve-handoff-envelope-bad-pipeline.yaml',
    ],
    extraValid: [
      'valid/improve-handoff-envelope-fast-track-patch.yaml',
      'valid/improve-handoff-envelope-full.yaml',
      'valid/improve-handoff-envelope-lean.yaml',
      'valid/improve-handoff-envelope-no-tdd.yaml',
    ],
  },
  'spec-changelog-notify.schema.yaml': {
    valid: 'valid/spec-changelog-notify.yaml',
    invalid: [
      'invalid/spec-changelog-notify-bad-origin.yaml',
      'invalid/spec-changelog-notify-empty-changed-files.yaml',
    ],
  },
  'handoff-receipt.schema.yaml': {
    valid: 'valid/handoff-receipt.yaml',
    invalid: [
      'invalid/handoff-receipt-bad-consumer.yaml',
      'invalid/handoff-receipt-bad-hash.yaml',
    ],
    extraValid: ['valid/handoff-receipt-halted.yaml'],
  },
  'handoff-validation-envelope.schema.yaml': {
    valid: 'valid/handoff-validation-envelope-valid.yaml',
    invalid: ['invalid/handoff-validation-envelope-valid-with-errors.yaml'],
    extraValid: ['valid/handoff-validation-envelope-invalid.yaml'],
  },
}

describe('Layer 2 — Schema Conformance', () => {
  describe('all schemas compile without errors', () => {
    const results = compileAllSchemas()

    it('at least one schema found', () => {
      expect(results.length).toBeGreaterThan(0)
    })

    it.each(results.map(r => [basename(r.file), r]))(
      '%s — compiles successfully',
      (_, result) => {
        expect(result.compiled, result.error ?? '').toBe(true)
      }
    )
  })

  describe('valid fixtures pass their schemas', () => {
    for (const [schemaName, { valid }] of Object.entries(SCHEMA_FIXTURE_MAP)) {
      it(`${valid} is valid against ${schemaName}`, () => {
        const schemaFile = join(SCHEMA_DIR, schemaName)
        const data = loadFixture(valid)
        const result = validate(schemaFile, data)
        expect(result.valid, JSON.stringify(result.errors, null, 2)).toBe(true)
      })
    }
  })

  describe('invalid fixtures fail their schemas', () => {
    for (const [schemaName, { invalid }] of Object.entries(SCHEMA_FIXTURE_MAP)) {
      for (const invalidFixture of invalid) {
        it(`${invalidFixture} fails ${schemaName}`, () => {
          const schemaFile = join(SCHEMA_DIR, schemaName)
          const data = loadFixture(invalidFixture)
          const result = validate(schemaFile, data)
          expect(result.valid).toBe(false)
        })
      }
    }
  })

  describe('extra valid fixtures pass their schemas', () => {
    for (const [schemaName, entry] of Object.entries(SCHEMA_FIXTURE_MAP)) {
      for (const extraFixture of (entry.extraValid ?? [])) {
        it(`${extraFixture} is valid against ${schemaName}`, () => {
          const schemaFile = join(SCHEMA_DIR, schemaName)
          const data = loadFixture(extraFixture)
          const result = validate(schemaFile, data)
          expect(result.valid, JSON.stringify(result.errors, null, 2)).toBe(true)
        })
      }
    }
  })
})
