---
name: u-be-standards
description: Shared quality standards used by both Developer and QA agents (backend). Defines mandatory tests per Story type, universal edge-case checklist, and test quality criteria. Single source of truth to avoid divergence between implementation and verification.
user-invocable: false
---

# SKILL: Standards — Backend (shared)

## Purpose
This skill is the **single source of truth** for the quality standards the Developer must follow when implementing and the QA must use when verifying. Both agents receive this file in context — any change here automatically propagates to both sides.

---

## Mandatory tests per Story type

| Story type | What the Developer must deliver | What the QA must verify |
|---|---|---|
| **New feature** | Unit for services/utils + Integration for routes (request -> response) + Input validation test | All criteria + edge cases. Documentation required for new artifacts |
| **Improvement** | Tests for modified behaviors (unit or integration) + update of affected existing tests | Modified criteria + in-scope edge cases. Regression required. Docs if new artifacts |
| **Refactoring** | Tests for preserved behaviors must keep passing; do not add new logic without a test | Preserved behaviors. Regression required. Docs only if the interface changed |
| **Bugfix** | Regression test required: reproduces the bug before the fix and confirms it passes after | Only the reported case + immediate regression |

---

## Test quality criteria

These criteria apply to both writing (Developer) and validation (QA).

| Criterion | Approved | Rejected (quality BUG) |
|---|---|---|
| Criteria coverage | Every acceptance criterion has at least 1 test | Criterion without test — High BUG |
| Edge case coverage | Required edge cases for the Story type have tests | Edge case without test — Medium BUG |
| Test behavior | `expect(response.status).toBe(201)` | `expect(service.internalState)` — Medium BUG |
| Integration covers error | There is a 4xx/5xx test + response body verification | Only tests success — Medium BUG |
| Regression on bugfix | Reproduces the bug and confirms the fix | Missing — High BUG |
| Tests pass | All tests pass on execution | Failure — High BUG |
| Test isolation | Each test cleans up its state (truncate, rollback, mocks reset) | Interdependent tests — Medium BUG |
| `TODO`/`FIXME` | Forbidden in committed code — open an issue/task before committing. Exception: `// TODO(US-XX):` linked to an active Story | `TODO`/`FIXME` without issue reference — Medium BUG |
| Lint-disable | Forbidden to disable lint rules (e.g., `eslint-disable`, `# noqa`, `// nolint`) without a comment justifying the reason | Lint-disable without justification — Medium BUG |

**Additional rules:**
- Test **behavior**, not implementation: prefer `expect(response.body.data.name).toBe("João")` over `expect(repository.findById).toHaveBeenCalled()`
- Each acceptance criterion of the Story must have at least one mapped test
- Edge cases handled in production code must have a corresponding test
- Integration tests must cover both success **and** error responses
- Tests must be isolated — do not depend on execution order or another test's state
- Avoid tests that always pass (`expect(true).toBe(true)`) — the QA will reject them
- Follow the AAA pattern: Arrange -> Act -> Assert
- Name tests descriptively: `should return error when email is already registered`
- Use mocks/stubs only at boundaries (I/O, database, external APIs) — never on business logic

---

## Edge cases — universal checklist

For every Story, verify the following:

**Handling patterns (Developer):**

| Scenario | How to handle |
|---|---|
| Null or undefined input | Validate at the validation layer (schema), before reaching the service |
| Empty list | Return `{ data: [], meta: { page, limit, total } }`, never `null` |
| Resource not found | Throw `NotFoundError` in the service -> controller returns 404 |
| Duplicate data | Catch unique constraint violation -> return 409 Conflict |
| Partially failed transaction | Use transaction/rollback — never leave data in an inconsistent state |
| Payload exceeding allowed size | Limit at the middleware level (body size limit) |
| Rate limit reached | Return 429 with `Retry-After` header |

**Input data:**
- [ ] Null or undefined input
- [ ] Empty string `""`
- [ ] Zero or negative number
- [ ] Empty list `[]`
- [ ] Boundary values (e.g., max characters, min/max of a range)
- [ ] Special characters and unicode in text fields
- [ ] Payload exceeding maximum allowed size

**Security and authentication:**
- [ ] Request without authentication token -> 401
- [ ] Request with expired token -> 401
- [ ] Request with valid token but insufficient permissions -> 403
- [ ] SQL injection attempt in text fields
- [ ] Attempt to access another user's resource -> 403 or 404
- [ ] Missing required headers

**System state:**
- [ ] Resource not found -> 404 (not 500)
- [ ] Duplicate resource (unique constraint) -> 409
- [ ] Resource in invalid state for the operation (e.g., trying to publish what is already published) -> 422
- [ ] Concurrency: two simultaneous requests on the same resource

**Integration and infrastructure:**
- [ ] Database unavailable -> handled error, not a crash
- [ ] External service returns error or timeout -> fallback or clear error
- [ ] External service response with unexpected format -> handled error
- [ ] Migration rollback works correctly

> **Developer:** handle the applicable scenarios for your Story and document them in the delivery file.
> **QA:** verify that applicable scenarios were handled and have a corresponding test.

---

## Bug severity classification

| Severity | Criterion | Impact on the Story |
|---|---|---|
| **Critical** | System crashes, data corruption, security breach, SQL injection possible | Reject + block other tests |
| **High** | Acceptance criterion not met, main flow broken, endpoint returns 500 on expected case | Reject the Story |
| **Medium** | Edge case not handled, uninformative error message, incorrect response field | Approve with mandatory caveat |
| **Low** | Naming inconsistency, unnecessary log, incomplete documentation | Log it, does not block approval |
