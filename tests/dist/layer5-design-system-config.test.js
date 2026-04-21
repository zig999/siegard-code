import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'fs'
import { join } from 'path'
import { getDistDir, loadYaml, loadFixture } from './helpers/load.js'
import { validate, loadAndCompile } from './helpers/schema.js'

const DIST_DIR = getDistDir()

// ─── File paths ───────────────────────────────────────────────────────────────

const CLAUDE_FRONTEND   = join(DIST_DIR, '..', 'dist', 'templates', 'CLAUDE.frontend.md')
const CLAUDE_FULLSTACK  = join(DIST_DIR, '..', 'dist', 'templates', 'CLAUDE.fullstack.md')
const PROTOCOL_DEV      = join(DIST_DIR, 'agents', 'dev', 'protocols', 'u-fe-context-mounting-developer.md')
const PROTOCOL_UI       = join(DIST_DIR, 'agents', 'dev', 'protocols', 'u-fe-context-mounting-ui.md')
const FE_VALIDATE_SKILL = join(DIST_DIR, 'skills', 'u-fe-validate', 'SKILL.md')
const FE_VALIDATE_CMD   = join(DIST_DIR, 'commands', 'u-fe-validate.md')
const SCHEMA_FILE       = join(DIST_DIR, 'skills', 'u-shared-templates', 'fe-validate-report.schema.yaml')
const TEMPLATE_FILE     = join(DIST_DIR, 'skills', 'u-shared-templates', 'fe-validate-report.yaml')

// Canonical default values — single source of truth in CLAUDE.md template comments.
// Any change here must be reflected in both templates and both context mounting protocols.
const CANONICAL_DEFAULTS = {
  path:              '{specs_dir}/front/design-system/',
  token_prefix:      '"--color-"',
  color_mode:        'both',
  component_library: 'none',
  enforce_tokens:    'true',
  motion_policy:     'strict',
}

const CANONICAL_DEFAULTS_LINE =
  `path = ${CANONICAL_DEFAULTS.path}, ` +
  `token_prefix = ${CANONICAL_DEFAULTS.token_prefix}, ` +
  `color_mode = ${CANONICAL_DEFAULTS.color_mode}, ` +
  `component_library = ${CANONICAL_DEFAULTS.component_library}, ` +
  `enforce_tokens = ${CANONICAL_DEFAULTS.enforce_tokens}, ` +
  `motion_policy = ${CANONICAL_DEFAULTS.motion_policy}`

// ─── Helpers ──────────────────────────────────────────────────────────────────

function readText(filePath) {
  return readFileSync(filePath, 'utf8')
}

// ─── Suite 1 — File existence ─────────────────────────────────────────────────

describe('Layer 5 — Design System Config: file existence', () => {
  const REQUIRED_FILES = [
    ['CLAUDE.frontend.md template',             CLAUDE_FRONTEND],
    ['CLAUDE.fullstack.md template',            CLAUDE_FULLSTACK],
    ['context-mounting-developer protocol',     PROTOCOL_DEV],
    ['context-mounting-ui protocol',            PROTOCOL_UI],
    ['u-fe-validate SKILL.md',                  FE_VALIDATE_SKILL],
    ['u-fe-validate command',                   FE_VALIDATE_CMD],
    ['fe-validate-report.schema.yaml',          SCHEMA_FILE],
    ['fe-validate-report.yaml template',        TEMPLATE_FILE],
  ]

  it.each(REQUIRED_FILES)('%s — exists', (_, filePath) => {
    expect(existsSync(filePath), `File not found: ${filePath}`).toBe(true)
  })
})

// ─── Suite 2 — CLAUDE.md templates contain design_system block ───────────────

describe('Layer 5 — Design System Config: CLAUDE.md templates', () => {
  const TEMPLATES = [
    ['CLAUDE.frontend.md', CLAUDE_FRONTEND],
    ['CLAUDE.fullstack.md', CLAUDE_FULLSTACK],
  ]

  it.each(TEMPLATES)('%s — contains design_system: block', (_, filePath) => {
    const content = readText(filePath)
    expect(content).toContain('design_system:')
  })

  it.each(TEMPLATES)('%s — declares all 5 config fields', (_, filePath) => {
    const content = readText(filePath)
    for (const field of Object.keys(CANONICAL_DEFAULTS)) {
      expect(content, `Missing field "${field}" in ${filePath}`).toContain(`${field}:`)
    }
  })

  it.each(TEMPLATES)('%s — canonical defaults comment block declares each field with the canonical value', (_, filePath) => {
    const content = readText(filePath)
    expect(content).toContain('design_system block is optional')
    const commentBlock = content.split('Canonical defaults')[1] ?? ''
    expect(commentBlock, 'Canonical defaults marker not found').not.toBe('')
    // Pin both the field name AND the value — protects against a rename or a
    // silent default change. CANONICAL_DEFAULTS at the top of this file is the
    // single source of truth.
    for (const [field, value] of Object.entries(CANONICAL_DEFAULTS)) {
      expect(
        commentBlock,
        `Canonical default "${field}: ${value}" missing in ${filePath}`
      ).toMatch(new RegExp(`${field}:\\s+${value.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&')}`))
    }
  })

  it('CLAUDE.frontend.md and CLAUDE.fullstack.md have identical canonical defaults', () => {
    const front     = readText(CLAUDE_FRONTEND)
    const fullstack = readText(CLAUDE_FULLSTACK)

    const extractCommentBlock = (text) => {
      const marker = 'Canonical defaults'
      const start  = text.indexOf(marker)
      if (start === -1) return ''
      // Take the next 6 lines after the marker
      return text.slice(start).split('\n').slice(0, 7).join('\n')
    }

    expect(extractCommentBlock(front)).toBe(extractCommentBlock(fullstack))
  })
})

// ─── Suite 3 — Context mounting protocols are consistent ─────────────────────

describe('Layer 5 — Design System Config: context mounting protocol consistency', () => {
  const PROTOCOLS = [
    ['u-fe-context-mounting-developer.md', PROTOCOL_DEV],
    ['u-fe-context-mounting-ui.md',        PROTOCOL_UI],
  ]

  const REQUIRED_FIELDS = Object.keys(CANONICAL_DEFAULTS).map(f => `design_system.${f}`)

  it.each(PROTOCOLS)('%s — references all 5 design_system fields', (_, filePath) => {
    const content = readText(filePath)
    for (const field of REQUIRED_FIELDS) {
      expect(content, `Field "${field}" not referenced in ${filePath}`).toContain(field)
    }
  })

  it.each(PROTOCOLS)('%s — states design_system block is optional', (_, filePath) => {
    const content = readText(filePath)
    expect(content).toContain('design_system` block is optional')
  })

  it.each(PROTOCOLS)('%s — references canonical defaults in CLAUDE.md template', (_, filePath) => {
    const content = readText(filePath)
    // The protocols must delegate defaults to the CLAUDE.md template comment block
    // (text uses backtick-wrapped `CLAUDE.md` — test checks the unambiguous phrase)
    expect(content).toContain('template comment block')
  })

  it('both protocols carry identical defaults text', () => {
    const devText = readText(PROTOCOL_DEV)
    const uiText  = readText(PROTOCOL_UI)

    const extractDefaults = (text) => {
      const marker = 'CLAUDE.md template comment block'
      const start  = text.indexOf(marker)
      if (start === -1) return ''
      return text.slice(start, start + 300)
    }

    expect(extractDefaults(devText)).toBe(extractDefaults(uiText))
  })
})

// ─── Suite 4 — u-fe-validate SKILL documents config behavior ─────────────────

describe('Layer 5 — Design System Config: u-fe-validate SKILL', () => {
  it('has a Step 2 that reads design_system config from CLAUDE.md', () => {
    const content = readText(FE_VALIDATE_SKILL)
    expect(content).toContain('Step 2')
    expect(content).toContain('design_system')
    expect(content).toContain('CLAUDE.md')
  })

  it('documents effect of enforce_tokens: false', () => {
    const content = readText(FE_VALIDATE_SKILL)
    expect(content).toContain('enforce_tokens: false')
  })

  it('documents effect of motion_policy: permissive', () => {
    const content = readText(FE_VALIDATE_SKILL)
    expect(content).toContain('motion_policy: permissive')
  })

  it('specifies default for each of the 5 config fields', () => {
    const content = readText(FE_VALIDATE_SKILL)
    for (const [field, value] of Object.entries(CANONICAL_DEFAULTS)) {
      expect(
        content,
        `Default for "${field}" (${value}) not documented in SKILL`
      ).toContain(value)
    }
  })

  it('has Steps 1 through 6 in order', () => {
    const content = readText(FE_VALIDATE_SKILL)
    for (let i = 1; i <= 6; i++) {
      expect(content, `Step ${i} not found in SKILL`).toContain(`### Step ${i}`)
    }
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
