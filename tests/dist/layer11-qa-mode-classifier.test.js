import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { execSync } from 'child_process'
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join, resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// ─── Layer 11 — qa_mode classifier + auto-approval gate ───────────────────────
//
//  Validates two scripts in dist/.claude/skills/phase-review-rules/scripts/:
//    classify_qa_mode.py        — qa_mode + concurrency_hint decision
//    check_micro_unanimous_clean.py — Step 5.0 strict auto-approval gate
//
//  Code ranges:
//    QM-001..QM-099 — classify_qa_mode.py
//    AA-001..AA-099 — check_micro_unanimous_clean.py
//
// ──────────────────────────────────────────────────────────────────────────────

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../..')
const SCRIPTS = resolve(REPO_ROOT, 'dist/.claude/skills/phase-review-rules/scripts')

const CLASSIFY = join(SCRIPTS, 'classify_qa_mode.py')
const AUTO_APPROVE = join(SCRIPTS, 'check_micro_unanimous_clean.py')

function runPy(script, args) {
  return execSync(`python3 "${script}" ${args.join(' ')}`, { encoding: 'utf-8' })
}

function classify({ workflowType, devImpact, changedFiles, tcType, deliveryRel, projectDir }) {
  return JSON.parse(runPy(CLASSIFY, [
    '--workflow-type', workflowType,
    '--dev-impact', devImpact,
    '--changed-files-count', String(changedFiles),
    '--tc-type', tcType,
    '--delivery-path', `"${deliveryRel}"`,
    '--project-dir', `"${projectDir}"`,
  ]))
}

function deliveryDoc({ created = [], modified = [], tests = [], hasNfr = false }) {
  const createdBlock = created.length === 0
    ? 'files_created: []'
    : `files_created:\n${created.map(p => `  - path: "${p}"\n    responsibility: ""`).join('\n')}`
  const modifiedBlock = modified.length === 0
    ? 'files_modified: []'
    : `files_modified:\n${modified.map(p => `  - path: "${p}"\n    change: ""`).join('\n')}`
  const testsBlock = tests.length === 0
    ? 'tests: []'
    : `tests:\n${tests.map(f => `  - file: "${f}"\n    covers: []`).join('\n')}`
  const nfrBlock = hasNfr
    ? `\nnfr_results:\n  - type: latency_p99_ms\n    threshold: 200\n    measured: 180\n    passed: true`
    : ''

  return [
    '```yaml',
    '# delivery-gate',
    'task: TC-XX',
    'qa_ready: true' + nfrBlock,
    '```',
    '',
    '```yaml',
    '# delivery-body',
    createdBlock,
    modifiedBlock,
    testsBlock,
    '```',
    '',
  ].join('\n')
}

function setupProject(rootDir, deliveryName, doc) {
  const proj = join(rootDir, 'proj')
  mkdirSync(proj, { recursive: true })
  writeFileSync(join(proj, deliveryName), doc, 'utf-8')
  return proj
}

// ─── classify_qa_mode.py tests ────────────────────────────────────────────────

describe('layer11 — classify_qa_mode.py', () => {
  let tmp

  beforeEach(() => { tmp = mkdtempSync(join(tmpdir(), 'qa-mode-')) })
  afterEach(() => { if (tmp && existsSync(tmp)) rmSync(tmp, { recursive: true, force: true }) })

  it('QM-001: micro path — improve + narrow + 1 file + Bugfix', () => {
    const proj = setupProject(tmp, 'd.md', deliveryDoc({
      modified: ['src/utils/format-date.ts'],
      tests: ['__tests__/unit/format-date.spec.ts'],
    }))
    const r = classify({
      workflowType: 'improve', devImpact: 'narrow', changedFiles: 1,
      tcType: 'Bugfix', deliveryRel: 'd.md', projectDir: proj,
    })
    expect(r.qa_mode).toBe('micro')
    expect(r.concurrency_hint).toBe(5)
  })

  it('QM-002: full overrides micro when delivery touches a controller', () => {
    const proj = setupProject(tmp, 'd.md', deliveryDoc({
      modified: ['src/users/controller.ts'],
      tests: ['__tests__/integration/users.spec.ts'],
    }))
    const r = classify({
      workflowType: 'improve', devImpact: 'narrow', changedFiles: 1,
      tcType: 'Bugfix', deliveryRel: 'd.md', projectDir: proj,
    })
    expect(r.qa_mode).toBe('full')
    expect(r.concurrency_hint).toBe(2)
    expect(r.signals.touches_public_api).toBe(true)
    expect(r.signals.matched_public_api_paths).toContain('src/users/controller.ts')
  })

  it('QM-003: full overrides micro when delivery touches auth/security', () => {
    const proj = setupProject(tmp, 'd.md', deliveryDoc({
      modified: ['src/middleware/auth-guard.ts'],
      tests: ['__tests__/unit/auth-guard.spec.ts'],
    }))
    const r = classify({
      workflowType: 'improve', devImpact: 'narrow', changedFiles: 1,
      tcType: 'Bugfix', deliveryRel: 'd.md', projectDir: proj,
    })
    expect(r.qa_mode).toBe('full')
    expect(r.signals.touches_security).toBe(true)
  })

  it('QM-004: full when TC has NFR', () => {
    const proj = setupProject(tmp, 'd.md', deliveryDoc({
      modified: ['src/utils/format-date.ts'],
      tests: ['__tests__/unit/format-date.spec.ts'],
      hasNfr: true,
    }))
    const r = classify({
      workflowType: 'improve', devImpact: 'narrow', changedFiles: 1,
      tcType: 'Bugfix', deliveryRel: 'd.md', projectDir: proj,
    })
    expect(r.qa_mode).toBe('full')
    expect(r.signals.has_nfr).toBe(true)
  })

  it('QM-005: standard fallback when changed_files > 2', () => {
    const proj = setupProject(tmp, 'd.md', deliveryDoc({
      modified: ['src/a.ts', 'src/b.ts', 'src/c.ts'],
      tests: ['__tests__/unit/a.spec.ts'],
    }))
    const r = classify({
      workflowType: 'improve', devImpact: 'narrow', changedFiles: 3,
      tcType: 'Bugfix', deliveryRel: 'd.md', projectDir: proj,
    })
    expect(r.qa_mode).toBe('standard')
    expect(r.concurrency_hint).toBe(3)
    expect(r.rationale).toContain('files=3')
  })

  it('QM-006: standard when tc_type is NewFeature even on a 1-file improve', () => {
    const proj = setupProject(tmp, 'd.md', deliveryDoc({
      modified: ['src/services/billing.ts'],
      tests: ['__tests__/unit/billing.spec.ts'],
    }))
    const r = classify({
      workflowType: 'improve', devImpact: 'narrow', changedFiles: 1,
      tcType: 'NewFeature', deliveryRel: 'd.md', projectDir: proj,
    })
    expect(r.qa_mode).toBe('standard')
  })

  it('QM-007: standard when workflow_type is standard (not improve)', () => {
    const proj = setupProject(tmp, 'd.md', deliveryDoc({
      modified: ['src/billing.ts'],
      tests: ['__tests__/unit/billing.spec.ts'],
    }))
    const r = classify({
      workflowType: 'standard', devImpact: 'narrow', changedFiles: 1,
      tcType: 'Bugfix', deliveryRel: 'd.md', projectDir: proj,
    })
    expect(r.qa_mode).toBe('standard')
  })
})

// ─── check_micro_unanimous_clean.py tests ─────────────────────────────────────

describe('layer11 — check_micro_unanimous_clean.py', () => {
  let tmp, qaDir

  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), 'auto-approve-'))
    qaDir = join(tmp, 'qa')
    mkdirSync(qaDir, { recursive: true })
  })
  afterEach(() => { if (tmp && existsSync(tmp)) rmSync(tmp, { recursive: true, force: true }) })

  function writeVerdict(name, verdict, severities = []) {
    const findings = severities.map(s => `- severity: ${s}\n  message: dummy`).join('\n')
    writeFileSync(join(qaDir, name),
      `verdict: ${verdict}\n\n## Findings\n${findings}\n`, 'utf-8')
  }

  function run(tasks) {
    return JSON.parse(runPy(AUTO_APPROVE, [
      '--project-dir', `"${tmp}"`,
      '--tasks', `'${JSON.stringify(tasks)}'`,
    ]))
  }

  it('AA-001: qualifies — 2 micro tasks, both approved, only low findings', () => {
    writeVerdict('a.md', 'approved', ['low'])
    writeVerdict('b.md', 'approved', [])
    const r = run([
      { task_id: 'a', qa_mode: 'micro', verdict_path: 'qa/a.md' },
      { task_id: 'b', qa_mode: 'micro', verdict_path: 'qa/b.md' },
    ])
    expect(r.qualifies).toBe(true)
    expect(r.evidence.max_finding_severity).toBe('low')
  })

  it('AA-002: disqualifies — non-micro task in batch', () => {
    writeVerdict('a.md', 'approved')
    writeVerdict('b.md', 'approved')
    const r = run([
      { task_id: 'a', qa_mode: 'micro', verdict_path: 'qa/a.md' },
      { task_id: 'b', qa_mode: 'standard', verdict_path: 'qa/b.md' },
    ])
    expect(r.qualifies).toBe(false)
    expect(r.evidence.non_micro_tasks).toEqual(['b'])
  })

  it('AA-003: disqualifies — medium severity finding', () => {
    writeVerdict('a.md', 'approved', ['low'])
    writeVerdict('b.md', 'approved', ['medium'])
    const r = run([
      { task_id: 'a', qa_mode: 'micro', verdict_path: 'qa/a.md' },
      { task_id: 'b', qa_mode: 'micro', verdict_path: 'qa/b.md' },
    ])
    expect(r.qualifies).toBe(false)
    expect(r.evidence.max_finding_severity).toBe('medium')
    expect(r.evidence.tasks_with_blocking_findings).toHaveLength(1)
  })

  it('AA-004: disqualifies — rejected verdict', () => {
    writeVerdict('a.md', 'approved')
    writeVerdict('b.md', 'rejected', ['high'])
    const r = run([
      { task_id: 'a', qa_mode: 'micro', verdict_path: 'qa/a.md' },
      { task_id: 'b', qa_mode: 'micro', verdict_path: 'qa/b.md' },
    ])
    expect(r.qualifies).toBe(false)
    expect(r.evidence.non_approved_tasks[0].task_id).toBe('b')
  })

  it('AA-005: disqualifies — empty task list', () => {
    const r = run([])
    expect(r.qualifies).toBe(false)
    expect(r.evidence.total_review_tasks).toBe(0)
  })

  it('AA-006: disqualifies — verdict artifact missing', () => {
    writeVerdict('a.md', 'approved')
    const r = run([
      { task_id: 'a', qa_mode: 'micro', verdict_path: 'qa/a.md' },
      { task_id: 'b', qa_mode: 'micro', verdict_path: 'qa/missing.md' },
    ])
    expect(r.qualifies).toBe(false)
    expect(r.evidence.non_approved_tasks.find(t => t.task_id === 'b').reason)
      .toBe('verdict_artifact_missing')
  })
})
