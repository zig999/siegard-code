import { describe, it, expect } from 'vitest'
import { join } from 'path'
import {
  getDistDir,
  parseFrontmatter,
  getAllAgentFiles,
  getTopLevelAgentFiles,
  getAllSchemaFiles,
  loadFixture,
} from './helpers/load.js'
import { validate, compileAllSchemas } from './helpers/schema.js'

// ─── Smoke tests for shared helpers ─────────────────────────────────────────
//
// These helpers are exercised end-to-end by every other layer (1–9). If they
// break, the whole suite fails loudly with concrete fixture/file errors.
// We only keep ONE smoke per helper here — enough to catch a genuine bug in
// the helper itself before the cascade of layer failures masks the root cause.

describe('helpers — smoke tests', () => {
  it('getDistDir() returns the dist/.claude directory and it exists', () => {
    const dir = getDistDir()
    expect(dir).toMatch(/\/dist\/\.claude$/)
    expect(getAllAgentFiles().length).toBeGreaterThan(10)
  })

  it('parseFrontmatter() extracts agent frontmatter as an object', () => {
    // Top-level agent files always have frontmatter; protocol content files do not.
    const fm = parseFrontmatter(getTopLevelAgentFiles()[0])
    expect(fm).toHaveProperty('name')
    expect(fm).toHaveProperty('description')
  })

  it('loadFixture() returns a parsed YAML object', () => {
    const data = loadFixture('valid/task-contract.yaml')
    expect(typeof data).toBe('object')
    expect(data).not.toBeNull()
  })

  it('validate() returns { valid, errors[] } for a known good fixture', () => {
    const schemaFile = join(getDistDir(), 'skills', 'u-shared-templates', 'task_contract.schema.yaml')
    const result = validate(schemaFile, loadFixture('valid/task-contract.yaml'))
    expect(result.valid).toBe(true)
    expect(Array.isArray(result.errors)).toBe(true)
  })

  it('compileAllSchemas() reports every schema in u-shared-templates compiles', () => {
    const failures = compileAllSchemas().filter(r => !r.compiled)
    expect(getAllSchemaFiles().length).toBeGreaterThan(0)
    expect(failures, failures.map(f => f.file).join(', ')).toHaveLength(0)
  })
})
