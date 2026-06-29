---
name: u-be-review
description: Read-only ad-hoc audit of backend code (a file, a directory, or a git diff) against the backend code-review rule registry — correctness, security, layering, API contract, type-safety, conventions, maintainability, explicit prohibitions, engineering principles (SOLID/CLEAN), folder structure, and tests. User-invocable. Emits an ephemeral structured parecer (findings grouped by severity plus a deterministic verdict). Does not modify files, write artifacts, or touch the orchestration log. Use this whenever someone wants a backend code review, a second opinion on a diff or pull request, a quality check before merging, or to verify that changed source files respect the project's backend standards.
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash(git diff:*)
dependencies:
  required:
    - skill: u-be-development
      path: .claude/skills/u-be-development/SKILL.md
      sections: ["Engineering principles", "Explicit prohibitions", "Naming conventions", "Error handling", "TypeScript code quality", "Architecture", "Default folder structure", "API design"]
      on_missing: "halt — report status: error / reason: dependency_not_found / dependency: u-be-development"
    - skill: u-be-standards
      path: .claude/skills/u-be-standards/SKILL.md
      sections: ["Bug severity classification", "Dependency Injection", "DTO and Validation Pattern", "Pagination", "Test quality criteria"]
      on_missing: "halt — report status: error / reason: dependency_not_found / dependency: u-be-standards"
    - skill: u-be-qa-docs
      path: .claude/skills/u-be-qa-docs/SKILL.md
      sections: ["Test types and when to use each", "Edge cases, severity, and quality standards"]
      on_missing: "halt — report status: error / reason: dependency_not_found / dependency: u-be-qa-docs"
  optional:
    - artifact: CLAUDE.md
      reads: ["di_strategy", "validation_library", "pagination.strategy", "naming conventions", "configured logger"]
      on_missing: "assume defaults — di_strategy=manual-factory, validation_library=zod, pagination.strategy=offset"
---

# SKILL: Backend Review

## Purpose

Audit one or more backend source files against the complete set of backend quality rules used in the development pipeline, and emit a **parecer**: findings grouped by severity plus a single deterministic verdict. This is a **read-only** skill — its only job is to analyze and judge.

> **Out-of-pipeline.** Requires no Task Contract, no active session, no orchestration log. Run it any time on any backend file, directory, or diff.

> **Read-only guarantee.** `allowed-tools` excludes `Edit`/`Write` by contract (P6 — least privilege). This skill never modifies code, never writes a report file, and never appends an event. The parecer lives only in the response. The rules it applies are the same ones the Developer must follow and the QA must verify — so a clean `u-be-review` parecer predicts a clean QA pass, and a `rejected` parecer surfaces the same blocking issues earlier and cheaper.

---

## Invocation

User-invocable skill — invoke it by name (there is no slash command). Arguments:

```
u-be-review [target] [--diff] [--focus CR-XXX]
```

| Argument | Required | Description |
|---|---|---|
| `target` | no | File path or directory. If a directory: scan backend source files recursively. Default when omitted: the project's backend source roots (`src/`, fallback to the working directory) |
| `--diff` | no | Restrict the scan to files reported by `git diff --name-only` (review a branch or pull request). When combined with `target`, intersect: only changed files under `target` |
| `--focus CR-XXX` | no | Limit detection to one category (e.g. `--focus CR-SEC`) or one rule (e.g. `--focus CR-SEC-01`). Everything else is skipped |

---

## Audit scope — Code Review Rule Registry (CR-NN)

Each rule carries its canonical source section so the standard stays single-sourced — the registry is the detection lens, not a second definition. Severity follows `u-be-standards § Bug severity classification`. Read the project's `CLAUDE.md` first (see ## Dependencies) so configurable rules (CR-ARC, CR-API, CR-TYP, CR-FLD) do not raise false positives against intentional project choices.

Each file is audited only against the rules that fit its class (production source vs test) — see ## Applicability by file class. Categories CR-SOL and CR-FLD are **heuristic** (judgment calls): flag only clear violations and stay silent when in doubt.

### 1. Correctness — `CR-COR`  (source: u-be-development § Error handling, u-be-standards § DTO/Pagination)

| Rule ID | What to detect | Severity |
|---|---|---|
| CR-COR-01 | Empty `catch {}` or a `catch` that swallows the error without rethrow/log | High |
| CR-COR-02 | `throw new Error("...")` with a generic message instead of a typed error class (`NotFoundError`, `ConflictError`, …) | Medium |
| CR-COR-03 | Raw `req.body` (or `unknown`) passed into a service without schema validation at the boundary | High |
| CR-COR-04 | Empty-list path returning `null` instead of `PaginatedResponse<T>` with `data: []` | High |
| CR-COR-05 | Resource-not-found path returning/throwing a 500-class error instead of a typed `NotFoundError` → 404 | Medium |

### 2. Security — `CR-SEC`  (source: u-be-development § Explicit prohibitions, § Error logging)

| Rule ID | What to detect | Severity |
|---|---|---|
| CR-SEC-01 | Raw SQL built by string concatenation/interpolation of input (no parameterization) | Critical |
| CR-SEC-02 | Hardcoded credential, token, secret, or environment URL in source | Critical |
| CR-SEC-03 | Secret, token, or credential written to a log or returned in an error message to the client | High |
| CR-SEC-04 | Stack trace or internal error detail exposed to the client | Medium |

### 3. Layering & Dependency Injection — `CR-ARC`  (source: u-be-development § Architecture, u-be-standards § Dependency Injection)

| Rule ID | What to detect | Severity |
|---|---|---|
| CR-ARC-01 | `new SomeDependency()` inside a service or controller (wiring outside a factory) | Medium |
| CR-ARC-02 | No factory function when `di_strategy: manual-factory` and the module wires dependencies | Medium |
| CR-ARC-03 | Constructor receives a concrete class where an interface exists | Low |
| CR-ARC-04 | DTO defined inline in a controller instead of `src/dto/` (or `src/modules/{domain}/dto/`) | Medium |
| CR-ARC-05 | Business logic placed in a controller or repository instead of a service | Medium |

### 4. API contract — `CR-API`  (source: u-be-development § API design, u-be-standards § Pagination)

| Rule ID | What to detect | Severity |
|---|---|---|
| CR-API-01 | Offset response missing `meta.pages`, or `meta.pages` hardcoded instead of `Math.ceil(total/limit)` | Medium |
| CR-API-02 | `limit` not validated against `max_limit` (no 400 + `PAGINATION_LIMIT_EXCEEDED`) | Medium |
| CR-API-03 | `PaginatedResponse<T>` redefined per module instead of imported from `src/types/pagination.ts` | Medium |
| CR-API-04 | Ad-hoc `{ data, meta }` shape instead of the canonical `PaginatedResponse<T>` | Medium |
| CR-API-05 | Error response not following `{ error: { code, message, details } }` | Medium |
| CR-API-06 | Route not versioned — missing the `/api/v1/` (or project-declared) URL prefix | Low |
| CR-API-07 | Wrong HTTP status for the semantics — create returning 200 not 201, delete-without-body not 204, validation failure not 422 | Medium |

### 5. Type safety — `CR-TYP`  (source: u-be-development § TypeScript code quality, § Explicit prohibitions)

| Rule ID | What to detect | Severity |
|---|---|---|
| CR-TYP-01 | Use of `any` | Medium |
| CR-TYP-02 | `as` type assertion without an accompanying type guard / narrowing | Medium |
| CR-TYP-03 | Public function signature missing explicit parameter or return types | Low |
| CR-TYP-04 | Magic number or magic string where a named constant is expected | Low |

### 6. Conventions — `CR-CON`  (source: u-be-development § Naming conventions, § Commit format)

| Rule ID | What to detect | Severity |
|---|---|---|
| CR-CON-01 | File / class / function / DTO / route / DB-identifier name deviating from the naming table | Low |
| CR-CON-02 | Commit subject without a semantic `feat/fix/refactor/test/docs/migration(TC-XX):` prefix (only checkable with `--diff` over `git log`) | Low |

### 7. Maintainability — `CR-MNT`  (source: u-be-development § TypeScript code quality, § Explicit prohibitions)

| Rule ID | What to detect | Threshold | Severity |
|---|---|---|---|
| CR-MNT-01 | Function longer than the project limit | > ~30 lines | Low |
| CR-MNT-02 | Function with too many positional parameters | > 3 params | Low |
| CR-MNT-03 | Commented-out code block | ≥ 2 consecutive commented code lines | Low |
| CR-MNT-04 | Unused import | any | Low |
| CR-MNT-05 | Logic duplicated across files (same block copy-pasted) | 2+ occurrences | Medium |

### 8. Prohibitions — `CR-PRH`  (source: u-be-development § Explicit prohibitions, u-be-standards § Test quality criteria)

| Rule ID | What to detect | Severity |
|---|---|---|
| CR-PRH-01 | `console.log` / `console.error` / `console.warn` in non-test production code (use the configured logger) | Medium |
| CR-PRH-02 | `TODO` / `FIXME` without a `(TC-XX)` reference | Medium |
| CR-PRH-03 | Destructive migration without a `down` / rollback | High |
| CR-PRH-04 | Lint-disable (`eslint-disable`, `# noqa`, `// nolint`) without a justifying comment | Medium |

### 9. Engineering principles — `CR-SOL`  (source: u-be-development § Engineering principles, § Architecture)

**Structurally detectable — flag when present (CR-SOL-01, CR-SOL-05):** these patterns are identifiable from the file content without contextual judgment. Do not apply "stay silent when in doubt" to these rules.

**Heuristic — flag only clear violations, stay silent when in doubt (CR-SOL-02, CR-SOL-03, CR-SOL-04):** these require contextual judgment. Only flag when the violation is unambiguous.

| Rule ID | Detection mode | What to detect | Severity |
|---|---|---|---|
| CR-SOL-01 | Structural | A class/module spanning more than one layer's responsibility — e.g. a service issuing HTTP responses, or calling the DB driver directly instead of through a repository (SRP / separation of concerns) | Medium |
| CR-SOL-02 | Heuristic | A domain entity importing a framework or external library (entities must stay framework-free) | Medium |
| CR-SOL-03 | Heuristic | Circular dependency between modules (A imports B and B imports A, directly or transitively across the scanned set) | Medium |
| CR-SOL-04 | Heuristic | Deep or concrete inheritance where composition fits (`extends` a concrete domain class, or 3+ inheritance levels) | Low |
| CR-SOL-05 | Structural | A large `switch`/`if-else` on a type field, repeated across files, that should be polymorphism (OCP) | Low |

### 10. Folder structure & placement — `CR-FLD`  (source: u-be-development § Default folder structure, § Naming conventions)

> Respect the `CLAUDE.md` `folder_structure` choice (`layered` default vs `modules`). Do not raise a placement finding that conflicts with the declared structure.

| Rule ID | What to detect | Severity |
|---|---|---|
| CR-FLD-01 | File in the wrong layer folder for its role suffix — a `*.service.*` outside `services/` (or `{domain}/service/`), a `*.controller.*` outside `controllers/`, etc. | Low |
| CR-FLD-02 | Business-logic file at the project root or in `utils/` instead of a layer folder | Low |
| CR-FLD-03 | A shared type duplicated per module instead of living in `src/types/` (generalizes CR-API-03 beyond pagination) | Medium |
| CR-FLD-04 | DTO file outside `src/dto/` or `src/modules/{domain}/dto/` | Low |
| CR-FLD-05 | Test file not mirroring the `__tests__/` (or project-declared) test structure | Low |

### 11. Tests — `CR-TST`  (source: u-be-standards § Test quality criteria, u-be-qa-docs § Test types)

> Applied **only to test files**. Coverage-style criteria that need a Task Contract / acceptance criteria (AC-to-test mapping, regression-reproduces-the-bug, required-edge-case coverage) are **out of scope** for an ad-hoc review — they need the pipeline's TC context. CR-TST covers what is statically checkable in the test file itself.

| Rule ID | What to detect | Severity |
|---|---|---|
| CR-TST-01 | Asserting on an implementation detail instead of behavior — e.g. `expect(repo.findById).toHaveBeenCalled()`, `expect(service.internalState)` | Medium |
| CR-TST-02 | Tautological / always-passing test — `expect(true).toBe(true)`, constant-equals-constant, or an empty test body | Medium |
| CR-TST-03 | Integration test (exercises a route/endpoint) asserting only success — no 4xx/5xx error-path assertion anywhere in the file | Medium |
| CR-TST-04 | Mock/stub applied to business logic instead of only boundaries (DB, network, external API, filesystem) | Medium |
| CR-TST-05 | Tests coupled by execution order / shared mutable state with no reset (no `beforeEach`/cleanup; a module-level `let` mutated across cases) | Medium |
| CR-TST-06 | Non-descriptive test name — `it('works')`, `test('test1')`, names that don't state the expected behavior | Low |

---

## Applicability by file class

Each scanned file is audited only against the rules that fit its class. This is why test files are now **scanned, not skipped** — but judged by test rules, not production-code rules (and vice-versa).

| File class | Matches | Rules applied | Rules NOT applied |
|---|---|---|---|
| **Source** (production) | everything not matching a test pattern | CR-COR, CR-SEC, CR-ARC, CR-API, CR-TYP, CR-CON, CR-MNT, CR-PRH, CR-SOL, CR-FLD | CR-TST |
| **Test** | `*.spec.*`, `*.test.*`, `__tests__/`, `/tests/` | CR-TST, CR-SEC-02, CR-PRH-02, CR-PRH-04, CR-FLD-05 | CR-COR, CR-ARC, CR-API, CR-CON, CR-MNT, CR-SOL, CR-PRH-01 (console.* is allowed in tests) |

> **Out of scope for both classes** (require Task Contract / spec context, unavailable in an ad-hoc review): acceptance-criteria-to-test coverage, regression-reproduces-the-bug, required-edge-case coverage, and behavioral edge-cases (401/403/429, concurrency, DB-down). These are enforced by the dev/review pipeline, not here. List them under Warnings as `not evaluated (needs pipeline context)` when the scan would otherwise imply full coverage.

---

## Dependencies

Resolve before executing any audit step. Halt on a missing required dependency.

```yaml
dependencies:
  required:
    - skill: u-be-development
      path: .claude/skills/u-be-development/SKILL.md
      used_in: [CR-COR, CR-SEC, CR-ARC, CR-API, CR-TYP, CR-CON, CR-MNT, CR-PRH]
      on_missing:
        status: error
        reason: dependency_not_found
        dependency: u-be-development

    - skill: u-be-standards
      path: .claude/skills/u-be-standards/SKILL.md
      used_in: [CR-COR, CR-ARC, CR-API, CR-TST, severity_classification, verdict]
      on_missing:
        status: error
        reason: dependency_not_found
        dependency: u-be-standards

    - skill: u-be-qa-docs
      path: .claude/skills/u-be-qa-docs/SKILL.md
      used_in: [CR-TST]
      on_missing:
        status: error
        reason: dependency_not_found
        dependency: u-be-qa-docs

  optional:
    - artifact: CLAUDE.md
      reads: [di_strategy, validation_library, pagination.strategy, naming, logger]
      on_missing:
        action: assume defaults
        defaults: { di_strategy: manual-factory, validation_library: zod, pagination.strategy: offset }
```

---

## Execution process

```
Step 0 — Resolve dependencies and config
  - Read .claude/skills/u-be-development/SKILL.md — halt if not found
  - Read .claude/skills/u-be-standards/SKILL.md   — halt if not found
  - Read .claude/skills/u-be-qa-docs/SKILL.md     — halt if not found
  - Read CLAUDE.md if present — extract di_strategy, validation_library,
    pagination.strategy, folder_structure, naming overrides, configured logger
    (else defaults)

Step 1 — Resolve and classify target set
  - If --diff: run `git diff --name-only` (and intersect with `target` if given)
  - Else if target is a file: scan list = [target]
  - Else if target is a directory (or omitted → src/ then cwd):
      glob backend source files recursively
  - Source extensions: .ts, .js, .py, .cs, .go, .java, .rb, .php (and project-declared)
  - Skip entirely: node_modules/, dist/, build/, .orch/, and any binary/non-text file
  - Classify each remaining file:
      • test file   → matches *.spec.*, *.test.*, __tests__/, /tests/
      • source file → everything else

Step 2 — Audit each file
  For each file in scan list:
    - Read file content
    - Apply the rule set for the file's class (see ## Applicability by file class),
      restricted by --focus if provided
    - Collect findings: {rule_id, file, line, excerpt, severity, rationale}

Step 3 — Classify and derive verdict
  - Tally findings_by_severity from u-be-standards § Bug severity classification
  - Derive verdict deterministically (see ## Verdict)

Step 4 — Emit parecer (always; report-only, nothing written to disk)
```

---

## Verdict

Derived deterministically from the highest severity present, aligned with `u-be-standards § Bug severity classification` (Critical/High reject a Task Contract; Medium approves with a mandatory caveat; Low does not block).

| Verdict | Condition |
|---|---|
| `rejected` | At least one `critical` **or** at least one `high` finding |
| `approved_with_caveats` | No critical/high finding **and** at least one `medium` finding |
| `approved` | Only `low` findings, or no findings at all |

---

## Output format

A YAML parecer block followed by the Markdown report. Both go to the response only — no file is written.

```yaml
# review-parecer
target: "<path | diff>"
timestamp: "<YYYY-MM-DDTHH:MM:SSZ>"
mode: "scan" | "diff"
focus: "<CR-XXX | all>"
stack: be
config:
  di_strategy: "<resolved>"
  validation_library: "<resolved>"
  pagination_strategy: "<resolved>"
  folder_structure: "<resolved>"
files_scanned: <int>
findings_total: <int>
findings_by_severity:
  critical: <int>
  high: <int>
  medium: <int>
  low: <int>
verdict: approved | approved_with_caveats | rejected
```

Followed by:

```markdown
# Backend Review — <target>

> Scanned: <N> files | Findings: <N> | Verdict: <verdict> | Date: YYYY-MM-DD

---

## Critical findings

| # | Rule | File | Line | Excerpt | Rationale |
|---|------|------|------|---------|-----------|
| 1 | CR-SEC-01 | user.repository.ts | 54 | `` `SELECT * FROM users WHERE id = ${id}` `` | Unparameterized SQL — injection risk |

## High findings
[same table]

## Medium findings
[same table]

## Low findings
[same table]

---

## Warnings

- [non-finding warnings, e.g. a file that could not be read]
```

When `findings_total` is 0, emit the parecer block with `verdict: approved` and a single line: `No findings. Code conforms to backend standards for the scanned scope.`

---

## Quality rules

| Condition | Action |
|---|---|
| Required dependency missing | Halt — `status: error / reason: dependency_not_found / dependency: <name>` |
| `target` path does not exist | Halt — `status: error / reason: target_not_found` |
| `--diff` outside a git repository | Halt — `status: error / reason: not_a_git_repo` |
| `--diff` reports no changed files | Emit parecer with `files_scanned: 0`, `verdict: approved` |
| File is binary or non-text | Skip file — log in Warnings |
| File cannot be read | Skip file — log in Warnings |
| A configurable rule (CR-ARC/CR-API/CR-TYP/CR-FLD) conflicts with a `CLAUDE.md` choice | Respect `CLAUDE.md` — do not raise the finding |
| A heuristic rule (CR-SOL/CR-FLD) is uncertain | Stay silent — flag only clear violations |
| Any finding | Report only — never edit, never write a file, never append an event |
