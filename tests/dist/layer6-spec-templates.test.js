import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const DIST_DIR = resolve(__dirname, '../../dist/.claude')

function readFile(path) {
  return readFileSync(path, 'utf8')
}

function hasSection(content, heading) {
  return content.includes(`## ${heading}`)
}

function hasSectionNumber(content, n, name) {
  return new RegExp(`## ${n}\\.\\s+${name}`).test(content)
}

function hasFlowId(content) {
  return /Flow ID:\s*FLOW-\w+/.test(content) || content.includes('Flow ID: FLOW-NN')
}

// ─── Template paths ───────────────────────────────────────────────────────────

const FEATURE_TEMPLATE   = resolve(DIST_DIR, 'skills/u-spec-templates/TEMPLATE.feature.spec.md')
const COMPONENT_TEMPLATE = resolve(DIST_DIR, 'skills/u-spec-templates/TEMPLATE.component.spec.md')
const FLOW_TEMPLATE      = resolve(DIST_DIR, 'skills/u-spec-templates/TEMPLATE.flow.md')
const TOKENS_TEMPLATE    = resolve(DIST_DIR, 'skills/u-spec-templates/TEMPLATE.design-system/tokens.md')


// ─── Tests ────────────────────────────────────────────────────────────────────
//
// Every per-template suite below collapses N section-presence + content-rule
// tests into a single test per template that asserts everything in one pass.
// On failure, the first assertion message names the missing section/content,
// so diagnostic granularity is preserved.

describe('Layer 6 — Spec Templates', () => {

  describe('all template files exist', () => {
    const files = [
      ['TEMPLATE.feature.spec.md', FEATURE_TEMPLATE],
      ['TEMPLATE.component.spec.md', COMPONENT_TEMPLATE],
      ['TEMPLATE.flow.md', FLOW_TEMPLATE],
      ['TEMPLATE.design-system/tokens.md', TOKENS_TEMPLATE],
    ]

    it.each(files)('%s exists', (_, path) => {
      expect(existsSync(path), `File not found: ${path}`).toBe(true)
    })
  })

  // ── TEMPLATE.feature.spec.md ─────────────────────────────────────────────

  it('TEMPLATE.feature.spec.md — required sections + content rules', () => {
    const content = readFile(FEATURE_TEMPLATE)
    const requiredSections = [
      [1, 'Consumed Endpoints'],
      [2, 'Feature States'],
      [3, 'State Transition Table'],
      [4, 'Requests, Order and Cache'],
      [5, 'Input Validations'],
      [6, 'API Error'],
      [7, 'Shared Components Used'],
      [8, 'Feature Accessibility'],
      [9, 'BDD Scenarios'],
      [10, 'Components to Create'],
      [11, 'Out of Scope'],
    ]
    for (const [n, name] of requiredSections) {
      expect(
        hasSectionNumber(content, n, name),
        `Section "## ${n}. ${name}" not found in TEMPLATE.feature.spec.md`
      ).toBe(true)
    }
    expect(hasSection(content, 'Changelog'), 'Changelog section missing').toBe(true)
    expect(content, 'Component adapters declaration missing').toContain('Component adapters')
    expect(content, 'BDD Given/When/Then pattern missing').toMatch(/Given .+\nWhen .+\nThen/)
  })

  // ── TEMPLATE.component.spec.md ───────────────────────────────────────────

  it('TEMPLATE.component.spec.md — required sections + content rules', () => {
    const content = readFile(COMPONENT_TEMPLATE)
    const requiredSections = [
      [1, 'Purpose and Responsibilities'],
      [2, 'When to Use'],
      [3, 'Props Contract'],
      [4, 'Component States'],
      [5, 'Events Emitted'],
      [6, 'Variants and Compositions'],
      [7, 'Do / Don'],
      [8, 'BDD Scenarios'],
      [9, 'Accessibility Contract'],
      [10, 'Internal Dependencies'],
    ]
    for (const [n, name] of requiredSections) {
      expect(
        hasSectionNumber(content, n, name),
        `Section "## ${n}. ${name}" not found in TEMPLATE.component.spec.md`
      ).toBe(true)
    }
    expect(hasSection(content, 'Changelog'), 'Changelog section missing').toBe(true)
    expect(content, 'Props Contract binding-contract note missing').toContain('Binding contract')

    const scenarioMatches = content.match(/###\s+\w/g) || []
    expect(scenarioMatches.length, 'Need at least 3 BDD scenarios').toBeGreaterThanOrEqual(3)
  })

  // ── TEMPLATE.flow.md ─────────────────────────────────────────────────────

  it('TEMPLATE.flow.md — required structure', () => {
    const content = readFile(FLOW_TEMPLATE)
    expect(hasFlowId(content), 'FLOW-NN identifier missing from header').toBe(true)
    expect(content, 'Involved Features section missing').toContain('Involved Features')
    expect(content, 'Happy Path section missing').toContain('Happy Path')
    expect(content, 'Alternative Flows section missing').toContain('Alternative Flows')
    expect(content, 'Navigation Rules section missing').toContain('Navigation Rules')
    expect(content, 'Deep Links section missing').toContain('Deep Links')
    expect(content, 'Navigation rules require explicit Fallback field').toContain('**Fallback:**')
    expect(hasSection(content, 'Changelog'), 'Changelog section missing').toBe(true)
  })

  // ── TEMPLATE.design-system/tokens.md ────────────────────────────────────

  it('TEMPLATE.design-system/tokens.md — required sections + content rules', () => {
    const content = readFile(TOKENS_TEMPLATE)
    const sections = [
      'Token Declarations',
      '3. Color Tokens',
      '4. Spacing Tokens',
      '5. Typographic Scale',
      '6. Shadows and Borders',
      '7. Animation and Motion Tokens',
      '8. Semantic Usage Rules',
    ]
    for (const heading of sections) {
      expect(content, `"## ${heading}" not found in tokens.md`).toContain(`## ${heading}`)
    }
    expect(content, 'CSS block missing').toContain('```css')
    expect(content, 'YAML manifest block missing').toContain('```yaml')
    expect(content, 'motion duration tokens missing in §7').toContain('--duration-')
    expect(content, '§7 must include prefers-reduced-motion rule').toContain('prefers-reduced-motion')

    const section7idx = content.indexOf('## 7.')
    const section8idx = content.indexOf('## 8.')
    expect(section7idx, 'Section 7 not found').toBeGreaterThan(0)
    expect(section8idx, 'Section 8 not found').toBeGreaterThan(0)
    expect(section7idx, 'Section 7 must appear before section 8').toBeLessThan(section8idx)
  })

})
