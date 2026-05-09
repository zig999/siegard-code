import { describe, it, expect } from 'vitest'
import { existsSync } from 'fs'
import { join } from 'path'
import { getDistDir, loadFixture } from './helpers/load.js'
import { validate, loadAndCompile } from './helpers/schema.js'

const DIST_DIR = getDistDir()

// ─── File paths ───────────────────────────────────────────────────────────────

const FE_VALIDATE_CMD = join(DIST_DIR, 'commands', 'u-fe-validate.md')
const SCHEMA_FILE     = join(DIST_DIR, 'skills', 'u-shared-templates', 'fe-validate-report.schema.yaml')
const TEMPLATE_FILE   = join(DIST_DIR, 'skills', 'u-shared-templates', 'fe-validate-report.yaml')

// ─── Suite 1 — File existence (artifacts present in dist/.claude) ─────────────

describe('Layer 5 — Design System Config: file existence', () => {
  const REQUIRED_FILES = [
    ['u-fe-validate command',          FE_VALIDATE_CMD],
    ['fe-validate-report.schema.yaml', SCHEMA_FILE],
    ['fe-validate-report.yaml',        TEMPLATE_FILE],
  ]

  it.each(REQUIRED_FILES)('%s — exists', (_, filePath) => {
    expect(existsSync(filePath), `File not found: ${filePath}`).toBe(true)
  })
})

// ─── Suite 5 — fe-validate-report schema validation ──────────────────────────

describe('Layer 5 — Design System Config: fe-validate-report schema', () => {
  it('schema compiles without errors', () => {
    expect(() => loadAndCompile(SCHEMA_FILE)).not.toThrow()
  })

  describe('valid fixtures pass schema', () => {
    const VALID_FIXTURES = [
      ['fe-validate-report (rejected)',          'valid/fe-validate-report.yaml'],
      ['fe-validate-report (approved)',          'valid/fe-validate-report-approved.yaml'],
      ['fe-validate-report (approved_with_caveats)', 'valid/fe-validate-report-caveats.yaml'],
    ]

    it.each(VALID_FIXTURES)('%s', (_, fixturePath) => {
      const data   = loadFixture(fixturePath)
      const result = validate(SCHEMA_FILE, data)
      const errors = result.errors.map(e => `${e.instancePath} ${e.message}`).join('\n')
      expect(result.valid, `Schema validation failed:\n${errors}`).toBe(true)
    })
  })

  describe('invalid fixtures fail schema', () => {
    const INVALID_FIXTURES = [
      ['missing meta field',              'invalid/fe-validate-report-missing-meta.yaml'],
      ['invalid verdict value',           'invalid/fe-validate-report-invalid-verdict.yaml'],
      ['invalid run_id pattern',          'invalid/fe-validate-report-invalid-run-id.yaml'],
      ['invalid finding severity value',  'invalid/fe-validate-report-invalid-finding-severity.yaml'],
      ['wrong validated_by value',        'invalid/fe-validate-report-wrong-validated-by.yaml'],
    ]

    it.each(INVALID_FIXTURES)('%s — rejected by schema', (_, fixturePath) => {
      const data   = loadFixture(fixturePath)
      const result = validate(SCHEMA_FILE, data)
      expect(result.valid, `Expected schema to reject: ${fixturePath}`).toBe(false)
    })
  })

  describe('verdict business rules', () => {
    it('approved fixture has summary.total == 0', () => {
      const data = loadFixture('valid/fe-validate-report-approved.yaml')
      expect(data.summary.total).toBe(0)
      expect(data.verdict).toBe('approved')
    })

    it('approved_with_caveats fixture has no critical or high findings', () => {
      const data = loadFixture('valid/fe-validate-report-caveats.yaml')
      expect(data.summary.critical).toBe(0)
      expect(data.summary.high).toBe(0)
      expect(data.summary.total).toBeGreaterThan(0)
      expect(data.verdict).toBe('approved_with_caveats')
    })

    it('rejected fixture has at least one critical finding', () => {
      const data = loadFixture('valid/fe-validate-report.yaml')
      expect(data.summary.critical).toBeGreaterThan(0)
      expect(data.verdict).toBe('rejected')
    })

    it('summary.total equals sum of all severity counts', () => {
      for (const fixturePath of [
        'valid/fe-validate-report.yaml',
        'valid/fe-validate-report-approved.yaml',
        'valid/fe-validate-report-caveats.yaml',
      ]) {
        const data = loadFixture(fixturePath)
        const sum  = data.summary.critical + data.summary.high + data.summary.medium + data.summary.low
        expect(sum, `summary.total mismatch in ${fixturePath}`).toBe(data.summary.total)
      }
    })

    it('findings array length matches summary.total', () => {
      for (const fixturePath of [
        'valid/fe-validate-report.yaml',
        'valid/fe-validate-report-approved.yaml',
        'valid/fe-validate-report-caveats.yaml',
      ]) {
        const data = loadFixture(fixturePath)
        expect(data.findings.length, `findings.length mismatch in ${fixturePath}`).toBe(data.summary.total)
      }
    })
  })
})
