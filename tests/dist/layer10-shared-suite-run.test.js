import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { execSync } from 'child_process'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join, resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// ─── Layer 10 — shared suite run ──────────────────────────────────────────────
//
//  Validates the dist/ scripts that power the shared suite-run protocol:
//    parse_test_output.py  — normalizes vitest/jest JSON
//    attribute_failures.py — maps suite-run failures to TCs via delivery files
//
//  The orchestrator-review.md "Step 3.5" documents the contract these scripts
//  fulfil. Code SR-001 .. SR-099 covers attribution flows.
//
// ──────────────────────────────────────────────────────────────────────────────

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../..')
const SCRIPTS = resolve(REPO_ROOT, 'dist/.claude/skills/phase-review-rules/scripts')

const PARSE_TEST = join(SCRIPTS, 'parse_test_output.py')
const ATTRIBUTE = join(SCRIPTS, 'attribute_failures.py')

function runPy(script, args) {
  return execSync(`python3 "${script}" ${args.join(' ')}`, { encoding: 'utf-8' })
}

function deliveryDoc({ created = [], modified = [], tests = [] }) {
  const yamlList = (items, key) =>
    items.length === 0
      ? `${key}: []`
      : `${key}:\n${items.map(p => `  - path: "${p}"\n    change: ""`).join('\n')}`
  const testsBlock = tests.length === 0
    ? 'tests: []'
    : `tests:\n${tests.map(f => `  - file: "${f}"\n    covers: []`).join('\n')}`

  // files_created uses `responsibility:` instead of `change:` per template
  const createdBlock = created.length === 0
    ? 'files_created: []'
    : `files_created:\n${created.map(p => `  - path: "${p}"\n    responsibility: ""`).join('\n')}`

  return [
    '```yaml',
    '# delivery-gate',
    'task: TC-XX',
    'qa_ready: true',
    '```',
    '',
    '```yaml',
    '# delivery-body',
    createdBlock,
    yamlList(modified, 'files_modified'),
    testsBlock,
    '```',
    '',
  ].join('\n')
}

function buildManifest({ srId = 'sr-1', round = 1, tcIds, parsed, build }) {
  return {
    schema_version: '1',
    suite_run_id: srId,
    round,
    scope: { tc_ids_covered: tcIds, signature: 'test-signature' },
    build: build || { command: 'tsc --noEmit', exit_code: 0, result: 'passed', errors: [] },
    tests: {
      command: 'vitest run --reporter=json',
      framework: parsed.framework || 'vitest',
      exit_code: parsed.summary.failed > 0 ? 1 : 0,
      result: parsed.summary.failed > 0 ? 'failed' : 'passed',
      summary: parsed.summary,
      executed_test_files: parsed.executed_test_files || [],
      failures: parsed.failures || [],
    },
  }
}

function setupSession(rootDir, deliveries) {
  const proj = join(rootDir, 'proj')
  const sr = join(rootDir, 'session/qa/_suite-run/sr-1')
  mkdirSync(proj, { recursive: true })
  mkdirSync(sr, { recursive: true })
  for (const { taskId, delivery, deliveryRel } of deliveries) {
    const fullDir = dirname(join(proj, deliveryRel))
    mkdirSync(fullDir, { recursive: true })
    writeFileSync(join(proj, deliveryRel), delivery, 'utf-8')
  }
  return { proj, sr }
}

function parseTestOutput(rawJsonPath, projectDir, framework = 'vitest') {
  return JSON.parse(runPy(PARSE_TEST, [
    '--framework', framework,
    '--input', `"${rawJsonPath}"`,
    '--project-dir', `"${projectDir}"`,
  ]))
}

function runAttribution({ sr, proj, deliveries }) {
  const arg = JSON.stringify(deliveries.map(d => ({
    task_id: d.taskId,
    delivery_path: d.deliveryRel,
  })))
  return JSON.parse(runPy(ATTRIBUTE, [
    '--suite-run-dir', `"${sr}"`,
    '--project-dir', `"${proj}"`,
    '--deliveries', `'${arg}'`,
  ]))
}

describe('layer10 — shared suite run / attribution', () => {
  let tmp

  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), 'shared-suite-'))
  })

  afterEach(() => {
    if (tmp && existsSync(tmp)) rmSync(tmp, { recursive: true, force: true })
  })

  it('SR-001: attributes a failing test to the TC that wrote it (Stage A)', () => {
    const deliveries = [
      {
        taskId: 'dev_tc_001',
        deliveryRel: '.orch/sessions/wf/delivery/dev_tc_001-delivery.md',
        delivery: deliveryDoc({
          created: ['src/users/controller.ts'],
          modified: ['src/users/service.ts'],
          tests: ['__tests__/integration/user.spec.ts'],
        }),
      },
      {
        taskId: 'dev_tc_002',
        deliveryRel: '.orch/sessions/wf/delivery/dev_tc_002-delivery.md',
        delivery: deliveryDoc({
          created: ['src/orders/service.ts'],
          tests: ['__tests__/unit/order.spec.ts'],
        }),
      },
      {
        taskId: 'dev_tc_003',
        deliveryRel: '.orch/sessions/wf/delivery/dev_tc_003-delivery.md',
        delivery: deliveryDoc({
          modified: ['src/billing.ts'],
          tests: ['__tests__/unit/billing.spec.ts'],
        }),
      },
    ]

    const { proj, sr } = setupSession(tmp, deliveries)

    const runnerOutput = {
      numTotalTests: 4,
      numPassedTests: 3,
      numFailedTests: 1,
      testResults: [
        {
          name: `${proj}/__tests__/integration/user.spec.ts`,
          assertionResults: [{
            fullName: 'POST /users returns 201',
            title: 'returns 201',
            status: 'failed',
            failureMessages: ['AssertionError: expected 500 to be 201'],
            location: { line: 42, column: 5 },
          }],
        },
        {
          name: `${proj}/__tests__/unit/order.spec.ts`,
          assertionResults: [{
            fullName: 'createOrder builds payload', title: 'builds', status: 'passed',
            location: { line: 12 },
          }],
        },
        {
          name: `${proj}/__tests__/unit/billing.spec.ts`,
          assertionResults: [
            { fullName: 'computeTax zero', title: 'zero', status: 'passed', location: { line: 8 } },
            { fullName: 'computeTax neg', title: 'neg', status: 'passed', location: { line: 18 } },
          ],
        },
      ],
    }
    const runnerOutPath = join(sr, 'tests.stdout.json')
    writeFileSync(runnerOutPath, JSON.stringify(runnerOutput), 'utf-8')

    const parsed = parseTestOutput(runnerOutPath, proj, 'vitest')
    expect(parsed.summary.failed).toBe(1)
    expect(parsed.failures).toHaveLength(1)

    const manifest = buildManifest({
      tcIds: deliveries.map(d => d.taskId),
      parsed,
    })
    writeFileSync(join(sr, 'manifest.json'), JSON.stringify(manifest, null, 2), 'utf-8')

    const result = runAttribution({ sr, proj, deliveries })
    expect(result.status).toBe('ok')
    expect(result.by_tc_count).toBe(3)
    expect(result.unattributed_test_failures).toBe(0)

    const slice1 = JSON.parse(readFileSync(join(sr, 'by-tc/dev_tc_001.json'), 'utf-8'))
    const slice2 = JSON.parse(readFileSync(join(sr, 'by-tc/dev_tc_002.json'), 'utf-8'))
    const slice3 = JSON.parse(readFileSync(join(sr, 'by-tc/dev_tc_003.json'), 'utf-8'))

    expect(slice1.test_gate_result).toBe('failed')
    expect(slice1.test_gate_cause).toBe('code')
    expect(slice1.test_attribution.failures_attributed).toHaveLength(1)
    expect(slice1.test_attribution.failures_attributed[0].attribution_reason).toBe('test_in_tests_written')
    expect(slice1.test_attribution.failures_attributed[0].diagnosis.probable_cause).toBe('code')

    expect(slice2.test_gate_result).toBe('passed')
    expect(slice2.test_attribution.failures_attributed).toHaveLength(0)

    expect(slice3.test_gate_result).toBe('passed')
    expect(slice3.test_attribution.failures_attributed).toHaveLength(0)
  })

  it('SR-002: blocks every active TC when a failure is unattributed (Stage C)', () => {
    const deliveries = [
      {
        taskId: 'dev_tc_001',
        deliveryRel: '.orch/sessions/wf/delivery/dev_tc_001-delivery.md',
        delivery: deliveryDoc({
          modified: ['src/users/service.ts'],
          tests: ['__tests__/unit/user.spec.ts'],
        }),
      },
      {
        taskId: 'dev_tc_002',
        deliveryRel: '.orch/sessions/wf/delivery/dev_tc_002-delivery.md',
        delivery: deliveryDoc({
          modified: ['src/orders/service.ts'],
          tests: ['__tests__/unit/order.spec.ts'],
        }),
      },
    ]
    const { proj, sr } = setupSession(tmp, deliveries)

    // Failure in a test file no TC owns and that imports nothing from any TC's sources
    const runnerOutput = {
      numTotalTests: 1,
      numPassedTests: 0,
      numFailedTests: 1,
      testResults: [{
        name: `${proj}/__tests__/integration/auth.spec.ts`,
        assertionResults: [{
          fullName: 'login returns token',
          title: 'login',
          status: 'failed',
          failureMessages: ['Error: ECONNREFUSED 127.0.0.1:5432'],
          location: { line: 10 },
        }],
      }],
    }
    const runnerOutPath = join(sr, 'tests.stdout.json')
    writeFileSync(runnerOutPath, JSON.stringify(runnerOutput), 'utf-8')

    const parsed = parseTestOutput(runnerOutPath, proj, 'vitest')
    const manifest = buildManifest({ tcIds: deliveries.map(d => d.taskId), parsed })
    writeFileSync(join(sr, 'manifest.json'), JSON.stringify(manifest, null, 2), 'utf-8')

    const result = runAttribution({ sr, proj, deliveries })
    expect(result.unattributed_test_failures).toBe(1)

    const slice1 = JSON.parse(readFileSync(join(sr, 'by-tc/dev_tc_001.json'), 'utf-8'))
    const slice2 = JSON.parse(readFileSync(join(sr, 'by-tc/dev_tc_002.json'), 'utf-8'))
    expect(slice1.test_gate_result).toBe('blocked_by_unattributed_failure')
    expect(slice2.test_gate_result).toBe('blocked_by_unattributed_failure')

    const updatedManifest = JSON.parse(readFileSync(join(sr, 'manifest.json'), 'utf-8'))
    expect(updatedManifest.attribution.unattributed_failures).toHaveLength(1)
    expect(updatedManifest.attribution.unattributed_failures[0].test_file).toContain('auth.spec.ts')
  })

  it('SR-003: build error in a TC file marks every TC as build-blocked', () => {
    const deliveries = [
      {
        taskId: 'dev_tc_001',
        deliveryRel: '.orch/sessions/wf/delivery/dev_tc_001-delivery.md',
        delivery: deliveryDoc({
          modified: ['src/users/service.ts'],
          tests: ['__tests__/unit/user.spec.ts'],
        }),
      },
      {
        taskId: 'dev_tc_002',
        deliveryRel: '.orch/sessions/wf/delivery/dev_tc_002-delivery.md',
        delivery: deliveryDoc({
          modified: ['src/orders/service.ts'],
          tests: ['__tests__/unit/order.spec.ts'],
        }),
      },
    ]
    const { proj, sr } = setupSession(tmp, deliveries)

    const parsed = {
      framework: 'vitest',
      summary: { total: 0, passed: 0, failed: 0, skipped: 0 },
      executed_test_files: [],
      failures: [],
    }
    const manifest = buildManifest({
      tcIds: deliveries.map(d => d.taskId),
      parsed,
      build: {
        command: 'tsc --noEmit',
        exit_code: 1,
        duration_s: 1.2,
        result: 'failed',
        errors: [{
          file: 'src/users/service.ts',
          line: 12,
          column: 3,
          code: 'TS2322',
          message: "Type 'string' is not assignable to type 'number'.",
        }],
      },
    })
    writeFileSync(join(sr, 'manifest.json'), JSON.stringify(manifest, null, 2), 'utf-8')

    const result = runAttribution({ sr, proj, deliveries })
    expect(result.status).toBe('ok')

    const slice1 = JSON.parse(readFileSync(join(sr, 'by-tc/dev_tc_001.json'), 'utf-8'))
    const slice2 = JSON.parse(readFileSync(join(sr, 'by-tc/dev_tc_002.json'), 'utf-8'))

    expect(slice1.build_attribution.blocked_by_build).toBe(true)
    expect(slice1.build_attribution.build_errors_in_my_files).toHaveLength(1)
    expect(slice1.test_gate_result).toBe('failed')
    expect(slice1.test_gate_cause).toBe('build')

    // TC-002 has no error in its files but build_failed=true → also blocked
    expect(slice2.build_attribution.blocked_by_build).toBe(true)
    expect(slice2.build_attribution.build_errors_in_my_files).toHaveLength(0)
    expect(slice2.test_gate_result).toBe('failed')
    expect(slice2.test_gate_cause).toBe('build')
  })

  it('SR-004: tests_declared_but_not_executed surfaced as a setup failure', () => {
    const deliveries = [{
      taskId: 'dev_tc_001',
      deliveryRel: '.orch/sessions/wf/delivery/dev_tc_001-delivery.md',
      delivery: deliveryDoc({
        modified: ['src/users/service.ts'],
        tests: [
          '__tests__/unit/user.spec.ts',          // executed
          '__tests__/unit/user-extra.spec.ts',    // declared but NOT executed
        ],
      }),
    }]
    const { proj, sr } = setupSession(tmp, deliveries)

    const runnerOutput = {
      numTotalTests: 1,
      numPassedTests: 1,
      numFailedTests: 0,
      testResults: [{
        name: `${proj}/__tests__/unit/user.spec.ts`,
        assertionResults: [{
          fullName: 'creates user', title: 'creates', status: 'passed',
          location: { line: 12 },
        }],
      }],
    }
    const runnerOutPath = join(sr, 'tests.stdout.json')
    writeFileSync(runnerOutPath, JSON.stringify(runnerOutput), 'utf-8')

    const parsed = parseTestOutput(runnerOutPath, proj, 'vitest')
    const manifest = buildManifest({ tcIds: ['dev_tc_001'], parsed })
    writeFileSync(join(sr, 'manifest.json'), JSON.stringify(manifest, null, 2), 'utf-8')

    runAttribution({ sr, proj, deliveries })

    const slice = JSON.parse(readFileSync(join(sr, 'by-tc/dev_tc_001.json'), 'utf-8'))
    expect(slice.test_attribution.tests_declared_but_not_executed).toContain('__tests__/unit/user-extra.spec.ts')
    expect(slice.test_gate_result).toBe('failed')
    expect(slice.test_gate_cause).toBe('setup')
  })
})
