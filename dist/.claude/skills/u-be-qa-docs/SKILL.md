---
name: u-be-qa-docs
description: Testing types, severity criteria, edge-case checklist, and documentation patterns for back-end QA. Covers unit, integration, and E2E tests for routes, services, repositories, and middleware. Loaded by orchestrator-dev when activating the QA & Docs agent.
user-invocable: false
---

# SKILL: QA & Docs (Backend)

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
| ORM/database | Test setup/teardown strategy |

---

## Verification scope by Task Contract type

> Refer to the unified **mandatory tests per Task Contract type** table in `standards/SKILL.md`. Apply only the required checks for the Task Contract type — do not run the universal checklist on narrow-scope Task Contracts.

---

## QA Agent role regarding tests

The Developer delivers tests alongside the code. The QA Agent **does not write tests** — it validates coverage, quality, and execution.

| Activity | Owner | Mode |
|---|---|---|
| Write unit tests for services and repositories | Developer | — |
| Write integration tests for routes/endpoints | Developer | — |
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
| `code` | The implementation has a bug — the test is correct but the code fails | Assertion `toEqual({status: 200})` receives `{status: 500}` |
| `test` | The test has a wrong or outdated expectation | Test expects old response body after a schema change |
| `setup` | Configuration issue preventing execution | Missing mock, test database unavailable, broken fixture |
| `build` | Compilation/type error before test execution | `tsc --noEmit` fails, import of nonexistent module |

The diagnosis must be **actionable** — the Developer should be able to fix the issue just by reading the diagnosis, without further investigation.

**Timeout / flake / performance failures require falsification before a cause is assigned.** Do not infer the cause from reading alone — reproduce in isolation vs. under the full suite and vary the relevant knob (timeout, concurrency, ordering), then record the result in the finding's `root_cause` (`confidence` + `evidence`). See `u-be-standards/SKILL.md` → "Root-cause falsification (R5)" for the procedure and the contention heuristic. A `low`-confidence cause is a hypothesis, not a prescription.

### Test quality criteria

> Refer to the **test quality criteria** table in `standards/SKILL.md`. Use it as a reference when validating the tests delivered by the Developer.

---

## Test types and when to use each

| Type | When to use | Suggested tool |
|---|---|---|
| **Unit** | Service functions, business rules, validations, data transformations | Jest, Vitest, pytest |
| **Integration** | Routes/endpoints (request -> response), middleware chain, repository with real or in-memory database | Supertest + Jest, httptest, pytest + TestClient |
| **E2E** | Full cross-service flows, health checks, complete authentication flows | Supertest, pytest, Postman/Newman |
| **Manual** | Concurrency scenarios, load performance, flows requiring real infrastructure | Checklist in the report |

---

## Test matrix — how to fill it

The QA fills the matrix based on tests **delivered by the Developer**, not tests created by the QA.

For each acceptance criterion: locate the test in `tc-XX-delivery.md` ("Tests written" section) and record it in the matrix. If it does not exist, record the absence as a BUG.

```markdown
| ID    | Scenario                                   | Type        | Priority | Test file                           | Result |
|-------|--------------------------------------------|-------------|----------|-------------------------------------|--------|
| T-01  | [Given/When/Then of acceptance criterion 1]| Integration | High     | `__tests__/integration/user.spec.ts` (L.42) | Passed |
| T-02  | [Given/When/Then of acceptance criterion 2]| Unit        | High     | `__tests__/unit/user.service.spec.ts` (L.88)| Passed |
| T-03  | Edge: null input in createUser             | Unit        | Medium   | `__tests__/unit/user.service.spec.ts` (L.61)| Passed |
| T-04  | Edge: duplicate resource (409)             | Integration | Medium   | Missing                                      | BUG-01 |
| T-05  | Edge: unauthenticated request (401)        | Integration | High     | `__tests__/integration/user.spec.ts` (L.102)| Passed |
```

High priority -> must pass to approve the Task Contract.
Medium/Low priority -> absence generates a caveat, not automatic rejection.

---

## Edge cases, severity, and quality standards

> Refer to `standards/SKILL.md` (single source of truth) for: universal edge-case checklist, bug severity classification, and test quality criteria.

---

## Bug report template

> For the full bug report and QA report template, read `.claude/skills/u-be-templates/qa-report.md`.

---

## Documentation verification

In the SDD flow, behavior documentation already exists in the spec (`openapi.yaml`, `.back.md`, `.spec.md`). The QA's role is not to generate documentation — it is to verify that the Developer delivered the required inline documentation.

### What to verify

| Change | What the Developer should have delivered |
|---|---|
| New service with complex business logic | JSDoc/TSDoc on the class/function |
| New environment variable | `.env.example` updated |
| New migration | Comment in the migration explaining the reason |
| New reusable middleware | JSDoc with usage example and configuration |

> If any required item is missing, log it as a `quality BUG` (Low severity). Do not generate the documentation yourself.

---

## Definition of Done — full checklist

A Task Contract can only move to `Done` when **all** items below are checked:

**Tests:**
- [ ] All acceptance criteria have at least one corresponding test
- [ ] All High priority tests are passing
- [ ] Edge cases from the universal checklist have been verified
- [ ] No Critical or High severity bugs are open
- [ ] Integration tests cover both success and error scenarios

**Documentation (verify — do not generate):**
- [ ] New services with complex rules have JSDoc/TSDoc — if missing: quality BUG (Low)
- [ ] New environment variables are in `.env.example` — if missing: quality BUG (Low)
- [ ] Migrations have a comment explaining the reason — if missing: quality BUG (Low)
- [ ] New reusable middleware has JSDoc — if missing: quality BUG (Low)

**Security:**
- [ ] Parameterized queries (no SQL concatenation)
- [ ] No secrets in logs or error responses
- [ ] Authentication and authorization validated on new endpoints

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

> When generating `tc-XX-qa.md`, read the full template at `.claude/skills/u-be-templates/qa-report.md`.

---

## Short Mode Activation

Activated by the Orchestrator from the 2nd invocation of this agent in the same session, and for all post-QA correction cycles.

In short mode, the Orchestrator passes a compact reminder instead of the full skill. The reminder must include:
1. Test command from `CLAUDE.md` (e.g., `npm test`)
2. Acceptance criteria list from the Task Contract
3. Verdict format: `approved | rejected`

Full skill re-read is skipped — agent relies on established standards from the first invocation.
