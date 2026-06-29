---
name: u-be-development
description: Coding standards, commit conventions, folder structure, naming rules, and error handling patterns for back-end implementation. Covers routes, controllers, services, repositories, models, and middleware. Loaded by orchestrator-dev when activating the Developer agent.
user-invocable: false
---

# SKILL: Development (Backend)

## Purpose
This skill defines how the Developer Agent must structure, name, organize, and deliver code — ensuring consistency across Task Contracts and predictability for the QA Agent.

---

## Customization via CLAUDE.md

> Precedence rule defined in `orchestrator-core.md`. Not repeated here.

Before creating any file, extract from `CLAUDE.md`:

| What to look for | Used in |
|---|---|
| Project folder structure | Where to create new files |
| Naming conventions | File, class, and function names |
| Testing framework/library | How to write and run tests |
| Configured logger | Replace `console.log` |
| Custom error pattern | Error classes to extend |
| Already defined environment variables | Avoid hardcoding and duplicates |
| Configured ORM/ODM | Model and migration patterns |
| `validation_library` | DTO schema strategy (Zod, Joi, class-validator) |
| `di_strategy` | Dependency injection pattern (manual-factory, nestjs-ioc, inversify) |
| `pagination.strategy` | Offset or cursor pagination — determines `PaginatedResponse<T>` meta shape |

If `CLAUDE.md` does not cover a given point, use the defaults from this skill and document the decision in the delivery file.

---

## Engineering principles

- Follow CLEAN Code and SOLID principles rigorously
- Apply appropriate design patterns whenever relevant (Factory, Strategy, Repository, Observer, etc.)
- Prefer composition over inheritance
- Apply Dependency Injection for all external dependencies (database, APIs, services)
- Prefer pure functions and immutability whenever possible
- Every public function/method must have a single, clear responsibility
- Prioritize simplicity: small, focused modules without unnecessary complexity
- Simplify first: avoid accidental complexity, YAGNI, and premature abstractions

---

## Progress reporting (mandatory)

Emit `task_progress` at each checkpoint before proceeding to the next phase of work. These events reset the stale detection timer and give the orchestrator visibility during long-running tasks.

```bash
# Checkpoint 1 — after reading and validating the task spec
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_progress \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","checkpoint":"spec_validated"}'

# Checkpoint 2 — after analysis, before writing any code
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_progress \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","checkpoint":"analysis_complete"}'

# Checkpoint 3 — after creating the branch, before first file write
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_progress \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","checkpoint":"branch_created"}'

# Checkpoint 4 — after all source code is written, before tests
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_progress \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","checkpoint":"implementation_done"}'

# Checkpoint 5 — after tests are written, before delivery.md
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_progress \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","checkpoint":"tests_written"}'
```

Never skip a checkpoint. If `$ORCH_WORKER_ID`, `$ORCH_TASK_ID`, or `$ORCH_ATTEMPT` are unresolved, stop and emit `task_failed` with `reason: unresolved_context_variables, retryable: false`.

---

## Terminal event guarantee (mandatory)

Before stopping for any reason — tool failure, blocked state, unexpected error, context limit — verify that a terminal event (`task_completed` or `task_failed`) has been emitted for `$ORCH_TASK_ID / $ORCH_ATTEMPT`.

**If no terminal has been emitted, emit `task_failed` immediately before stopping:**

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_failed \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","reason":"<specific_reason>","retryable":true}'
```

| Situation | reason | retryable |
|-----------|--------|-----------|
| Tool call denied or failed | `tool_failure` | `true` |
| Required file not found | `missing_input:<file>` | `false` |
| Implementation blocked by ambiguity | `blocked_ambiguity` | `false` |
| Context limit approaching | `context_limit` | `true` |
| Unresolved env variables | `unresolved_context_variables` | `false` |
| Any other unexpected stop | `unexpected_exit` | `true` |

The `on_subagent_stop` hook synthesizes `task_failed` if this rule is not followed, but explicit emission is always preferred — it carries an accurate reason and retryable flag.

---

## Mandatory flow before coding

```
1. Read the full Task Contract (narrative + all acceptance criteria)
   → emit checkpoint: spec_validated
2. Read the files listed as dependencies in the previous delivery (if any)
3. Map the interface contracts the Task Contract will touch or create
   → emit checkpoint: analysis_complete
4. Confirm you are on the Task Contract branch the Orchestrator created (feat/TC-XX, fix/TC-XX, or refactor/TC-XX) in your worktree
   → emit checkpoint: branch_created
5. Write the implementation plan as a comment at the top of the first file created
6. Only then begin implementation
   → emit checkpoint: implementation_done (after all source code is written, before tests)
7. Write tests
   → emit checkpoint: tests_written (after tests, before delivery.md)
```

If any step reveals a blocking ambiguity -> **stop, emit `task_failed` with `reason: blocked_ambiguity, retryable: false`, and record the ambiguity in the delivery file**.

---

## Branch and commits

### Branch per Task Contract

The Orchestrator-Dev creates one branch + worktree per Task Contract from `main` before activating you (SIEGARD-04). Confirm you are on it before any implementation:

```
feat/TC-XX    <- for Task Contracts of type New feature, Improvement
fix/TC-XX     <- for fixes coming from QA
refactor/TC-XX <- for Task Contracts of type Refactoring
```

**Rules:**
- Work exclusively on the Task Contract branch (inside your worktree) — never commit directly to `main`
- **Never merge to `main`** — integration is the sole responsibility of the Orchestrator-Dev, performed at the end of the dev phase (before review) so QA runs on the integrated head (SIEGARD-04)
- Commit locally as often as you like
- Remove any scratch/backup files you created (e.g. `*.tcNN`) before emitting your terminal event — never leave them in the working tree (SIEGARD-08)

### Commit format

Mandatory semantic prefix:

```
feat(TC-XX): [description of what was added]
fix(TC-XX):  [description of what was fixed]
refactor(TC-XX): [description of improvement without behavior change]
test(TC-XX): [description of tests added]
docs(TC-XX): [documentation update]
migration(TC-XX): [description of migration created]
```

Prefer per-layer commits when the Task Contract spans multiple modules (e.g., first `feat(TC-05): add user model and migration`, then `feat(TC-05): add user repository`, then `feat(TC-05): add user service`, then `feat(TC-05): add user controller and routes`).

---

## Naming conventions

| Element | Pattern | Example |
|---|---|---|
| Files | kebab-case | `user-profile.service.ts` |
| Classes | PascalCase | `UserProfileService` |
| Functions/methods | camelCase | `getUserById()` |
| Constants | SCREAMING_SNAKE | `MAX_RETRY_ATTEMPTS` |
| Variables | camelCase | `isActive` |
| Interfaces | IPascalCase | `IUserRepository`, `IPaymentGateway` |
| Types | PascalCase | `CreateUserInput`, `UserResponse` |
| DTOs | PascalCaseDTO | `CreateUserDTO`, `UpdateOrderDTO` |
| Enums | PascalCase (members in UPPER_SNAKE_CASE) | `UserRole.ADMIN`, `OrderStatus.PENDING` |
| DB tables | snake_case (plural) | `user_profiles` |
| DB columns | snake_case | `created_at` |
| API routes | kebab-case (plural) | `/api/v1/user-profiles` |
| Environment variables | SCREAMING_SNAKE | `DATABASE_URL` |
| Tests | same name + `.spec` or `.test` | `user-profile.service.spec.ts` |

> `CLAUDE.md` conventions take precedence (see precedence rule in orchestrator-core).

---

## TypeScript code quality

- Strict TypeScript: enable `strict: true`, `noImplicitAny`, `strictNullChecks`
- Never use `any` — prefer `unknown`, generics, or explicit types
- Avoid `as` type assertions; use type guards and narrowing
- Define explicit types on public function signatures (parameters and return)
- Use `readonly` for properties that must not be reassigned
- Prefer `const enum` or union types over conventional enums
- Use the `Result<T, E>` or Either pattern for operations that can fail (avoid throw in business logic)
- Limit functions to ~30 lines; extract complex logic into named helpers
- Maximum of 3 parameters per function — use objects for more
- Avoid magic numbers and magic strings — extract named constants

---

## Architecture

- Adopt layered architecture (Layered/Clean Architecture) or Hexagonal when applicable
- Minimum layers: Controller -> Service/UseCase -> Repository/Gateway
- Keep business rules isolated from frameworks and I/O
- Use Ports & Adapters for external integrations (database, queues, third-party APIs)
- Domain entities must not depend on external libraries
- Each module/domain must be self-contained — avoid circular dependencies
- Clearly separate configuration, bootstrap, and application logic

### SRP within a service class

A service class that methods reference two or more distinct noun domains violates SRP — even if it lives in the correct layer.

| Signal | Action |
|---|---|
| Method names come from two different noun domains (e.g., `UserService` handling profile + notification + billing) | Split into one service per domain concept |
| A service method orchestrates unrelated concerns sequentially | Extract each concern into a named helper or a separate service |
| A service grows past ~5 public methods and they cluster into two natural groups | Split by cluster |

Correct form: one domain concept per service class. Adding a responsibility = new service class, not a new method on the existing one.

### OCP at feature design time

When a domain concept has type variants, choose the implementation strategy before writing code.

| Condition | Implementation |
|---|---|
| Spec or `CLAUDE.md` declares the concept extensible (e.g., `PaymentMethod: extensible via Strategy`) | Define an interface + one class per variant + factory function. Adding a variant = new file only, no existing file modified |
| Variants are closed and will not grow (spec declares `closed enum`) | A single `switch` or lookup map is correct — do not over-engineer |
| No declaration in spec | Ask before implementing. Default to closed enum if variants are domain-stable (e.g., `OrderStatus`); default to Strategy if variants are integration points (e.g., payment gateways, storage backends) |

Violation to avoid: `switch(type)` inside a service method when the spec declares the concept extensible — this forces a modification to existing code every time a new variant is added.

### ISP at interface design time

Before finalizing an interface with 4+ methods, list its known consumers and verify whether each consumer needs every method.

| Result of the check | Action |
|---|---|
| All consumers use all methods | Interface is cohesive — keep it as-is |
| Consumers use disjoint subsets | Split into one interface per consumer need |
| One consumer uses all methods; others use a subset | Extract a narrower interface for the subset consumers; full interface remains for the primary consumer |

**Enterprise examples:**

```
IUserRepository (findByEmail, create, findAll, count, update, delete)
  → AuthService needs: findByEmail, create
  → AdminService needs: findAll, count, update, delete
  → ReportService needs: findAll, count
  ✗ All consumers import the full interface for methods they never call
  ✓ Split: IAuthUserRepository, IAdminUserRepository, IReportUserRepository

IPaymentGateway (charge, refund, getStatus)
  → CheckoutService needs: charge, refund
  → ReconciliationService needs: charge, getStatus
  → All consumers use overlapping methods
  ✓ Interface is cohesive — keep it
```

Apply this check when defining new interfaces, not retroactively on existing ones unless refactoring is already in scope.

---

## Dependency Injection

**Default strategy: manual factory function per module.**

Read `di_strategy` from `CLAUDE.md`. If absent, use `manual-factory`.

| `di_strategy` value | Pattern |
|---|---|
| `manual-factory` | Factory function in `src/factories/[resource].factory.ts` — explicit wiring |
| `nestjs-ioc` | NestJS `@Injectable()` — follow framework conventions |
| `inversify` | InversifyJS container — declare bindings in `src/config/container.ts` |

**Manual factory pattern (default):**

```typescript
// src/factories/user.factory.ts
import { DatabaseClient } from "@/config/database";
import { UserRepository } from "@/repositories/user.repository";
import { UserService }    from "@/services/user.service";
import { UserController } from "@/controllers/user.controller";

export function createUserModule(db: DatabaseClient) {
  const repository = new UserRepository(db);
  const service    = new UserService(repository);
  const controller = new UserController(service);
  return { repository, service, controller };
}
```

**Rules (all strategies):**
- Constructors receive **interfaces**, never concrete classes
- Never instantiate a dependency inside a service — receive via constructor
- Never use `new SomeService()` inline in a controller or route
- Factory functions are the only place where `new` is used to wire dependencies

---

## DTO Pattern

**Default library: Zod** — unless `CLAUDE.md` declares `validation_library`.

| `validation_library` value | Pattern |
|---|---|
| `zod` | `z.object(...)` schema + `z.infer<typeof Schema>` type (default) |
| `class-validator` | Class with decorators — follows NestJS conventions |
| `joi` | `Joi.object(...)` schema + explicit TypeScript type |

**Zod default — naming and file conventions:**

```typescript
// src/dto/create-user.dto.ts
import { z } from "zod";

export const CreateUserSchema = z.object({
  name:  z.string().min(1).max(255),
  email: z.string().email(),
});

export type CreateUserDto = z.infer<typeof CreateUserSchema>;
```

| Use case | Schema name | Inferred type | File |
|---|---|---|---|
| Create | `Create{Resource}Schema` | `Create{Resource}Dto` | `create-{resource}.dto.ts` |
| Update | `Update{Resource}Schema` | `Update{Resource}Dto` | `update-{resource}.dto.ts` |
| API response | `{Resource}ResponseSchema` | `{Resource}Response` | `{resource}-response.dto.ts` |
| Query params | `List{Resource}QuerySchema` | `List{Resource}Query` | `list-{resource}-query.dto.ts` |

**Rules:**
- Schema name = `PascalCase + "Schema"`; type name = `PascalCase + "Dto"` or `"Response"`
- Validate at the route/middleware boundary — service receives an already-typed DTO, never raw `req.body`
- DTOs live in `src/dto/` (flat) or `src/modules/{domain}/dto/` (module structure) — never inline in controllers
- Do not redefine the same schema in tests — import from `src/dto/`

---

## Default folder structure

```
src/
├── routes/              <- route/endpoint definitions
│   └── [resource].routes.ts
├── controllers/         <- HTTP handlers (receive request, return response)
│   └── [resource].controller.ts
├── services/            <- business rules
│   └── [resource].service.ts
├── repositories/        <- data access (queries, ORM calls)
│   └── [resource].repository.ts
├── models/              <- entity/database schema definitions
│   └── [resource].model.ts
├── dto/                 <- input/output schemas and inferred types
│   ├── create-[resource].dto.ts
│   ├── update-[resource].dto.ts
│   └── [resource]-response.dto.ts
├── middleware/           <- shared middleware (auth, logging, error handler)
│   ├── auth.middleware.ts
│   ├── error-handler.middleware.ts
│   └── validation.middleware.ts
├── migrations/          <- database migration scripts
│   └── YYYYMMDDHHMMSS-[description].ts
├── config/              <- application configuration
│   ├── database.ts
│   ├── env.ts
│   └── app.ts
├── types/               <- global types and interfaces
│   ├── api.ts
│   ├── pagination.ts    <- PaginatedResponse<T>, OffsetPaginationMeta, CursorPaginationMeta
│   └── index.ts
├── factories/           <- module factory functions (DI wiring)
│   └── [resource].factory.ts
├── utils/               <- pure utility functions
│   └── [utility].ts
└── __tests__/           <- tests (mirrors src/ structure)
    ├── integration/
    │   └── [resource].integration.spec.ts
    └── unit/
        ├── [resource].service.spec.ts
        └── [resource].repository.spec.ts
```

> Adapt according to the structure defined in `CLAUDE.md`.

**Module-based alternative** (when `CLAUDE.md` declares `folder_structure: modules`):
```
src/modules/{domain}/
    controller/   dto/   service/   repository/   entity/   factory/
```
In this case `src/types/pagination.ts` and `src/types/api.ts` remain at the root `src/types/` — never duplicated per module.

---

## Mandatory tests and quality criteria

> Refer to `standards/SKILL.md` for the mandatory tests per Task Contract type table and test quality criteria. Tests are part of the delivery — the QA Agent does not write tests; it validates the coverage of the tests you delivered.

---

## Error handling

Every function that can fail must:

1. Use explicit error types — avoid `throw new Error("something went wrong")`
2. Differentiate operational errors (expected, e.g., resource not found) from programming errors (bugs)
3. Never silence errors with an empty `catch {}`
4. Propagate context: `throw new AppError("createUser failed", { cause: err })`

```typescript
// Bad
try {
  const user = await db.user.findUnique({ where: { id } });
  return user;
} catch (e) {
  throw new Error("error");
}

// Good
async function getUserById(id: string): Promise<User> {
  const user = await db.user.findUnique({ where: { id } });
  if (!user) throw new NotFoundError(`User ${id} not found`);
  return user;
}
```

### Error layers

| Layer | Responsibility |
|---|---|
| Controller | Catches service errors, maps to HTTP status code |
| Service | Throws business errors (NotFound, Conflict, ValidationError) |
| Repository | Throws data errors (ConnectionError, QueryError) |
| Middleware (error handler) | Catches all unhandled errors, formats standard response |

### Mandatory fields in error classes

Every custom error class must inherit from `Error` and include:
- `name` — error class name (e.g., `NotFoundError`, `ConflictError`)
- `message` — human-readable error description
- `statusCode` — corresponding HTTP code (e.g., 404, 409, 422)
- `context` — additional diagnostic data (input, entity ID, etc.)

### Error logging

- Always log errors with sufficient context: correlation ID, relevant input, stack trace
- Never expose stack traces or internal details to the client in production

### Error response format

Error responses must follow a standardized format:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "User with ID 123 not found",
    "details": {}
  }
}
```

---

## API design

- RESTful by default; document with OpenAPI/Swagger
- Versioning via URL prefix: `/api/v1/`
- Use HTTP status codes correctly (201 for creation, 204 for delete without body, 422 for validation)
- Validate input at the boundary (controller/middleware) using DTOs from `src/dto/` — never raw `req.body` in services
- Paginated responses use `PaginatedResponse<T>` from `src/types/pagination.ts` — never ad-hoc `{ data, meta }` shapes
- Idempotency for sensitive operations (POST with idempotency key)

---

## Pagination

Read `pagination.strategy` from `CLAUDE.md`. If absent, use `offset`.

**Shared types — always in `src/types/pagination.ts`, never duplicated per module:**

```typescript
export interface OffsetPaginationMeta {
  page:  number;
  limit: number;
  total: number;
  pages: number;          // Math.ceil(total / limit)
}

export interface CursorPaginationMeta {
  next_cursor: string | null;
  has_more:    boolean;
  limit:       number;
}

export interface PaginatedResponse<T> {
  data: T[];
  meta: OffsetPaginationMeta | CursorPaginationMeta;
}
```

| Strategy | When to use | Query params |
|---|---|---|
| `offset` | Admin lists, reports, exports — default | `?page=1&limit=20` |
| `cursor` | Feeds, timelines, real-time streams | `?cursor=abc&limit=20` |

**Rules:**
- Never return `null` for an empty list — always `PaginatedResponse<T>` with `data: []`
- `default_limit` and `max_limit` are read from `CLAUDE.md` — never hardcode these values
- If `limit` exceeds `max_limit`, reject with 400 and `error.code: PAGINATION_LIMIT_EXCEEDED`
- `pages` field (offset only) must always be computed — never omitted

---

## Edge cases

> Refer to the **universal checklist** and **handling patterns** in `standards/SKILL.md`. For every implemented function, handle applicable scenarios and document them in the delivery file.

---

## Explicit prohibitions

- `console.log` in production code (use the project's configured logger)
- Hardcoded credentials, tokens, or environment URLs
- `any` in TypeScript — prefer `unknown`, generics, or explicit types
- `as` type assertions without a corresponding type guard or narrowing
- Unused imports
- Commented-out code (delete it, don't comment it)
- `TODO` without a Task Contract or issue reference (`// TODO(TC-12): add cache`)
- Changing code outside the Task Contract scope without creating a separate technical Task Contract
- Raw SQL queries without parameterization (SQL injection risk)
- Secrets in logs or error messages returned to the client
- Destructive migrations without rollback (always provide `up` and `down`)

---

## Delivery file template

> When generating `tc-XX-delivery.md`, read the full template at `.claude/skills/u-be-templates/delivery.md`.

---

## Infrastructure dependency verification

Before starting implementation, the Developer must map **all infrastructure services and resources** the Task Contract requires.

### How to verify

1. Extract from the Task Contract and API Spec all infrastructure dependencies (database, queues, cache, third-party services, storage, etc.)
2. For each dependency, check whether the configuration **already exists** in the project:
   - Environment variables defined
   - Clients/connections configured
   - Docker compose / setup scripts
3. Classify each dependency:
   - **Available** — configuration found and functional
   - **Partial** — exists but with incomplete configuration
   - **Missing** — not found in any source

### When to generate the report

Generate the file `$SESSION_DIR/pending/$ORCH_TASK_ID-infra-pending.md` whenever there is **at least one dependency classified as Partial or Missing**.

> For the full report template, read `.claude/skills/u-be-templates/infra-pending-items.md`.

---

## Pre-delivery checklist

- [ ] All acceptance criteria have been addressed (even those not implemented, with justification)
- [ ] None of the explicit prohibitions were violated
- [ ] Mandatory edge cases have been handled
- [ ] **Each acceptance criterion has at least one corresponding test**
- [ ] **Edge cases handled in code have a corresponding test**
- [ ] "Tests written" section filled in the delivery file
- [ ] Infrastructure dependency verification executed (Step 1B)
- [ ] If there are infra issues: `$SESSION_DIR/pending/$ORCH_TASK_ID-infra-pending.md` generated and Orchestrator notified
- [ ] Delivery file generated at `$SESSION_DIR/delivery/$ORCH_TASK_ID-delivery.md`
- [ ] `task_progress` event emitted via `emit.py` with `status: in_testing`
- [ ] Working on the correct branch (`feat/TC-XX`, `fix/TC-XX`, or `refactor/TC-XX`)
- [ ] Commits follow the semantic pattern (including `test(TC-XX):` for test commits)
- [ ] **Branch contains only local commits** — push will be executed by Orchestrator-Dev after QA approval
- [ ] Migrations include `up` and `down`
- [ ] Queries are parameterized (no string concatenation in SQL)
- [ ] No secrets in logs or error responses
- [ ] If this is a post-QA fix: only the bugs from the report were changed — approved behaviors left untouched
- [ ] Orchestrator-Dev notified of completion
