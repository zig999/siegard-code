---
name: u-be-development
description: Coding standards, commit conventions, folder structure, naming rules, and error handling patterns for back-end implementation. Covers routes, controllers, services, repositories, models, and middleware. Loaded by orchestrator-dev when activating the Developer agent.
user-invocable: false
---

# SKILL: Development (Backend)

## Purpose
This skill defines how the Developer Agent must structure, name, organize, and deliver code — ensuring consistency across Stories and predictability for the QA Agent.

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
| Validation pattern (Zod, Joi, class-validator...) | Input schemas |

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

## Mandatory flow before coding

```
1. Read the full Story (narrative + all acceptance criteria)
2. Read the files listed as dependencies in the previous delivery (if any)
3. Map the interface contracts the Story will touch or create
4. Write the plan as a comment at the top of the first file created
5. Only then begin implementation
```

If any step reveals a blocking ambiguity -> **stop and record it in the delivery file before continuing**.

---

## Branch and commits

### Branch per Story

Before any implementation, create a branch from `main`:

```
feat/US-XX    <- for Stories of type New feature, Improvement
fix/US-XX     <- for fixes coming from QA
refactor/US-XX <- for Stories of type Refactoring
```

**Rules:**
- Work exclusively on the Story branch — never commit directly to `main`
- **Never push** — pushing is the sole responsibility of the Orchestrator-Dev, after QA approval
- Commit locally as often as you like

### Commit format

Mandatory semantic prefix:

```
feat(US-XX): [description of what was added]
fix(US-XX):  [description of what was fixed]
refactor(US-XX): [description of improvement without behavior change]
test(US-XX): [description of tests added]
docs(US-XX): [documentation update]
migration(US-XX): [description of migration created]
```

Prefer per-layer commits when the Story spans multiple modules (e.g., first `feat(US-05): add user model and migration`, then `feat(US-05): add user repository`, then `feat(US-05): add user service`, then `feat(US-05): add user controller and routes`).

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
├── middleware/           <- shared middleware (auth, logging, error handler)
│   ├── auth.middleware.ts
│   ├── error-handler.middleware.ts
│   └── validation.middleware.ts
├── validators/          <- input validation schemas (Zod, Joi, etc.)
│   └── [resource].validator.ts
├── migrations/          <- database migration scripts
│   └── YYYYMMDDHHMMSS-[description].ts
├── config/              <- application configuration
│   ├── database.ts
│   ├── env.ts
│   └── app.ts
├── types/               <- global types and interfaces
│   ├── api.ts
│   └── index.ts
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

---

## Mandatory tests and quality criteria

> Refer to `standards/SKILL.md` for the mandatory tests per Story type table and test quality criteria. Tests are part of the delivery — the QA Agent does not write tests; it validates the coverage of the tests you delivered.

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
- Validate input at the boundary (controller/middleware) with schemas (Zod, Joi, class-validator)
- Standardized pagination: `?page=1&limit=20` -> `{ data, meta: { page, limit, total } }`
- Idempotency for sensitive operations (POST with idempotency key)

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
- `TODO` without a Story or issue reference (`// TODO(US-12): add cache`)
- Changing code outside the Story scope without creating a separate technical Story
- Raw SQL queries without parameterization (SQL injection risk)
- Secrets in logs or error messages returned to the client
- Destructive migrations without rollback (always provide `up` and `down`)

---

## Delivery file template

> When generating `us-XX-delivery.md`, read the full template at `.claude/skills/u-be-templates/delivery.md`.

---

## Infrastructure dependency verification

Before starting implementation, the Developer must map **all infrastructure services and resources** the Story requires.

### How to verify

1. Extract from the Story and API Spec all infrastructure dependencies (database, queues, cache, third-party services, storage, etc.)
2. For each dependency, check whether the configuration **already exists** in the project:
   - Environment variables defined
   - Clients/connections configured
   - Docker compose / setup scripts
3. Classify each dependency:
   - **Available** — configuration found and functional
   - **Partial** — exists but with incomplete configuration
   - **Missing** — not found in any source

### When to generate the report

Generate the file `{SESSIONS_DIR}/{SESSION}/us-XX-infra-pending-items.md` whenever there is **at least one dependency classified as Partial or Missing**.

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
- [ ] If there are infra issues: `us-XX-infra-pending-items.md` report generated and Orchestrator notified
- [ ] Delivery file generated at `{SESSIONS_DIR}/{SESSION}/us-XX-delivery.md`
- [ ] Story status in `backlog.md` updated to `In testing`
- [ ] Working on the correct branch (`feat/US-XX`, `fix/US-XX`, or `refactor/US-XX`)
- [ ] Commits follow the semantic pattern (including `test(US-XX):` for test commits)
- [ ] **Branch contains only local commits** — push will be executed by Orchestrator-Dev after QA approval
- [ ] Migrations include `up` and `down`
- [ ] Queries are parameterized (no string concatenation in SQL)
- [ ] No secrets in logs or error responses
- [ ] If this is a post-QA fix: only the bugs from the report were changed — approved behaviors left untouched
- [ ] Orchestrator-Dev notified of completion
