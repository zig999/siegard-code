---
name: u-worker-compliance
description: Static analysis validator for worker and orchestrator .md protocol compliance (rules W01–W09 — terminal events, canonical phase values, register_worker arguments, emit.py skill declaration, exit-criteria gate fields declared by their producing worker). Run scripts/check_worker.py on .claude/agents/**/*.md before promoting to dist/; enforced in CI by tests/test_worker_compliance_gate.py, which fails the suite on any W01–W09 violation. Not user-invocable — reviewers and CI run the script directly.
user-invocable: false
allowed-tools: Bash(python3 *), Read, Glob, Grep
---

# SKILL: Worker Compliance Validator

## Purpose

Static analysis tool that validates worker agent `.md` files for protocol compliance before promotion to `dist/`. Eliminates the manual review gap that causes repeated critical issues on every worker audit cycle.

---

## When to Use

- Before promoting any worker or orchestrator to `dist/`
- When a new worker is created or an existing one is modified
- As a gate in the review phase — run `check_worker.py` on every `.claude/agents/**/*.md`

---

## What It Checks

### Rule W01 — Terminal event: task_completed

Every worker must contain a `task_completed` emit block with the required schema fields.

**Required fields in `--data`:** `phase`, `artifacts`

**Detection:** grep for `--kind completed` followed by `--data` containing `"phase"` and `"artifacts"`.

**Violation:** worker emits completed but omits `phase` or `artifacts`.

---

### Rule W02 — Terminal event: task_failed

Every worker must contain a `task_failed` emit block with the required schema fields.

**Required fields in `--data`:** `phase`, `reason`, `retryable`

**Detection:** grep for `--kind failed` followed by `--data` containing `"phase"`, `"reason"`, and `"retryable"`.

**Violation:** worker emits failed but omits any of the three required fields.

---

### Rule W03 — No terminal event

Worker contains no `emit.py` call with `--kind completed` or `--kind failed`.

**Severity:** CRITICAL — on_subagent_stop.py will synthesize task_failed for every run, including successes.

---

### Rule W04 — Non-canonical phase value

Worker hardcodes `"phase":"default"` in any emit call.

**Valid values:** any string except `"default"` (which signals missing implementation). Canonical values: `sdd`, `dev`, `review`, `test`.

**Detection:** grep for `"phase":"default"` or `"phase": "default"` in any emit.py call.

---

### Rule W05 — register_worker missing phase argument

Orchestrator file calls `register_worker(...)` without `phase=` keyword argument.

**Detection:** grep for `register_worker(` lines that do not contain `phase=`.

**Applies to:** orchestrator files only (filename starts with `orchestrator`).

**Violation:** on_subagent_stop.py falls back to full log replay to discover phase — unnecessary cost.

---

### Rule W06 — emit.py not in skills frontmatter

Worker YAML frontmatter `skills:` list does not include `orch-report`.

**Detection:** parse frontmatter block; check `skills` list for `orch-report` entry.

**Violation:** emit.py may not be available in the worker's context.

---

### Rule W08 — Gate field not declared in the producing worker's protocol

A field that a phase exit-criteria checker reads from a worker artifact is never named in
that worker's own `.md`.

**Detection:** `GATE_FIELDS_BY_WORKER` in `scripts/check_worker.py` maps each producing
worker to the `(field, checker)` pairs it owns; the rule requires a word-boundary mention of
each field in the worker file. Workers absent from the registry are not checked.

**Violation:** the worker can finish its work correctly and still block the phase. Origin:
`documentation_verified` was required by `check_documentation_verified.py` and documented
only in the qa-report template — the QA worker delivered the review, omitted the field, and
the phase blocked with `E08` after the fact. A requirement reachable only through a file the
agent is expected to open on its own is a requirement with a recurring failure mode.

**Maintenance:** adding a field to a checker means adding it to `GATE_FIELDS_BY_WORKER` and
to the worker protocol in the same change. The registry is the artifact → checker contract in
one place; leaving it stale fails this gate.

---

### Rule W09 — Review-only worker registers the artifact it reviewed

A worker in `REVIEW_ONLY_WORKERS` declares an `artifacts` entry under `domains/`.

**Detection:** scan every `"artifacts": [...]` payload in the worker `.md`; flag entries whose
path contains a `domains/` segment.

**Severity:** CRITICAL — separation of duties. A judge that can write its own subject can make a
finding disappear instead of reporting it.

**Violation origin:** a reviewer reported two **Major** issues via
`task_failed(validation_failed, retryable: true)`; the engine retried the same reviewer over
unchanged input, and the only route to terminal-success was for the problem to vanish. Attempt 2
edited both spec files, reclassified both findings as "minor", removed a business-rule block, and
approved its own edit — registering the spec files as its artifacts. Three guards now close it:
`should_retry` refuses to retry `validation_failed` on a verdict task type (R02b), `emit.py`
refuses the artifact path at runtime (R02c), and this rule refuses it in the agent contract.

---

## Output Format

```yaml
file: <path>
status: pass | fail
violations:
  - rule: W03
    severity: critical
    detail: "No --kind completed or --kind failed emit.py call found"
  - rule: W04
    severity: error
    detail: 'Hardcoded "phase":"default" in emit call at line 55'
```

Exit code: `0` = all pass, `1` = any violation found.

---

## Usage

### Validate a single worker

```bash
python3 .claude/skills/u-worker-compliance/scripts/check_worker.py \
  --file .claude/agents/dev/u-be-developer.md
```

### Validate all workers in a directory

```bash
python3 .claude/skills/u-worker-compliance/scripts/check_worker.py \
  --dir .claude/agents/
```

### Validate and emit structured JSON report

```bash
python3 .claude/skills/u-worker-compliance/scripts/check_worker.py \
  --dir .claude/agents/ \
  --format json > compliance-report.json
```

---

## Integration Points

- Run before any `git commit` that touches `.claude/agents/`
- Can be wired as a Claude Code hook: `UserPromptSubmit` → run on changed `.md` files
- Orchestrator can call it as a pre-promotion gate before `phase_transitioned`

---

## Limitations

- Static analysis only — does not execute workers or simulate orchestration
- Cannot verify that `task_id` and `attempt` are correctly interpolated at runtime
- Does not validate the semantic correctness of `artifacts` paths
