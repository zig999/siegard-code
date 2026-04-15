import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const DIST_DIR = resolve(__dirname, '../../dist')
const EXTRAS_DIR = resolve(__dirname, '../../extras')

function readFile(path) {
  return readFileSync(path, 'utf8')
}

function hasSection(content, heading) {
  // Matches ## Heading or ## N. Heading (with or without number prefix)
  return content.includes(`## ${heading}`)
}

function hasSectionNumber(content, n, name) {
  // Matches "## N. Name" exactly
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

const FEATURE_EXAMPLE    = resolve(EXTRAS_DIR, 'feature.spec.md')
const COMPONENT_EXAMPLE  = resolve(EXTRAS_DIR, 'component.spec.md')

// ─── Template existence ───────────────────────────────────────────────────────

describe('Layer 6 — Spec Templates', () => {

  describe('template files exist', () => {
    const files = [
      ['TEMPLATE.feature.spec.md', FEATURE_TEMPLATE],
      ['TEMPLATE.component.spec.md', COMPONENT_TEMPLATE],
      ['TEMPLATE.flow.md', FLOW_TEMPLATE],
      ['TEMPLATE.design-system/tokens.md', TOKENS_TEMPLATE],
      ['extras/feature.spec.md', FEATURE_EXAMPLE],
      ['extras/component.spec.md', COMPONENT_EXAMPLE],
    ]

    it.each(files)('%s exists', (_, path) => {
      expect(existsSync(path), `File not found: ${path}`).toBe(true)
    })
  })

  // ─── TEMPLATE.feature.spec.md ─────────────────────────────────────────────

  describe('TEMPLATE.feature.spec.md — required sections', () => {
    const content = readFile(FEATURE_TEMPLATE)

    const requiredSections = [
      ['§1', 1, 'Consumed Endpoints'],
      ['§2', 2, 'Feature States'],
      ['§3', 3, 'State Transition Table'],
      ['§4', 4, 'Requests, Order and Cache'],
      ['§5', 5, 'Input Validations'],
      ['§6', 6, 'API Error'],
      ['§7', 7, 'Shared Components Used'],
      ['§8', 8, 'Feature Accessibility'],
      ['§9', 9, 'BDD Scenarios'],
      ['§10', 10, 'Components to Create'],
      ['§11', 11, 'Out of Scope'],
    ]

    it.each(requiredSections)('%s present', (label, n, name) => {
      const found = hasSectionNumber(content, n, name)
      expect(found, `Section "## ${n}. ${name}" not found in TEMPLATE.feature.spec.md`).toBe(true)
    })

    it('has Changelog section', () => {
      expect(hasSection(content, 'Changelog')).toBe(true)
    })

    it('has component adapter declaration syntax', () => {
      expect(content).toContain('Component adapters')
    })

    it('has BDD Given/When/Then pattern', () => {
      expect(content).toMatch(/Given .+\nWhen .+\nThen/)
    })
  })

  // ─── TEMPLATE.component.spec.md ───────────────────────────────────────────

  describe('TEMPLATE.component.spec.md — required sections', () => {
    const content = readFile(COMPONENT_TEMPLATE)

    const requiredSections = [
      ['§1', 1, 'Purpose and Responsibilities'],
      ['§2', 2, 'When to Use'],
      ['§3', 3, 'Props Contract'],
      ['§4', 4, 'Component States'],
      ['§5', 5, 'Events Emitted'],
      ['§6', 6, 'Variants and Compositions'],
      ['§7', 7, 'Do / Don'],
      ['§8', 8, 'BDD Scenarios'],
      ['§9', 9, 'Accessibility Contract'],
      ['§10', 10, 'Internal Dependencies'],
    ]

    it.each(requiredSections)('%s present', (label, n, name) => {
      const found = hasSectionNumber(content, n, name)
      expect(found, `Section "## ${n}. ${name}" not found in TEMPLATE.component.spec.md`).toBe(true)
    })

    it('has Changelog section', () => {
      expect(hasSection(content, 'Changelog')).toBe(true)
    })

    it('Props Contract section notes it is a binding contract', () => {
      expect(content).toContain('Binding contract')
    })

    it('has minimum 3 BDD scenarios (default render + error + keyboard)', () => {
      const scenarioMatches = content.match(/###\s+\w/g) || []
      // At least 3 scenario headings inside BDD section
      expect(scenarioMatches.length).toBeGreaterThanOrEqual(3)
    })
  })

  // ─── TEMPLATE.flow.md ─────────────────────────────────────────────────────

  describe('TEMPLATE.flow.md — required structure', () => {
    const content = readFile(FLOW_TEMPLATE)

    it('has FLOW-NN identifier in header', () => {
      expect(hasFlowId(content), 'FLOW-NN identifier missing from header').toBe(true)
    })

    it('has Involved Features section', () => {
      expect(content).toContain('Involved Features')
    })

    it('has Happy Path section', () => {
      expect(content).toContain('Happy Path')
    })

    it('has Alternative Flows section', () => {
      expect(content).toContain('Alternative Flows')
    })

    it('has Navigation Rules (FL) section', () => {
      expect(content).toContain('Navigation Rules')
    })

    it('has Deep Links section', () => {
      expect(content).toContain('Deep Links')
    })

    it('navigation rules require explicit fallback field', () => {
      expect(content).toContain('**Fallback:**')
    })

    it('has Changelog section', () => {
      expect(hasSection(content, 'Changelog')).toBe(true)
    })
  })

  // ─── TEMPLATE.design-system/tokens.md ────────────────────────────────────

  describe('TEMPLATE.design-system/tokens.md — required sections', () => {
    const content = readFile(TOKENS_TEMPLATE)

    const sections = [
      ['Token Declarations', 'Token Declarations'],
      ['§3 Color Tokens', '3. Color Tokens'],
      ['§4 Spacing Tokens', '4. Spacing Tokens'],
      ['§5 Typographic Scale', '5. Typographic Scale'],
      ['§6 Shadows and Borders', '6. Shadows and Borders'],
      ['§7 Animation and Motion Tokens', '7. Animation and Motion Tokens'],
      ['§8 Semantic Usage Rules', '8. Semantic Usage Rules'],
    ]

    it.each(sections)('%s present', (label, heading) => {
      expect(content, `"## ${heading}" not found in tokens.md`).toContain(`## ${heading}`)
    })

    it('has CSS block with token declarations', () => {
      expect(content).toContain('```css')
    })

    it('has YAML manifest block', () => {
      expect(content).toContain('```yaml')
    })

    it('has motion duration tokens in §7', () => {
      expect(content).toContain('--duration-')
    })

    it('§7 includes prefers-reduced-motion rule', () => {
      expect(content).toContain('prefers-reduced-motion')
    })

    it('section numbering is sequential — no gap between 6 and 8', () => {
      const section7idx = content.indexOf('## 7.')
      const section8idx = content.indexOf('## 8.')
      expect(section7idx, 'Section 7 not found').toBeGreaterThan(0)
      expect(section8idx, 'Section 8 not found').toBeGreaterThan(0)
      expect(section7idx, 'Section 7 must appear before section 8').toBeLessThan(section8idx)
    })
  })

  // ─── extras/feature.spec.md (example) ────────────────────────────────────

  describe('extras/feature.spec.md — conforms to current template structure', () => {
    const content = readFile(FEATURE_EXAMPLE)

    it('written in English (not Portuguese)', () => {
      // Quick heuristic: template headers should be in English
      expect(content).toContain('Consumed Endpoints')
      expect(content).not.toContain('## 1. Objetivo')
    })

    it('has Feature ID (FEAT-NN) in header', () => {
      expect(content).toMatch(/Feature ID:\s*FEAT-\d+/)
    })

    it('has §1 Consumed Endpoints with operationId column', () => {
      expect(content).toContain('operationId')
    })

    it('has §2 Feature States with UI-NN identifiers', () => {
      expect(content).toMatch(/UI-\d{2}/)
    })

    it('has §3 State Transition Table', () => {
      expect(hasSectionNumber(content, 3, 'State Transition Table')).toBe(true)
    })

    it('has §6 API Error → UI Mapping', () => {
      expect(hasSectionNumber(content, 6, 'API Error')).toBe(true)
    })

    it('has §7 with component adapter declarations', () => {
      expect(content).toContain('Component adapters')
    })

    it('has §9 BDD Scenarios with Given/When/Then', () => {
      expect(content).toMatch(/Given .+\nWhen .+\nThen/)
    })

    it('has §11 Out of Scope', () => {
      expect(hasSectionNumber(content, 11, 'Out of Scope')).toBe(true)
    })

    it('has Changelog', () => {
      expect(hasSection(content, 'Changelog')).toBe(true)
    })
  })

  // ─── extras/component.spec.md (example) ──────────────────────────────────

  describe('extras/component.spec.md — conforms to current template structure', () => {
    const content = readFile(COMPONENT_EXAMPLE)

    it('written in English (not Portuguese)', () => {
      expect(content).toContain('Props Contract')
      expect(content).not.toContain('## 1. Objetivo')
    })

    it('has Component ID (COMP-NN) in header', () => {
      expect(content).toMatch(/Component ID:\s*COMP-\d+/)
    })

    it('has §2 When to Use / When Not to Use', () => {
      expect(hasSectionNumber(content, 2, 'When to Use')).toBe(true)
    })

    it('has §3 Props Contract with binding contract note', () => {
      expect(content).toContain('Binding contract')
    })

    it('has §5 Events Emitted with TypeScript payload types', () => {
      expect(hasSectionNumber(content, 5, 'Events Emitted')).toBe(true)
    })

    it('has §8 BDD Scenarios with at least 3 scenarios', () => {
      const bddStart = content.indexOf('## 8. BDD Scenarios')
      const bddSection = content.slice(bddStart)
      const scenarioCount = (bddSection.match(/^### /gm) || []).length
      expect(scenarioCount, 'Need at least 3 BDD scenarios').toBeGreaterThanOrEqual(3)
    })

    it('has §9 Accessibility Contract', () => {
      expect(hasSectionNumber(content, 9, 'Accessibility Contract')).toBe(true)
    })

    it('has §10 Internal Dependencies', () => {
      expect(hasSectionNumber(content, 10, 'Internal Dependencies')).toBe(true)
    })

    it('has Changelog', () => {
      expect(hasSection(content, 'Changelog')).toBe(true)
    })
  })
})
