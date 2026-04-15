import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { basename } from 'path'
import {
  getTopLevelAgentFiles,
  getProtocolIndexFiles,
  getProtocolContentFiles,
  parseFrontmatter,
} from './helpers/load.js'

// Standalone agents — full frontmatter including model
const AGENT_REQUIRED_FIELDS = ['name', 'description', 'user-invocable', 'model']

// Protocol index files (*-protocols.md) — frontmatter without model
const PROTOCOL_INDEX_REQUIRED_FIELDS = ['name', 'description', 'user-invocable']

const ALLOWED_MODELS = [
  'claude-sonnet-4-6',
  'claude-opus-4-6',
  'claude-haiku-4-5-20251001',
]

describe('Layer 1 — Frontmatter', () => {
  const agentFiles = getTopLevelAgentFiles()
  const protocolIndexFiles = getProtocolIndexFiles()
  const protocolContentFiles = getProtocolContentFiles()

  it('finds standalone agent files', () => {
    expect(agentFiles.length).toBeGreaterThan(0)
  })

  it('finds protocol index files', () => {
    expect(protocolIndexFiles.length).toBeGreaterThan(0)
  })

  it('finds protocol content files', () => {
    expect(protocolContentFiles.length).toBeGreaterThan(0)
  })

  describe('standalone agents — full frontmatter (including model)', () => {
    it.each(agentFiles.map(f => [basename(f), f]))(
      '%s — has all required fields',
      (_, file) => {
        const fm = parseFrontmatter(file)
        for (const field of AGENT_REQUIRED_FIELDS) {
          expect(fm, `"${field}" missing in ${basename(file)}`).toHaveProperty(field)
        }
      }
    )

    it.each(agentFiles.map(f => [basename(f), f]))(
      '%s — model is in allowed list',
      (_, file) => {
        const fm = parseFrontmatter(file)
        expect(ALLOWED_MODELS, `"${fm.model}" not allowed in ${basename(file)}`).toContain(fm.model)
      }
    )

    it.each(agentFiles.map(f => [basename(f), f]))(
      '%s — user-invocable is boolean',
      (_, file) => {
        const fm = parseFrontmatter(file)
        expect(typeof fm['user-invocable'], `user-invocable must be boolean in ${basename(file)}`).toBe('boolean')
      }
    )

    it.each(agentFiles.map(f => [basename(f), f]))(
      '%s — name matches filename',
      (_, file) => {
        const fm = parseFrontmatter(file)
        const expected = basename(file, '.md')
        expect(fm.name, `name "${fm.name}" != filename "${expected}"`).toBe(expected)
      }
    )
  })

  describe('protocol index files (*-protocols.md) — frontmatter without model', () => {
    it.each(protocolIndexFiles.map(f => [basename(f), f]))(
      '%s — has required fields',
      (_, file) => {
        const fm = parseFrontmatter(file)
        for (const field of PROTOCOL_INDEX_REQUIRED_FIELDS) {
          expect(fm, `"${field}" missing in ${basename(file)}`).toHaveProperty(field)
        }
      }
    )

    it.each(protocolIndexFiles.map(f => [basename(f), f]))(
      '%s — user-invocable is boolean',
      (_, file) => {
        const fm = parseFrontmatter(file)
        expect(typeof fm['user-invocable'], `user-invocable must be boolean in ${basename(file)}`).toBe('boolean')
      }
    )
  })

  describe('protocol content files (protocols/) — non-empty Markdown', () => {
    it.each(protocolContentFiles.map(f => [basename(f), f]))(
      '%s — is non-empty',
      (_, file) => {
        const content = readFileSync(file, 'utf8').trim()
        expect(content.length, `${basename(file)} is empty`).toBeGreaterThan(0)
      }
    )
  })
})
