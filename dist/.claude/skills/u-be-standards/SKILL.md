---
name: u-be-standards
description: Shared quality standards used by both Developer and QA agents (backend). Defines mandatory tests per Task Contract type, universal edge-case checklist, and test quality criteria. Single source of truth to avoid divergence between implementation and verification.
user-invocable: false
---

# SKILL: Standards — Backend (shared)

## Purpose
This skill is the **single source of truth** for the quality standards the Developer must follow when implementing and the QA must use when verifying. Both agents receive this file in context — any change here automatically propagates to both sides.

---

## Mandatory tests per Task Contract type

| Task Contract type | What the Developer must deliver | What the QA must verify |
|---|---|---|
| **feature** | Unit for services/utils + Integration for routes (request -> response) + Input validation test | All criteria + edge cases. Documentation required for new artifacts |
| **refactoring** | Tests for modified behaviors (unit or integration) + update of affected existing tests | Modified criteria + in-scope edge cases. Regression required. Docs if new artifacts |
| **refactoring (structure-only)** | Tests for preserved behaviors must keep passing; do not add new logic without a test | Preserved behaviors. Regression required. Docs only if the interface changed |
| **bugfix** | Regression test required: reproduces the bug before the fix and confirms it passes after | Only the reported case + immediate regression |

---

## Test quality criteria

These criteria apply to both writing (Developer) and validation (QA).

| Criterion | Approved | Rejected (quality BUG) |
|---|---|---|
| Criteria coverage | Every acceptance criterion has at least 1 test | Criterion without test — High BUG |
| Edge case coverage | Required edge cases for the Task Contract type have tests | Edge case without test — Medium BUG |
| Test behavior | `expect(response.status).toBe(201)` | `expect(service.internalState)` — Medium BUG |
| Integration covers error | There is a 4xx/5xx test + response body verification | Only tests success — Medium BUG |
| Regression on bugfix | Reproduces the bug and confirms the fix | Missing — High BUG |
| Tests pass | All tests pass on execution | Failure — High BUG |
| Test isolation | Each test cleans up its state (truncate, rollback, mocks reset) | Interdependent tests — Medium BUG |
| `TODO`/`FIXME` | Forbidden in committed code — open an issue/task before committing. Exception: `// TODO(TC-XX):` linked to an active Task Contract | `TODO`/`FIXME` without issue reference — Medium BUG |
| Lint-disable | Forbidden to disable lint rules (e.g., `eslint-disable`, `# noqa`, `// nolint`) without a comment justifying the reason | Lint-disable without justification — Medium BUG |

**Additional rules:**
- Test **behavior**, not implementation: prefer `expect(response.body.data.name).toBe("John Smith")` over `expect(repository.findById).toHaveBeenCalled()`
- Each acceptance criterion of the Task Contract must have at least one mapped test
- Edge cases handled in production code must have a corresponding test
- Integration tests must cover both success **and** error responses
- Tests must be isolated — do not depend on execution order or another test's state
- Avoid tests that always pass (`expect(true).toBe(true)`) — the QA will reject them
- Follow the AAA pattern: Arrange -> Act -> Assert
- Name tests descriptively: `should return error when email is already registered`
- Use mocks/stubs only at boundaries (I/O, database, external APIs) — never on business logic

---

## Edge cases — universal checklist

For every Task Contract, verify the following:

**Handling patterns (Developer):**

| Scenario | How to handle |
|---|---|
| Null or undefined input | Validate at the validation layer (schema), before reaching the service |
| Empty list | Return `PaginatedResponse<T>` with `data: []`, never `null` |
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

> **Developer:** handle the applicable scenarios for your Task Contract and document them in the delivery file.
> **QA:** verify that applicable scenarios were handled and have a corresponding test.

---

## Bug severity classification

| Severity | Criterion | Impact on the Task Contract |
|---|---|---|
| **Critical** | System crashes, data corruption, security breach, SQL injection possible | Reject + block other tests |
| **High** | Acceptance criterion not met, main flow broken, endpoint returns 500 on expected case | Reject the Task Contract |
| **Medium** | Edge case not handled, uninformative error message, incorrect response field | Approve with mandatory caveat |
| **Low** | Naming inconsistency, unnecessary log, incomplete documentation | Log it, does not block approval |

---

## Root-cause falsification (R5)

A finding can be real but its diagnosed cause wrong — and a wrong cause sends the dev fix in the wrong direction (SIEGARD D5: QA blamed a static import for a test timeout and prescribed `React.lazy`; the real cause was CPU contention under the full parallel suite, and the timeout persisted until a file-scoped timeout was added).

**QA side — before assigning a cause to any timeout / flake / performance finding:**
1. Reproduce in isolation vs. under load — run the failing test alone, then under the full suite.
2. Vary the relevant knob — timeout, concurrency/`--maxWorkers`, ordering/seed.
3. Record the result in the finding's `root_cause.evidence`, and set `root_cause.confidence`:
   - `high` only when the cause was reproduced/verified by steps 1–2;
   - `low` when the cause is inferred from reading and was NOT reproduced.

Heuristic: **a test that times out in the full suite but passes in isolation ⇒ suspect contention / ordering / shared-state, NOT the code under test, until proven otherwise.**

**Dev side — consuming a QA finding:** a finding with `root_cause.confidence` below `high` carries a *hypothesis*, not a verified cause. Reproduce it before applying the suggested fix; do not apply the prescribed fix verbatim on a `low`-confidence cause.

---

## Dependency Injection

**Default:** `manual-factory` — unless `CLAUDE.md` declares `di_strategy`.

| Strategy | Detection signal |
|---|---|
| `manual-factory` | Factory function in `src/factories/` or `src/modules/{domain}/factory/` |
| `nestjs-ioc` | `@Injectable()` decorators present |
| `inversify` | `@injectable()` / `container.bind()` in `src/config/container.ts` |

**QA verifies:**
- [ ] Constructors receive interfaces, not concrete implementations
- [ ] No `new SomeDependency()` inside services or controllers — only in factory functions
- [ ] Factory functions exist and are used as the wiring point (manual-factory strategy)

**Developer quality BUGs:**
- Instantiating a dependency inside a service constructor: **Medium**
- No factory function when `di_strategy: manual-factory`: **Medium**
- Constructor receiving a concrete class instead of an interface when interface exists: **Low**

---

## DTO and Validation Pattern

**Default library:** Zod — unless `CLAUDE.md` declares `validation_library`.

**File naming (all libraries):**

| Use case | Schema/Class name | Type name | File |
|---|---|---|---|
| Create | `Create{Resource}Schema` | `Create{Resource}Dto` | `create-{resource}.dto.ts` |
| Update | `Update{Resource}Schema` | `Update{Resource}Dto` | `update-{resource}.dto.ts` |
| API response | `{Resource}ResponseSchema` | `{Resource}Response` | `{resource}-response.dto.ts` |
| Query params | `List{Resource}QuerySchema` | `List{Resource}Query` | `list-{resource}-query.dto.ts` |

**QA verifies:**
- [ ] DTOs live in `src/dto/` or `src/modules/{domain}/dto/` — not inline in controllers
- [ ] Services receive typed DTOs — never raw `req.body` or `unknown`
- [ ] Validation happens at the route/middleware boundary, before reaching the service
- [ ] Tests import DTO schemas from `src/dto/` — no inline redefinition

**Developer quality BUGs:**
- `req.body` passed directly to a service without schema validation: **High** (security risk)
- DTO file naming deviates from convention: **Low**
- DTO schema redefined inline inside a test: **Low**

---

## Pagination

**Default strategy:** `offset` — unless `CLAUDE.md` declares `pagination.strategy`.

**Canonical types live in `src/types/pagination.ts` — never duplicated per module.**

| Field | Type | Rule |
|---|---|---|
| `data` | `T[]` | Never `null` — use `[]` for empty |
| `meta.page` | `number` | Offset only |
| `meta.limit` | `number` | Both strategies |
| `meta.total` | `number` | Offset only |
| `meta.pages` | `number` | Offset only — `Math.ceil(total / limit)` |
| `meta.next_cursor` | `string \| null` | Cursor only |
| `meta.has_more` | `boolean` | Cursor only |

**QA verifies:**
- [ ] Empty list returns `PaginatedResponse<T>` with `data: []` — never `null`
- [ ] `meta.pages` is always computed for offset strategy
- [ ] `limit` exceeding `max_limit` returns 400 with `error.code: PAGINATION_LIMIT_EXCEEDED`
- [ ] `PaginatedResponse<T>` is imported from `src/types/pagination.ts` — not redeclared

**Developer quality BUGs:**
- Returning `null` instead of `{ data: [], meta: {...} }`: **High**
- `meta.pages` missing or hardcoded: **Medium**
- `PaginatedResponse` redefined per module instead of imported from shared types: **Medium**
- `limit` not validated against `max_limit`: **Medium**
