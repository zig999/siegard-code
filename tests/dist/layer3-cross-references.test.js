import { describe, it, expect } from 'vitest'
import { join, basename } from 'path'
import { existsSync } from 'fs'
import { getDistDir, getAllSchemaFiles, getAllSkillDirs } from './helpers/load.js'

const DIST_DIR = getDistDir()

// Skill dirs that are collections of files, not single-skill dirs — no SKILL.md required
const SKIP_SKILL_DIRS = new Set([
  'u-spec-globals',
  'u-spec-templates',
  'u-fe-templates',
  'u-be-templates',
  'u-shared-templates',
])

// Schemas that must always be present in u-shared-templates/
const REQUIRED_SCHEMAS = [
  'task_contract.schema.yaml',
  'handoff-manifest.schema.yaml',
  'validation-result.schema.yaml',
  'blocked-report.schema.yaml',
  'cr.schema.yaml',
]

describe('Layer 3 — Cross References', () => {
  describe('dist/ directory structure', () => {
    const REQUIRED_DIRS = [
      ['agents/', join(DIST_DIR, 'agents')],
      ['agents/spec/', join(DIST_DIR, 'agents', 'spec')],
      ['agents/dev/', join(DIST_DIR, 'agents', 'dev')],
      ['agents/reverse-spec/', join(DIST_DIR, 'agents', 'reverse-spec')],
      ['skills/', join(DIST_DIR, 'skills')],
      ['commands/', join(DIST_DIR, 'commands')],
    ]

    it.each(REQUIRED_DIRS)('%s exists', (_, dirPath) => {
      expect(existsSync(dirPath), `Directory not found: ${dirPath}`).toBe(true)
    })
  })

  describe('required shared schemas exist', () => {
    it.each(REQUIRED_SCHEMAS)('%s present in u-shared-templates/', (schemaName) => {
      const schemaPath = join(DIST_DIR, 'skills', 'u-shared-templates', schemaName)
      expect(existsSync(schemaPath), `Missing required schema: ${schemaName}`).toBe(true)
    })
  })

  describe('each schema file has a matching template', () => {
    // Internal-only schemas used for event/log validation — no human-facing template required
    const SKIP_TEMPLATE_SCHEMAS = new Set([
      'backlog.schema.yaml',
      'delivery.schema.yaml',
      'qa-verdict.schema.yaml',
    ])

    const schemaFiles = getAllSchemaFiles().filter(f => !SKIP_TEMPLATE_SCHEMAS.has(basename(f)))

    it('finds schema files', () => {
      expect(schemaFiles.length).toBeGreaterThan(0)
    })

    it.each(schemaFiles.map(f => [basename(f), f]))(
      '%s — has a corresponding template file',
      (name, schemaFile) => {
        // Matches: task_contract.schema.yaml → task_contract.yaml
        // Also matches: cr.schema.yaml → cr-template.yaml
        const plain = schemaFile.replace('.schema.yaml', '.yaml')
        const templated = schemaFile.replace('.schema.yaml', '-template.yaml')
        const exists = existsSync(plain) || existsSync(templated)
        expect(exists, `No template found for ${name}`).toBe(true)
      }
    )
  })

  describe('skill directories contain SKILL.md', () => {
    const skillDirs = getAllSkillDirs().filter(d => !SKIP_SKILL_DIRS.has(d.name))

    it('finds at least one skill directory', () => {
      expect(skillDirs.length).toBeGreaterThan(0)
    })

    it.each(skillDirs.map(d => [d.name, d.path]))(
      '%s — has SKILL.md',
      (name, dirPath) => {
        const skillFile = join(dirPath, 'SKILL.md')
        expect(existsSync(skillFile), `SKILL.md not found in dist/skills/${name}/`).toBe(true)
      }
    )
  })
})
