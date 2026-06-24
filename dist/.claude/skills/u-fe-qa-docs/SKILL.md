---
name: u-fe-qa-docs
description: Testing types, severity criteria, edge-case checklist, accessibility verification, and documentation patterns for front-end QA. Covers unit, component, integration (MSW), and E2E tests with Vitest, Testing Library, and Playwright. Loaded by orchestrator-dev when activating the QA & Docs agent.
user-invocable: false
---

# SKILL: QA & Docs

## Purpose
This skill defines how the QA & Docs Agent must structure tests, classify bugs, verify edge cases, and produce documentation that survives team turnover.

---

## Customization via CLAUDE.md

> Precedence rule defined in `orchestrator-core.md`. Not repeated here.

Before testing, extract from `CLAUDE.md`:

| What to look for | Used in |
|---|---|
| Configured testing framework | Tool selection in the matrix |
| Test naming convention | File names for `.spec` / `.test` |
| Project documentation location | Where to save generated docs |
| External APIs consumed by the front end | Edge cases for API responses |

---

## Verification scope by Task Contract type

> Refer to the unified **mandatory tests per Task Contract type** table in `.claude/skills/u-fe-standards/SKILL.md`. Apply only the required checks for the Task Contract type — do not run the universal checklist on narrow-scope Task Contracts.

---

## QA Agent role regarding tests

The Developer delivers tests alongside the code. The QA Agent **does not write tests** — it validates coverage, quality, and execution.

| Activity | Owner | Mode |
|---|---|---|
| Write unit and component tests | Developer | — |
| Write integration tests with mocked API | Developer | — |
| Write regression tests for bugfixes | Developer | — |
| Run build and tests, diagnose failures | **QA** | **test-gate** |
| Return structured diagnosis to the Developer | **QA** | **test-gate** |
| Validate that each acceptance criterion has a test | QA | full |
| Validate that tests assert the correct behavior | QA | full |
| Identify edge cases without test coverage | QA | full |
| Report missing or insufficient test quality as BUG | QA | full |

### Test-gate — failure diagnosis

> This section applies only to test-gate mode (defined in `qa-docs.md`). In full mode, tests have already passed.

When diagnosing failures in test-gate, classify each one with:

| Likely cause | Meaning | Example |
|---|---|---|
| `code` | The implementation has a bug — the test is correct but the code fails | Assertion `toEqual([1,2,3])` receives `[1,2]` |
| `test` | The test has a wrong or outdated expectation | Test expects old text after a copy change |
| `setup` | Configuration issue preventing execution | Missing mock, broken fixture, invalid import |
| `build` | Compilation/type error before test execution | `tsc --noEmit` fails, import of nonexistent module |

The diagnosis must be **actionable** — the Developer should be able to fix the issue just by reading the diagnosis, without further investigation.

**Timeout / flake / performance failures require falsification before a cause is assigned.** Do not infer the cause from reading alone — reproduce in isolation vs. under the full suite and vary the relevant knob (`testTimeout`, `--maxWorkers`/`poolOptions`, ordering), then record the result in the finding's `root_cause` (`confidence` + `evidence`). See `u-fe-standards/SKILL.md` → "Root-cause falsification (R5)" for the procedure and the contention heuristic. A `low`-confidence cause is a hypothesis, not a prescription.

### Test quality criteria

> Refer to the **test quality criteria** table in `standards/SKILL.md`. Use it as a reference when validating the tests delivered by the Developer.

---

## Test types and when to use each

| Type | When to use | Suggested tool |
|---|---|---|
| **Unit** | Pure utility functions, hooks, data transformation logic | Jest, Vitest |
| **Component** | Rendering, props, states, events, and behaviors of isolated components | Testing Library + Vitest/Jest |
| **Integration** | Flows across multiple components, global state, mocked API responses | Testing Library + MSW |
| **E2E** | Full flows from the user’s perspective navigating the application | Playwright, Cypress |
| **Manual** | Visual behaviors, responsiveness, perceived accessibility, exception flows hard to automate | Checklist in the report |

---

## Test matrix — how to fill it

The QA fills the matrix based on tests **delivered by the Developer**, not tests created by the QA.

For each acceptance criterion: locate the test in `tc-XX-delivery.md` ("Tests written" section) and record it in the matrix. If it does not exist, record the absence as a BUG.

```markdown
| ID    | Scenario                                   | Type        | Priority | Test file                      | Result |
|-------|--------------------------------------------|-------------|----------|-------------------------------|--------|
| T-01  | [Given/When/Then of acceptance criterion 1]| Component   | High     | `component.spec.tsx` (L.42)   | Passed |
| T-02  | [Given/When/Then of acceptance criterion 2]| Integration | High     | `page.spec.tsx` (L.88)        | Passed |
| T-03  | Edge: null prop in [component X]           | Component   | Medium   | `component.spec.tsx` (L.61)   | Passed |
| T-04  | Edge: empty list returned by API           | Integration | Medium   | Missing                        | BUG-01 |
| T-05  | Edge: API returns error 500                | Integration | High     | `page.spec.tsx` (L.102)       | Passed |
```

High priority -> must pass to approve the Task Contract.
Medium/Low priority -> absence generates a caveat, not automatic rejection.

---

## Edge cases, severity, and quality standards

> Refer to `.claude/skills/u-fe-standards/SKILL.md` (single source of truth) for: universal edge-case checklist, bug severity classification, and test quality criteria.

---

## Bug report template

> For the full bug report and QA report template, read `.claude/skills/u-fe-templates/qa-report.md`.

---

## Documentation verification

In the SDD flow, behavior documentation already exists in the spec (`feature.spec.md`, `flow.md`, `openapi.yaml`). The QA’s role is not to generate documentation — it is to verify that the Developer delivered the required inline documentation.

### What to verify

| Change | What the Developer should have delivered |
|---|---|
| New reusable component | JSDoc/TSDoc with documented props (name, type, required, description) |
| New custom hook | JSDoc with usage example and parameters |
| New environment variable | `.env.example` updated |

> If any required item is missing, log it as a `quality BUG` (Low severity). Do not generate the documentation yourself.

---

## Definition of Done — full checklist

A Task Contract can only move to `Done` when **all** items below are checked:

**Code quality (verify before running tests):**
- [ ] No `console.log` in modified production files — Quality BUG (Medium) if found
- [ ] No `dangerouslySetInnerHTML` without DOMPurify — Security BUG (Critical) if found
- [ ] No `export default` for components or types — Quality BUG (Medium) if found
- [ ] No `any` without justification comment — Quality BUG (Medium) if found
- [ ] No `TODO`/`FIXME` without Task Contract reference — Quality BUG (Medium) if found
- [ ] No commented-out code blocks — Quality BUG (Low) if found
- [ ] No inline CSS (`style=` / `style={{`) — Quality BUG (Medium) if found
- [ ] ErrorBoundary present at page/route level for new pages — Quality BUG (High) if missing
- [ ] No hardcoded user-facing strings when `i18n: true` — Quality BUG (Medium) if found

**Tests:**
- [ ] All acceptance criteria have at least one corresponding test
- [ ] All High priority tests are passing
- [ ] Edge cases from the universal checklist have been verified
- [ ] No Critical or High severity bugs are open

**Documentation (verify — do not generate):**
- [ ] New reusable components have JSDoc with documented props — if missing: quality BUG (Low)
- [ ] New custom hooks have JSDoc with usage example — if missing: quality BUG (Low)
- [ ] New environment variables are in `.env.example` — if missing: quality BUG (Low)

**Traceability:**
- [ ] QA report generated at `$SESSION_DIR/qa/$ORCH_TASK_ID-qa.md` with round number
- [ ] Bugs logged with severity and reproduction steps
- [ ] `task_completed` or `task_failed` event emitted via `emit.py`
- [ ] Orchestrator-Dev notified of the final verdict

**Round protocol:**
- Round 1 -> normal result
- Round 2 -> verify that only the reported bugs were fixed
- Round 3+ -> flag to the human before continuing; may indicate an issue with the acceptance criteria

---

## QA report template

> When generating `tc-XX-qa.md`, read the full template at `.claude/skills/u-fe-templates/qa-report.md`.
