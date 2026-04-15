import { createRequire } from 'module'
import { basename } from 'path'
import { loadYaml, getAllSchemaFiles } from './load.js'

const require = createRequire(import.meta.url)
const Ajv = require('ajv')

const ajv = new Ajv({ allErrors: true, strict: false })
const schemaCache = new Map()

export function loadAndCompile(schemaFile) {
  const id = basename(schemaFile)
  if (schemaCache.has(id)) return schemaCache.get(id)
  const schema = loadYaml(schemaFile)
  const validator = ajv.compile(schema)
  schemaCache.set(id, validator)
  return validator
}

export function validate(schemaFile, data) {
  const validator = loadAndCompile(schemaFile)
  const valid = validator(data)
  return { valid, errors: validator.errors || [] }
}

export function compileAllSchemas() {
  return getAllSchemaFiles().map(f => {
    try {
      loadAndCompile(f)
      return { file: f, compiled: true, error: null }
    } catch (err) {
      return { file: f, compiled: false, error: err.message }
    }
  })
}
