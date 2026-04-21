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

  it('discovery sanity: standalone agents, protocol indexes, and protocol content files all present', () => {
    expect(agentFiles.length, 'no standalone agent files found').toBeGreaterThan(0)
    expect(protocolIndexFiles.length, 'no *-protocols.md index files found').toBeGreaterThan(0)
    expect(protocolContentFiles.length, 'no protocol content files found').toBeGreaterThan(0)
  })

  // ── Standalone agents — every check on a single frontmatter parse ────────
  //
  // Previously these were 4 separate it.each blocks, each parsing the same
  // frontmatter. Consolidated into one it.each per file: 4 assertions, 1 read.
  // Vitest still names the failing file ("u-fe-developer.md — frontmatter
  // well-formed") and the first assertion failure shows which rule broke.

  describe('standalone agents — frontmatter well-formed', () => {
    it.each(agentFiles.map(f => [basename(f), f]))(
      '%s',
      (_, file) => {
        const fm = parseFrontmatter(file)

        // 1. All required fields present
        for (const field of AGENT_REQUIRED_FIELDS) {
          expect(fm, `"${field}" missing in ${basename(file)}`).toHaveProperty(field)
        }

        // 2. Model is in the allow-list
        expect(
          ALLOWED_MODELS,
          `model "${fm.model}" not allowed in ${basename(file)}`
        ).toContain(fm.model)

        // 3. user-invocable is a boolean
        expect(
          typeof fm['user-invocable'],
          `user-invocable must be boolean in ${basename(file)}`
        ).toBe('boolean')

        // 4. name field matches the filename
        const expectedName = basename(file, '.md')
        expect(
          fm.name,
          `name "${fm.name}" != filename "${expectedName}"`
        ).toBe(expectedName)
      }
    )
  })

  // ── Protocol index files (*-protocols.md) — frontmatter without model ────

  describe('protocol index files — frontmatter well-formed', () => {
    it.each(protocolIndexFiles.map(f => [basename(f), f]))(
      '%s',
      (_, file) => {
        const fm = parseFrontmatter(file)

        for (const field of PROTOCOL_INDEX_REQUIRED_FIELDS) {
          expect(fm, `"${field}" missing in ${basename(file)}`).toHaveProperty(field)
        }
        expect(
          typeof fm['user-invocable'],
          `user-invocable must be boolean in ${basename(file)}`
        ).toBe('boolean')
      }
    )
  })

  // ── Protocol content files — non-empty Markdown ──────────────────────────

  describe('protocol content files — non-empty', () => {
    it.each(protocolContentFiles.map(f => [basename(f), f]))(
      '%s',
      (_, file) => {
        const content = readFileSync(file, 'utf8').trim()
        expect(content.length, `${basename(file)} is empty`).toBeGreaterThan(0)
      }
    )
  })
})
