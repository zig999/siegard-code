import { describe, it, expect } from 'vitest'
import { basename } from 'path'
import {
  getTopLevelAgentFiles,
  parseFrontmatter,
} from './helpers/load.js'

// Worker agents (in subdirs: dev/, spec/, reverse-spec/) — full frontmatter
const WORKER_REQUIRED_FIELDS = ['name', 'description', 'user-invocable', 'model']

// Orchestrators at the agents/ root — no user-invocable (spawned by meta-orchestrator)
const ORCHESTRATOR_REQUIRED_FIELDS = ['name', 'description', 'model']

const ALLOWED_MODELS = [
  'claude-sonnet-4-6',
  'claude-opus-4-6',
  'claude-opus-4-7',
  'claude-haiku-4-5-20251001',
]

describe('Layer 1 — Frontmatter', () => {
  const agentFiles = getTopLevelAgentFiles()

  it('discovery sanity: agent files found', () => {
    expect(agentFiles.length, 'no agent files found').toBeGreaterThan(0)
  })

  // Orchestrators live at the top of agents/ (no subdir path component other than agents/).
  // Workers live one level deeper: agents/dev/, agents/spec/, agents/reverse-spec/.
  const orchestratorFiles = agentFiles.filter(f => {
    const rel = f.split('/agents/')[1] ?? ''
    return !rel.includes('/')
  })
  const workerFiles = agentFiles.filter(f => {
    const rel = f.split('/agents/')[1] ?? ''
    return rel.includes('/')
  })

  describe('orchestrators — frontmatter well-formed', () => {
    it.each(orchestratorFiles.map(f => [basename(f), f]))(
      '%s',
      (_, file) => {
        const fm = parseFrontmatter(file)
        for (const field of ORCHESTRATOR_REQUIRED_FIELDS) {
          expect(fm, `"${field}" missing in ${basename(file)}`).toHaveProperty(field)
        }
        expect(ALLOWED_MODELS, `model "${fm.model}" not allowed in ${basename(file)}`).toContain(fm.model)
        const expectedName = basename(file, '.md')
        expect(fm.name, `name "${fm.name}" != filename "${expectedName}"`).toBe(expectedName)
      }
    )
  })

  describe('worker agents — frontmatter well-formed', () => {
    it.each(workerFiles.map(f => [basename(f), f]))(
      '%s',
      (_, file) => {
        const fm = parseFrontmatter(file)
        for (const field of WORKER_REQUIRED_FIELDS) {
          expect(fm, `"${field}" missing in ${basename(file)}`).toHaveProperty(field)
        }
        expect(ALLOWED_MODELS, `model "${fm.model}" not allowed in ${basename(file)}`).toContain(fm.model)
        expect(typeof fm['user-invocable'], `user-invocable must be boolean in ${basename(file)}`).toBe('boolean')
        const expectedName = basename(file, '.md')
        expect(fm.name, `name "${fm.name}" != filename "${expectedName}"`).toBe(expectedName)
      }
    )
  })
})
