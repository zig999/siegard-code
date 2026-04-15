import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'url'
import { dirname } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  test: {
    include: ['dist/**/*.test.js'],
    exclude: ['**/node_modules/**'],
    reporters: ['verbose'],
    environment: 'node',
    root: __dirname,
  },
})
