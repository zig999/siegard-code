import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'fs'
import { join } from 'path'
import { getDistDir, parseFrontmatter } from './helpers/load.js'

const dist = getDistDir()
const read = (rel) => readFileSync(join(dist, rel), 'utf8')

function assertNotContains(content, pattern, label) {
  if (typeof pattern === 'string') {
    expect(content, label).not.toContain(pattern)
  } else {
    expect(content, label).not.toMatch(pattern)
  }
}

function assertContains(content, pattern, label) {
  if (typeof pattern === 'string') {
    expect(content, label).toContain(pattern)
  } else {
    expect(content, label).toMatch(pattern)
  }
}

describe('Layer 7 — Content Integrity Guardrails', () => {

  describe('DEV-I-01: ui-spec-gate field name', () => {
    it('GUARD-01: u-fe-ui.md must not contain task_contracts_covered', () => {
      const content = read('agents/dev/u-fe-ui.md')
      assertNotContains(content, 'task_contracts_covered', 'GUARD-01')
    })

    it('GUARD-02: u-fe-development/SKILL.md must not contain task_contracts_covered', () => {
      const content = read('skills/u-fe-development/SKILL.md')
      assertNotContains(content, 'task_contracts_covered', 'GUARD-02')
    })

    it('GUARD-03: ui-agent-output.schema.yaml must contain tasks_covered', () => {
      const schemaPath = join(dist, 'skills', 'u-shared-templates', 'ui-agent-output.schema.yaml')
      if (!existsSync(schemaPath)) return // schema may not exist yet in this branch
      const content = readFileSync(schemaPath, 'utf8')
      assertContains(content, 'tasks_covered', 'GUARD-03')
    })
  })

  describe('DEV-I-02: scope:both prohibited', () => {
    it('GUARD-04: u-fullstack-orchestrator.md must not contain "scope: both"', () => {
      const content = read('agents/dev/u-fullstack-orchestrator.md')
      assertNotContains(content, 'scope: both', 'GUARD-04')
    })

    it('GUARD-05: u-fullstack-coordination.md must not use "scope: both" as a valid value', () => {
      const content = read('agents/dev/protocols/u-fullstack-coordination.md')
      // The file may contain "scope: both" in prohibition notices — check it doesn't appear as a positive instruction
      // The only allowed occurrences are in "is prohibited" / "do not create" context
      const lines = content.split('\n').filter(l => l.includes('scope: both'))
      for (const line of lines) {
        expect(line.toLowerCase(), `Line "${line}" should only mention scope:both in prohibition context`).toMatch(
          /prohibited|do not|never|not allowed/i
        )
      }
    })
  })

  describe('SPEC-I-01: validation result filename', () => {
    it('GUARD-07: u-spec-orchestrator.md must not reference validation.md without -result', () => {
      const content = read('agents/spec/u-spec-orchestrator.md')
      assertNotContains(content, /\{domain\}-validation\.md/, 'GUARD-07')
      assertNotContains(content, /\*-validation\.md/, 'GUARD-07')
    })

    it('GUARD-07b: u-spec-orchestrator.md must contain validation-result.yaml', () => {
      const content = read('agents/spec/u-spec-orchestrator.md')
      assertContains(content, 'validation-result.yaml', 'GUARD-07b')
    })

    it('GUARD-08: u-spec-to-dev-handoff.md must not reference validation.md without -result', () => {
      const content = read('agents/spec/protocols/u-spec-to-dev-handoff.md')
      assertNotContains(content, '{domain}-validation.md', 'GUARD-08')
    })
  })

  describe('SPEC-I-02: cr-NN.yaml creation instruction', () => {
    it('GUARD-09: u-spec-orchestrator.md must contain cr-NN.yaml', () => {
      const content = read('agents/spec/u-spec-orchestrator.md')
      assertContains(content, 'cr-NN.yaml', 'GUARD-09a')
      assertContains(content, 'cr.schema.yaml', 'GUARD-09b')
    })

    it('GUARD-10: u-spec-versioning.md must contain cr-NN.yaml', () => {
      const content = read('agents/spec/protocols/u-spec-versioning.md')
      assertContains(content, 'cr-NN.yaml', 'GUARD-10')
    })

    it('GUARD-11: u-spec-to-dev-handoff.md must contain cr-NN.yaml gate check', () => {
      const content = read('agents/spec/protocols/u-spec-to-dev-handoff.md')
      assertContains(content, 'cr-NN.yaml', 'GUARD-11')
    })
  })

  describe('SPEC-I-03: reverse spec writer §1 columns', () => {
    it('GUARD-12: u-reverse-spec-writer.md must not list Method+Path in §1 context', () => {
      const content = read('agents/reverse-spec/u-reverse-spec-writer.md')
      // Check the §1 table description doesn't list Method+Path as a column
      const lines = content.split('\n')
      const sect1Idx = lines.findIndex(l => l.includes('§1 Consumed Endpoints'))
      if (sect1Idx >= 0) {
        const sect1Line = lines[sect1Idx]
        expect(sect1Line, 'GUARD-12a: §1 should not list Method+Path as column').not.toContain('Method+Path')
        expect(sect1Line, 'GUARD-12b: §1 should not list Auth required as column').not.toContain('Auth required')
      }
    })
  })

  describe('SPEC-I-04: spec validator model', () => {
    it('GUARD-13: u-spec-validator.md must use claude-sonnet-4-6 model', () => {
      const fm = parseFrontmatter(join(dist, 'agents/spec/u-spec-validator.md'))
      expect(fm.model, 'GUARD-13').toBe('claude-sonnet-4-6')
    })
  })

  describe('SPEC-I-05: cleanup permanent files list', () => {
    it('GUARD-14: u-spec-cleanup.md must contain all required permanent file types', () => {
      const content = read('agents/spec/protocols/u-spec-cleanup.md')
      assertContains(content, 'front/front.md', 'GUARD-14a')
      assertContains(content, 'design-system', 'GUARD-14b')
      assertContains(content, 'decisions.md', 'GUARD-14c')
      assertContains(content, 'handoff-manifest.yaml', 'GUARD-14d')
      assertContains(content, 'validation-result.yaml', 'GUARD-14e')
      assertContains(content, 'compliance.yaml', 'GUARD-14f')
    })
  })

  describe('SPEC-I-06: context-mounting design-system templates', () => {
    it('GUARD-15: u-spec-context-mounting.md must reference TEMPLATE.design-system', () => {
      const content = read('agents/spec/protocols/u-spec-context-mounting.md')
      assertContains(content, 'TEMPLATE.design-system', 'GUARD-15a')
      assertContains(content, 'TEMPLATE.design-system-rules.md', 'GUARD-15b')
    })
  })

  describe('DEV-I-04: BE orchestrator session-decisions path', () => {
    it('GUARD-16: u-be-orchestrator-core.md must not reference u-fe-templates for session-decisions', () => {
      const content = read('agents/dev/u-be-orchestrator-core.md')
      assertNotContains(content, 'u-fe-templates/session-decisions.md', 'GUARD-16a')
      assertContains(content, 'u-be-templates/session-decisions.md', 'GUARD-16b')
    })
  })

  describe('DEV-I-06: BE orchestrator decisions.md read', () => {
    it('GUARD-17: u-be-orchestrator-core.md Expected inputs must mention decisions.md', () => {
      const content = read('agents/dev/u-be-orchestrator-core.md')
      // Check decisions.md appears in expected inputs context
      assertContains(content, 'decisions.md', 'GUARD-17')
    })
  })

  describe('DEV-I-07: BE orchestrator environment validation', () => {
    it('GUARD-18: u-be-orchestrator-core.md must contain Step 0 with environment checks', () => {
      const content = read('agents/dev/u-be-orchestrator-core.md')
      assertContains(content, 'Step 0', 'GUARD-18a')
      assertContains(content, /git (rev-parse|initialized)/i, 'GUARD-18b')
      assertContains(content, /[Tt]est command/i, 'GUARD-18c')
    })
  })

  describe('DEV-I-08: BE developer qualified paths', () => {
    it('GUARD-19: u-be-developer.md must use qualified path for u-spec-feedback-loop', () => {
      const content = read('agents/dev/u-be-developer.md')
      // When spec-feedback-loop appears, it should be in a qualified path context
      const lines = content.split('\n').filter(l => l.includes('spec-feedback-loop'))
      for (const line of lines) {
        expect(line, `Line should have qualified path: "${line}"`).toContain('.claude/agents/spec/protocols/')
      }
    })
  })

  describe('DEV-I-09: architecture reviewer god_service threshold', () => {
    it('GUARD-20: u-architecture-reviewer.md must not use ≥20 for god_service detection', () => {
      const content = read('agents/dev/u-architecture-reviewer.md')
      // Check the god_service detection line
      const lines = content.split('\n').filter(l => l.includes('god_service') || l.includes('public methods'))
      const detectionLine = lines.find(l => l.includes('Detection') || l.includes('public methods'))
      if (detectionLine) {
        expect(detectionLine, 'GUARD-20: should not use ≥20').not.toContain('≥20')
        expect(detectionLine, 'GUARD-20: should not use "20 public methods"').not.toContain('20 public methods')
      }
    })
  })

  describe('DEV-I-10: CLAUDE templates tc-XX naming', () => {
    it('GUARD-22: CLAUDE.frontend.md must not contain us-XX-delivery', () => {
      const content = read('templates/CLAUDE.frontend.md')
      assertNotContains(content, 'us-XX-delivery', 'GUARD-22')
    })

    it('GUARD-23: CLAUDE.backend.md must not contain us-XX-delivery', () => {
      const content = read('templates/CLAUDE.backend.md')
      assertNotContains(content, 'us-XX-delivery', 'GUARD-23')
    })
  })

  describe('SPEC-I-07: analyzer no duplicate section numbers', () => {
    it('GUARD-24: u-reverse-spec-analyzer.md must have no duplicate ## N. section numbers', () => {
      const content = read('agents/reverse-spec/u-reverse-spec-analyzer.md')
      const matches = [...content.matchAll(/^## (\d+)\./gm)]
      const numbers = matches.map(m => m[1])
      const unique = new Set(numbers)
      expect(numbers.length, 'GUARD-24: duplicate section numbers found').toBe(unique.size)
    })
  })

  describe('SPEC-I-08: spec-validation SKILL no alert severity', () => {
    it('GUARD-25: u-spec-validation/SKILL.md must not use "alert" as severity value', () => {
      const content = read('skills/u-spec-validation/SKILL.md')
      // Check no occurrence of "alert" as a severity value (in column or enum context)
      assertNotContains(content, /\| `alert` \|/, 'GUARD-25a')
      assertNotContains(content, /or `alert`/, 'GUARD-25b')
      assertNotContains(content, /flag as alert/, 'GUARD-25c')
    })
  })

  describe('SPEC-I-09: conventions.md has FLOW-NN and COMP-NN prefixes', () => {
    it('GUARD-26: u-spec-globals/conventions.md must contain FLOW-NN', () => {
      const content = read('skills/u-spec-globals/conventions.md')
      assertContains(content, 'FLOW-NN', 'GUARD-26')
    })

    it('GUARD-26b: u-spec-globals/conventions.md must contain COMP-NN', () => {
      const content = read('skills/u-spec-globals/conventions.md')
      assertContains(content, 'COMP-NN', 'GUARD-26b')
    })

    it('GUARD-27: u-reverse-spec-writer.md must not reference manual-spec-agents.md', () => {
      const content = read('agents/reverse-spec/u-reverse-spec-writer.md')
      assertNotContains(content, 'manual-spec-agents.md', 'GUARD-27')
    })
  })

  describe('SPEC-I-10: triage uses artifact_version not timestamp', () => {
    it('GUARD-28: u-spec-validation-triage.md must use artifact_version for stale detection', () => {
      const content = read('agents/spec/protocols/u-spec-validation-triage.md')
      assertContains(content, 'artifact_version', 'GUARD-28a')
      // Should not use filesystem timestamp for stale detection
      const lines = content.split('\n')
      const staleIdx = lines.findIndex(l => l.includes('Stale') || l.includes('Rule 7'))
      if (staleIdx >= 0) {
        const staleContext = lines.slice(staleIdx, staleIdx + 5).join('\n')
        assertNotContains(staleContext, /spec timestamp > report timestamp/, 'GUARD-28b')
      }
    })
  })

  describe('DEV-I-05: epic integration no skill re-injection', () => {
    it('GUARD-29: u-be-epic-integration.md must not re-inject SKILL.md in activation prompt', () => {
      const content = read('agents/dev/protocols/u-be-epic-integration.md')
      // Should not have "Skills: .../SKILL.md" re-injection line
      assertNotContains(content, /Skills:.*SKILL\.md/, 'GUARD-29')
    })
  })

  describe('DEV-I-11: TC types use schema enum values', () => {
    const files = [
      ['u-be-standards/SKILL.md', 'skills/u-be-standards/SKILL.md'],
      ['u-fe-standards/SKILL.md', 'skills/u-fe-standards/SKILL.md'],
    ]

    it.each(files)('GUARD-30: %s must not contain non-canonical TC type names', (label, rel) => {
      const content = read(rel)
      assertNotContains(content, /\| \*\*Improvement\*\* \|/, `GUARD-30a: ${label}`)
      assertNotContains(content, /\| \*\*Enhancement\*\* \|/, `GUARD-30b: ${label}`)
      assertNotContains(content, /\| \*\*Visual adjustment\*\* \|/, `GUARD-30c: ${label}`)
    })
  })

  describe('DEV-I-12: bug mode post-merge specification', () => {
    it('GUARD-31: u-be-orchestrator-core.md must specify post-merge behavior in bug mode', () => {
      const content = read('agents/dev/u-be-orchestrator-core.md')
      assertContains(content, /[Bb]ug mode/i, 'GUARD-31a')
      assertContains(content, /Epic Integration/i, 'GUARD-31b')
    })

    it('GUARD-32: u-fe-orchestrator-core.md must specify post-merge behavior in bug mode', () => {
      const content = read('agents/dev/u-fe-orchestrator-core.md')
      assertContains(content, /[Bb]ug mode/i, 'GUARD-32a')
      assertContains(content, /Epic Integration/i, 'GUARD-32b')
    })
  })

  describe('SPEC-I-11: compliance-report renamed to spec-quality-report', () => {
    it('GUARD-33: u-spec-validator.md must not contain compliance-report.md', () => {
      const content = read('agents/spec/u-spec-validator.md')
      assertNotContains(content, 'compliance-report.md', 'GUARD-33a')
      assertContains(content, 'spec-quality-report.md', 'GUARD-33b')
    })
  })

  describe('DEV-I-13: BE QA short mode', () => {
    it('GUARD-34: u-be-qa-docs.md must contain short mode section', () => {
      const content = read('agents/dev/u-be-qa-docs.md')
      assertContains(content, /short mode/i, 'GUARD-34a')
      assertContains(content, 'u-context-mounting-short-mode.md', 'GUARD-34b')
    })
  })

  // ── SPEC-I-12: u-spec REQUIREMENT parameter ───────────────────────────────

  describe('SPEC-I-12: /u-spec REQUIREMENT resolution', () => {
    it('GUARD-35: u-spec.md must document REQUIREMENT resolution', () => {
      const content = read('commands/u-spec.md')
      assertContains(content, 'Resolving `REQUIREMENT`', 'GUARD-35a')
    })

    it('GUARD-35b: u-spec.md must support inline requirement via arguments', () => {
      const content = read('commands/u-spec.md')
      assertContains(content, 'source: inline', 'GUARD-35b')
    })

    it('GUARD-35c: u-spec.md must define interactive fallback when REQUIREMENT absent', () => {
      const content = read('commands/u-spec.md')
      assertContains(content, 'Requirement:', 'GUARD-35c')
    })

    it('GUARD-35d: u-spec.md usage line must include requirement parameter', () => {
      const content = read('commands/u-spec.md')
      assertContains(content, '"requirement"', 'GUARD-35d')
    })
  })

  // ── SPEC-I-13: u-spec-orchestrator new mode requirement handling ──────────

  describe('SPEC-I-13: spec orchestrator new mode requirement handling', () => {
    it('GUARD-36: u-spec-orchestrator.md must handle new mode with requirement provided inline', () => {
      const content = read('agents/spec/u-spec-orchestrator.md')
      assertContains(content, 'new mode (no log) with requirement provided', 'GUARD-36a')
    })

    it('GUARD-36b: u-spec-orchestrator.md must handle new mode without requirement (interactive prompt)', () => {
      const content = read('agents/spec/u-spec-orchestrator.md')
      assertContains(content, 'new mode (no log) without requirement', 'GUARD-36b')
    })

    it('GUARD-36c: orchestrator must not re-prompt when requirement is provided inline', () => {
      const content = read('agents/spec/u-spec-orchestrator.md')
      assertContains(content, 'do NOT prompt the human for description again', 'GUARD-36c')
    })
  })

  // ── SPEC-I-14: u-improve fast-track handoff context ──────────────────────

  describe('SPEC-I-14: /u-improve fast-track handoff to /u-spec', () => {
    it('GUARD-37: u-improve SKILL.md must emit handoff envelope to /u-spec when spec update confirmed', () => {
      // The "fast-track handoff block" was renamed to "handoff envelope" when the
      // write-before-confirm + return-contract design landed. The guarantee remains:
      // u-improve emits a structured handoff package to /u-spec without requiring
      // the human to copy-paste a shell command.
      const content = read('skills/u-improve/SKILL.md')
      assertContains(content, 'handoff envelope', 'GUARD-37a')
    })

    it('GUARD-37b: fast-track handoff must include improvement task as inline requirement', () => {
      const content = read('skills/u-improve/SKILL.md')
      assertContains(content, '{improvement_task}', 'GUARD-37b')
    })

    it('GUARD-37c: fast-track handoff must list affected files with change summaries', () => {
      const content = read('skills/u-improve/SKILL.md')
      assertContains(content, '{change_summary}', 'GUARD-37c')
    })
  })

  // ── SPEC-I-15: improve_scope no improve##.md ─────────────────────────────

  describe('SPEC-I-15: improve##.md eliminated from all pipelines', () => {
    // GUARD-38a..38g — same anti-pattern across 7 files. Diagnostic still names
    // the failing file path via the it.each parameter.
    const IMPROVE_HASH_FILES = [
      'skills/u-improve/SKILL.md',
      'agents/dev/protocols/u-improve-mode.md',
      'agents/dev/u-fe-orchestrator-core.md',
      'agents/dev/u-be-orchestrator-core.md',
      'agents/spec/protocols/u-spec-validation-triage.md',
      'commands/u-dev.md',
      'commands/u-spec-triage.md',
    ]
    it.each(IMPROVE_HASH_FILES)('GUARD-38: %s must not reference improve##.md', (rel) => {
      assertNotContains(read(rel), 'improve##.md', `GUARD-38: ${rel}`)
    })
  })

  // ── BE-I-01: CLAUDE.backend.md required production fields ────────────────
  describe('BE-I-01: CLAUDE.backend.md required production fields', () => {
    it('GUARD-39a: CLAUDE.backend.md must contain di_strategy field', () => {
      const content = read('templates/CLAUDE.backend.md')
      assertContains(content, 'di_strategy', 'GUARD-39a')
    })

    it('GUARD-39b: CLAUDE.backend.md must contain validation_library field', () => {
      const content = read('templates/CLAUDE.backend.md')
      assertContains(content, 'validation_library', 'GUARD-39b')
    })

    it('GUARD-39c: CLAUDE.backend.md must contain pagination section with offset and cursor options', () => {
      const content = read('templates/CLAUDE.backend.md')
      assertContains(content, '## Pagination', 'GUARD-39c: section header')
      assertContains(content, 'offset', 'GUARD-39c: offset option')
      assertContains(content, 'cursor', 'GUARD-39c: cursor option')
    })
  })

  // ── BE-I-02: Pagination canonical type location ───────────────────────────
  describe('BE-I-02: PaginatedResponse<T> must reference src/types/pagination.ts', () => {
    const PAGINATION_FILES = [
      'skills/u-be-development/SKILL.md',
      'agents/dev/u-be-developer.md',
      'skills/u-be-standards/SKILL.md',
      'agents/dev/u-be-qa-docs.md',
    ]
    it.each(PAGINATION_FILES)('GUARD-40: %s must reference src/types/pagination.ts', (rel) => {
      assertContains(read(rel), 'src/types/pagination.ts', `GUARD-40: ${rel}`)
    })
  })

  // ── BE-I-03: null-list rule consistency ──────────────────────────────────
  describe('BE-I-03: empty list must return PaginatedResponse<T>, never null', () => {
    // GUARD-41a has 2 anti-patterns; the others have 1. Encode as table of
    // [file, list-of-banned-shapes] so all files share the same iteration.
    const AD_HOC_PAGINATION_SHAPES = [
      ['skills/u-be-standards/SKILL.md',  ['{ data: [], pagination:', '{ data: [], meta: { page, limit']],
      ['agents/dev/u-be-developer.md',    ['{ data: [], pagination:']],
      ['agents/dev/u-be-qa-docs.md',      ['{ data: [], pagination:']],
    ]
    it.each(AD_HOC_PAGINATION_SHAPES)('GUARD-41: %s must not use ad-hoc pagination shapes', (rel, shapes) => {
      const content = read(rel)
      for (const shape of shapes) {
        assertNotContains(content, shape, `GUARD-41: ${rel} contains banned shape "${shape}"`)
      }
    })
  })

  // ── BE-I-04: DI pattern cross-consistency ────────────────────────────────
  describe('BE-I-04: DI manual-factory default must be consistent across BE files', () => {
    // GUARD-42a/b: manual-factory must appear; GUARD-42c/d: ## Dependency Injection
    // section must appear. Encode as [file, required-substring].
    const DI_REQUIREMENTS = [
      ['skills/u-be-development/SKILL.md', 'manual-factory'],
      ['skills/u-be-standards/SKILL.md',   'manual-factory'],
      ['agents/dev/u-be-developer.md',     '## Dependency Injection'],
      ['agents/dev/u-be-qa-docs.md',       '## Dependency Injection'],
    ]
    it.each(DI_REQUIREMENTS)('GUARD-42: %s must contain "%s"', (rel, needle) => {
      assertContains(read(rel), needle, `GUARD-42: ${rel}`)
    })
  })

  // ── BE-I-05: DTO pattern cross-consistency ───────────────────────────────
  describe('BE-I-05: DTO Zod default must be consistent across BE files', () => {
    it('GUARD-43a: u-be-development/SKILL.md must declare Zod as default validation_library', () => {
      const content = read('skills/u-be-development/SKILL.md')
      assertContains(content, 'zod', 'GUARD-43a')
      assertContains(content, 'validation_library', 'GUARD-43a')
    })

    it('GUARD-43b: u-be-developer.md must not pass raw req.body to service (positive rule)', () => {
      const content = read('agents/dev/u-be-developer.md')
      // The file must mention the req.body prohibition rule
      assertContains(content, 'req.body', 'GUARD-43b: prohibition rule must exist')
    })

    it('GUARD-43c: u-be-qa-docs.md must have DTO validation as a quality BUG', () => {
      const content = read('agents/dev/u-be-qa-docs.md')
      assertContains(content, 'req.body', 'GUARD-43c: req.body security risk must be in QA')
      assertContains(content, 'High', 'GUARD-43c: must classify req.body as High bug')
    })

    it('GUARD-43d: u-be-standards/SKILL.md must include DTO and Validation Pattern section', () => {
      const content = read('skills/u-be-standards/SKILL.md')
      assertContains(content, 'DTO and Validation Pattern', 'GUARD-43d')
    })
  })

  // ── BE-I-06: factories/ folder in default structure ──────────────────────
  describe('BE-I-06: factories/ must be present in BE default folder structure', () => {
    const FACTORY_FILES = [
      'skills/u-be-development/SKILL.md',
      'agents/dev/u-be-developer.md',
    ]
    it.each(FACTORY_FILES)('GUARD-44: %s folder structure must include factories/', (rel) => {
      assertContains(read(rel), 'factories/', `GUARD-44: ${rel}`)
    })
  })

})
