import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { basename } from 'path'
import { getAllAgentFiles } from './helpers/load.js'

// Banned terms per CLAUDE.md — vague qualifiers prohibited in agent instructions
const BANNED_TERMS = [
  { pattern: /\bappropriate\b/gi, term: 'appropriate' },
  { pattern: /\bplease\b/gi, term: 'please' },
  { pattern: /\bif possible\b/gi, term: 'if possible' },
  { pattern: /\bbetter\b/gi, term: 'better' },
]

function extractViolations(filePath) {
  const lines = readFileSync(filePath, 'utf8').split('\n')
  const violations = []
  let inFrontmatter = false

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()

    // Track YAML frontmatter block (between leading --- delimiters)
    if (i === 0 && trimmed === '---') { inFrontmatter = true; continue }
    if (inFrontmatter && trimmed === '---') { inFrontmatter = false; continue }
    if (inFrontmatter) continue

    // Skip comment lines
    if (trimmed.startsWith('#') || trimmed.startsWith('<!--')) continue

    for (const { pattern, term } of BANNED_TERMS) {
      pattern.lastIndex = 0
      if (pattern.test(line)) {
        violations.push({ line: i + 1, term, content: trimmed.slice(0, 100) })
      }
    }
  }

  return violations
}

describe('Layer 4 — Controlled Vocabulary', () => {
  const files = getAllAgentFiles()

  it('finds agent files to scan', () => {
    expect(files.length).toBeGreaterThan(0)
  })

  it.each(files.map(f => [basename(f), f]))(
    '%s — contains no banned terms',
    (_, file) => {
      const violations = extractViolations(file)
      const report = violations
        .map(v => `  L${v.line} ["${v.term}"]: ${v.content}`)
        .join('\n')
      expect(violations, `Banned terms in ${basename(file)}:\n${report}`).toHaveLength(0)
    }
  )
})
