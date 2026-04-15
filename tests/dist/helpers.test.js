import { describe, it, expect } from 'vitest'
import { join } from 'path'
import {
  getDistDir,
  loadYaml,
  parseFrontmatter,
  fileExists,
  getAllAgentFiles,
  getTopLevelAgentFiles,
  getProtocolIndexFiles,
  getProtocolContentFiles,
  getAllSkillDirs,
  getAllSchemaFiles,
  loadFixture,
} from './helpers/load.js'
import { loadAndCompile, validate, compileAllSchemas } from './helpers/schema.js'

// ─── load.js ─────────────────────────────────────────────────────────────────

describe('helpers/load.js', () => {

  describe('getDistDir()', () => {
    it('returns an absolute path ending in /dist', () => {
      const dir = getDistDir()
      expect(dir).toMatch(/\/dist$/)
    })

    it('returns a path that actually exists on disk', () => {
      expect(fileExists(getDistDir())).toBe(true)
    })
  })

  describe('fileExists()', () => {
    it('returns true for a known existing file', () => {
      expect(fileExists(join(getDistDir(), 'agents'))).toBe(true)
    })

    it('returns false for a path that does not exist', () => {
      expect(fileExists(join(getDistDir(), '__nonexistent__'))).toBe(false)
    })
  })

  describe('loadYaml()', () => {
    it('parses a valid YAML file and returns an object', () => {
      const schemaDir = join(getDistDir(), 'skills', 'u-shared-templates')
      const schemas = getAllSchemaFiles()
      expect(schemas.length).toBeGreaterThan(0)
      const result = loadYaml(schemas[0])
      expect(typeof result).toBe('object')
      expect(result).not.toBeNull()
    })
  })

  describe('parseFrontmatter()', () => {
    it('extracts frontmatter fields from a markdown agent file', () => {
      const agentFiles = getTopLevelAgentFiles()
      expect(agentFiles.length).toBeGreaterThan(0)
      const fm = parseFrontmatter(agentFiles[0])
      expect(fm).toHaveProperty('name')
      expect(fm).toHaveProperty('description')
    })

    it('returns an empty object for a file with no frontmatter', () => {
      const protocolFiles = getProtocolContentFiles()
      expect(protocolFiles.length).toBeGreaterThan(0)
      // Protocol content files have no frontmatter — parseFrontmatter returns {}
      const fm = parseFrontmatter(protocolFiles[0])
      expect(typeof fm).toBe('object')
    })
  })

  describe('getAllAgentFiles()', () => {
    it('returns at least 10 agent files', () => {
      expect(getAllAgentFiles().length).toBeGreaterThan(10)
    })

    it('returns only .md files', () => {
      for (const f of getAllAgentFiles()) {
        expect(f).toMatch(/\.md$/)
      }
    })
  })

  describe('getTopLevelAgentFiles()', () => {
    it('returns files that are not in protocols/ subdirectory', () => {
      for (const f of getTopLevelAgentFiles()) {
        expect(f).not.toContain('/protocols/')
      }
    })

    it('is a subset of getAllAgentFiles()', () => {
      const all = new Set(getAllAgentFiles())
      for (const f of getTopLevelAgentFiles()) {
        expect(all.has(f)).toBe(true)
      }
    })
  })

  describe('getProtocolIndexFiles()', () => {
    it('returns only files ending in -protocols.md', () => {
      for (const f of getProtocolIndexFiles()) {
        expect(f).toMatch(/-protocols\.md$/)
      }
    })

    it('does not overlap with protocol content files', () => {
      const contentSet = new Set(getProtocolContentFiles())
      for (const f of getProtocolIndexFiles()) {
        expect(contentSet.has(f)).toBe(false)
      }
    })
  })

  describe('getProtocolContentFiles()', () => {
    it('returns files inside protocols/ subdirectory', () => {
      for (const f of getProtocolContentFiles()) {
        expect(f).toContain('/protocols/')
      }
    })
  })

  describe('getAllSkillDirs()', () => {
    it('returns at least one skill directory', () => {
      expect(getAllSkillDirs().length).toBeGreaterThan(0)
    })

    it('each entry has name and path properties', () => {
      for (const entry of getAllSkillDirs()) {
        expect(entry).toHaveProperty('name')
        expect(entry).toHaveProperty('path')
      }
    })
  })

  describe('getAllSchemaFiles()', () => {
    it('returns at least one schema file', () => {
      expect(getAllSchemaFiles().length).toBeGreaterThan(0)
    })

    it('returns only .schema.yaml files', () => {
      for (const f of getAllSchemaFiles()) {
        expect(f).toMatch(/\.schema\.yaml$/)
      }
    })
  })

  describe('loadFixture()', () => {
    it('loads a valid fixture as a plain object', () => {
      const data = loadFixture('valid/task-contract.yaml')
      expect(typeof data).toBe('object')
      expect(data).not.toBeNull()
    })

    it('loads an invalid fixture without throwing', () => {
      const data = loadFixture('invalid/task-contract-scope-both.yaml')
      expect(data).toBeDefined()
    })
  })
})

// ─── schema.js ───────────────────────────────────────────────────────────────

describe('helpers/schema.js', () => {
  const schemaFile = join(getDistDir(), 'skills', 'u-shared-templates', 'task_contract.schema.yaml')

  describe('loadAndCompile()', () => {
    it('compiles a schema file and returns a function', () => {
      const validator = loadAndCompile(schemaFile)
      expect(typeof validator).toBe('function')
    })

    it('returns the same compiled instance on repeated calls (cache)', () => {
      const v1 = loadAndCompile(schemaFile)
      const v2 = loadAndCompile(schemaFile)
      expect(v1).toBe(v2)
    })
  })

  describe('validate()', () => {
    it('returns { valid: true } for a conforming fixture', () => {
      const data = loadFixture('valid/task-contract.yaml')
      const result = validate(schemaFile, data)
      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })

    it('returns { valid: false } with errors for a non-conforming fixture', () => {
      const data = loadFixture('invalid/task-contract-scope-both.yaml')
      const result = validate(schemaFile, data)
      expect(result.valid).toBe(false)
      expect(result.errors.length).toBeGreaterThan(0)
    })

    it('errors array is always an array (never null)', () => {
      const data = loadFixture('valid/task-contract.yaml')
      const result = validate(schemaFile, data)
      expect(Array.isArray(result.errors)).toBe(true)
    })
  })

  describe('compileAllSchemas()', () => {
    it('returns at least one result', () => {
      const results = compileAllSchemas()
      expect(results.length).toBeGreaterThan(0)
    })

    it('every result has file, compiled, and error properties', () => {
      for (const r of compileAllSchemas()) {
        expect(r).toHaveProperty('file')
        expect(r).toHaveProperty('compiled')
        expect(r).toHaveProperty('error')
      }
    })

    it('all known schemas compile successfully', () => {
      const failures = compileAllSchemas().filter(r => !r.compiled)
      expect(failures, failures.map(f => f.file).join(', ')).toHaveLength(0)
    })
  })
})
