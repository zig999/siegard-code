import { readFileSync, readdirSync, statSync, existsSync } from 'fs'
import { resolve, join, extname, basename, dirname, sep } from 'path'
import { fileURLToPath } from 'url'
import { createRequire } from 'module'
import yaml from 'js-yaml'

const require = createRequire(import.meta.url)
const matter = require('gray-matter')

const __dirname = dirname(fileURLToPath(import.meta.url))
const DIST_DIR = resolve(__dirname, '../../../dist')

export function getDistDir() {
  return DIST_DIR
}

export function loadYaml(filePath) {
  const content = readFileSync(filePath, 'utf8')
  return yaml.load(content)
}

export function parseFrontmatter(filePath) {
  const content = readFileSync(filePath, 'utf8')
  const { data } = matter(content)
  return data
}

export function fileExists(filePath) {
  return existsSync(filePath)
}

function walkDir(dir, ext, results = []) {
  if (!existsSync(dir)) return results
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      walkDir(full, ext, results)
    } else if (!ext || extname(entry) === ext) {
      results.push(full)
    }
  }
  return results
}

export function getAllAgentFiles() {
  return walkDir(join(DIST_DIR, 'agents'), '.md')
}

// Standalone agent files — have full frontmatter: name, description, user-invocable, model
export function getTopLevelAgentFiles() {
  return getAllAgentFiles().filter(f =>
    !f.includes(`${sep}protocols${sep}`) && !basename(f).endsWith('-protocols.md')
  )
}

// Protocol index files (top-level *-protocols.md) — have frontmatter WITHOUT model field
export function getProtocolIndexFiles() {
  return getAllAgentFiles().filter(f =>
    !f.includes(`${sep}protocols${sep}`) && basename(f).endsWith('-protocols.md')
  )
}

// Protocol content files (in protocols/ subdirs) — pure Markdown, no frontmatter
export function getProtocolContentFiles() {
  return getAllAgentFiles().filter(f => f.includes(`${sep}protocols${sep}`))
}

export function getAllSkillDirs() {
  const skillsDir = join(DIST_DIR, 'skills')
  if (!existsSync(skillsDir)) return []
  return readdirSync(skillsDir)
    .map(name => ({ name, path: join(skillsDir, name) }))
    .filter(({ path }) => statSync(path).isDirectory())
}

export function getAllSchemaFiles() {
  const dir = join(DIST_DIR, 'skills', 'u-shared-templates')
  if (!existsSync(dir)) return []
  return readdirSync(dir)
    .filter(f => f.endsWith('.schema.yaml'))
    .map(f => join(dir, f))
}

export function loadFixture(relativePath) {
  const fixturePath = resolve(__dirname, '../fixtures', relativePath)
  return loadYaml(fixturePath)
}
