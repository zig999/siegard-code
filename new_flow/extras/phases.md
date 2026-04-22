# Phases

Siegard v2 executes workflows in up to four phases. Each phase has a dedicated orchestrator, a set of workers, and deterministic exit criteria evaluated by Python scripts.

```
sdd → dev → review → test
```

---

## Phase 1: SDD — Specification & Design

**Orchestrator**: `orchestrator-sdd.md`
**Human interaction**: Confirmation gates (async via escalation + human_response).
**Input**: User-provided feature description or requirement document.
**Output**: `handoff-manifest.yaml` + validated spec files in `SPECS_DIR`.

### Worker routing (`phase-sdd-rules/scripts/select_worker.py`)

| task.type | Worker |
|-----------|--------|
| `spec-writer` | `u-spec-writer` |
| `spec-reviewer` | `u-spec-reviewer` |
| `spec-back` | `u-spec-back` |
| `spec-front` | `u-spec-front` |
| `spec-validator` | `u-spec-validator` |
| `spec-compliance` | `u-spec-compliance` |

### Execution flow

```
1. orchestrator-sdd reduces log; derives current SDD state
2. Creates task_created(spec-writer) for each domain in scope
3. Dispatches spec-writer workers (parallel if multiple domains)
4. Spec-reviewer reviews each spec:
   - approved → task_completed; proceed
   - rejected → retry writer (max 3 rejections before escalation E03)
5. Spec-back validates backend contracts
6. Spec-validator validates cross-domain consistency:
   - VALID → proceed
   - INVALID → return to writer (max 2 rejections before escalation E03)
7. Spec-front validates frontend contracts
8. Spec-compliance checks prohibition compliance
9. Human confirmation gate:
   - orchestrator-sdd emits escalation(E12)
   - Meta presents handoff manifest to human
   - Human responds: confirm_proceed → phase_transitioned(sdd→dev)
               │     abort → stop
               └──   return_to_writer → cycle restarts
```

### Exit criteria

All must be satisfied before `phase_exit_approved`:

| Criterion | Script | What it checks |
|-----------|--------|----------------|
| `handoff_manifest_approved` | `check_handoff_manifest_approved.py` | `handoff-manifest.yaml` exists with `Status: approved` |
| `all_domains_validated` | `check_all_domains_validated.py` | No `INVALID` status in `SPECS_DIR/_validation/` |
| `error_codes_synced` | `check_error_codes_synced.py` | All `error.code` values in `error-codes.md` |

---

## Phase 2: Dev — Implementation

**Orchestrator**: `orchestrator-dev.md`
**Human interaction**: Autonomous. No gates during execution.
**Input**: `handoff-manifest.yaml` from SDD (determines stack: be/fe/fullstack).
**Output**: delivery artifacts in `SESSION_DIR/delivery/<task_id>-delivery.md`.

### Worker routing (`phase-dev-rules/scripts/select_worker.py`)

| task.type | Stack | Worker |
|-----------|-------|--------|
| `planning` | `be` | `u-be-planner` |
| `planning` | `fe` | `u-fe-planner` |
| `impl` | `be` | `u-be-developer` |
| `impl` | `fe` | `u-fe-developer` |
| `impl` | `fullstack` | `u-be-developer` + `u-fe-developer` |

### Execution flow

```
1. orchestrator-dev reads handoff-manifest.yaml → derives stack
2. Creates task_created(planning, stack=<be|fe|fullstack>)
3. Dispatches planner worker
4. Planner generates backlog.json: array of task contracts
   (each: task_id, spec path, deps, tier, type, stack, title)
5. For each task contract in backlog:
   - emit task_created(impl, deps=[...], tier=<critical|standard>)
6. Dispatches impl workers (parallel where deps allow)
   - Critical tier tasks dispatched first; others wait
7. Each worker delivers: SESSION_DIR/delivery/<task_id>-delivery.md
   Frontmatter required: task_id, qa_ready: true, prohibition_violations: []
```

### Backlog schema

```json
[
  {
    "task_id": "dev_tc_001",
    "spec":    "sessions/2026-04-21/backlog/tc-001.md",
    "deps":    [],
    "tier":    "critical",
    "type":    "impl",
    "stack":   "be",
    "title":   "POST /auth/login with JWT issuance"
  }
]
```

### Delivery artifact schema

```markdown
---
task_id: dev_tc_001
qa_ready: true
prohibition_violations: []
summary: "Implemented POST /auth/login with JWT issuance"
spec_divergences: []
---
## Changes
## Tests Written
## Notes for QA
```

### Exit criteria

| Criterion | Script | What it checks |
|-----------|--------|----------------|
| `all_impl_tasks_terminal` | `check_all_impl_tasks_terminal.py` | All dev tasks in `completed` or `dlq` |
| `all_deliveries_qa_ready` | `check_all_deliveries_qa_ready.py` | All `delivery.md` have `qa_ready: true` |
| `no_open_prohibitions` | `check_no_open_prohibitions.py` | No `prohibition_violations` in any delivery |

---

## Phase 3: Review — QA & Approval

**Orchestrator**: `orchestrator-review.md`
**Human interaction**: Semi-autonomous. Human approves or rejects the QA verdict summary.
**Input**: Delivery artifacts from Dev phase.
**Output**: QA verdict files in `SPECS_DIR/qa/<task_id>-qa.md`.

### Worker routing (`phase-review-rules/scripts/select_worker.py`)

| task.type | Worker |
|-----------|--------|
| `qa` (backend) | `u-be-qa-docs` |
| `qa` (frontend) | `u-fe-qa-docs` |
| `architecture-review` | `u-architecture-reviewer` |
| `security-review` | `u-security-reviewer` |

### Execution flow

```
1. orchestrator-review reads delivery artifacts from dev phase
2. For each delivery: emit task_created(qa, delivery_artifact_path=...)
3. Dispatches QA workers (parallel)
4. Each worker produces: SPECS_DIR/qa/<task_id>-qa.md
   Verdicts: approved | approved_with_reservations | rejected
5. Human approval gate:
   - orchestrator-review collects all verdicts
   - Emits escalation(E12) with verdict summary
   - Human responds:
     confirm_proceed → all approved → phase_transitioned(review→test)
     return_to_dev → rejected tasks return to dev backlog
```

### QA verdict artifact schema

```markdown
---
task_id: dev_tc_001
verdict: approved
documentation_verified: true
findings:
  - id: QA-001
    severity: low
    description: "Missing JSDoc on authService.generateToken()"
    file: src/services/auth_service.ts
    suggestion: "Add @param and @returns annotations"
test_coverage:
  unit: true
  integration: true
  e2e: false
---
## QA Review — dev_tc_001
...
```

### Exit criteria

| Criterion | Script | What it checks |
|-----------|--------|----------------|
| `all_qa_verdicts_approved` | `check_all_qa_verdicts_approved.py` | No verdict == `rejected` |
| `no_open_critical_findings` | `check_no_open_critical_findings.py` | No finding with `severity: critical` or `high` |
| `documentation_verified` | `check_documentation_verified.py` | At least one QA verdict with `documentation_verified: true` |

---

## Phase 4: Test — Automated Testing

**Orchestrator**: `orchestrator-test.md` (pending — deferred post-pilot)
**Human interaction**: Fully autonomous.
**Input**: Implementation artifacts from Dev phase.
**Output**: Test execution results.

### Execution flow (planned)

```
1. Read test runner from CLAUDE.md (field: test_runner)
2. For each test suite: emit task_created(test-run)
3. Spawn test runner workers (parallel)
4. Collect results: pass_count, failure_count, coverage_pct
```

### Exit criteria (planned)

| Criterion | What it checks |
|-----------|----------------|
| `all_tests_passing` | Zero failed tests |
| `coverage_target_met` | `coverage_pct >= threshold` (default 80%) |

---

## Exit Criterion Checker Protocol

All checker scripts in `phase-{name}-rules/scripts/check_*.py` follow this contract:

**Invocation**:
```bash
ORCH_PROJECT_DIR=<path> python3 .claude/skills/phase-dev-rules/scripts/check_all_impl_tasks_terminal.py
```

**Output (stdout, JSON)**:
```json
{
  "criterion": "all_impl_tasks_terminal",
  "met":       true,
  "evidence":  [101, 102, 103, 104],
  "details": {
    "total_impl_tasks": 12,
    "completed":        11,
    "dlq":               1,
    "still_running":     0
  }
}
```

**Exit code**: 0 always (errors reported in output JSON).

Phase orchestrators call all checkers in the pre-transition step; emit `phase_exit_criterion_met` for each `met: true` result before evaluating `phase_exit_approved`.
