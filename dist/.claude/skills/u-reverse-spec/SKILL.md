---
name: u-reverse-spec
description: Primary reverse engineering skill - defines the mapping between code artifacts and spec artifacts, generation rules, and quality criteria for specs generated from existing code.
user-invocable: false
---

# SKILL: Reverse Engineering Specs

## Purpose
Define how to translate source code artifacts into specification artifacts, following the same templates, conventions, and folder structure as the `/u-spec` flow.

---

## AI-First Principle

Specs generated here are consumed by AI implementation agents.

An AI agent that finds silence in a spec will invent a value.
An AI agent that finds ambiguity will choose an interpretation.

For every implementation detail an agent would need to guess, the spec is incomplete. The following are mandatory when extractable from the code:

- Numeric thresholds and derived formulas (`clamp(8, x × 0.4, 12)`, not "adaptive font")
- CSS tokens used directly (`bg-data` / `text-data`, not "highlight color")
- Regex and format rules (`^[A-Z0-9]+$`, not "letters and numbers only")
- User-visible messages (verbatim text from source, not "appropriate error message")
- Cache invalidation keys (literal array `["groups", id]`, not "invalidate groups")
- Prop and field defaults (`decimal_places=2`, `is_active=true`)
- Query parameters and headers effectively used per feature (not everything the endpoint accepts)

**Completeness test:** if two independent AI agents, reading only this spec, produce different implementations for any detail, the spec is incomplete at that point. Mark unresolvable gaps with `<!-- TO CONFIRM: ... -->`.

---

## Core Principle

> Reverse engineering documents what the code **does**, not what it **should do**.
> Generated specs receive `draft` status and must be reviewed by a human via `/u-spec`.

---

## Mapping: Code -> Spec

### Backend

| Code Artifact | Spec Artifact | Target Section |
|---------------|--------------|----------------|
| Controller/Route with HTTP decorators | `openapi.yaml` | `paths` with verb, route, operationId |
| DTO/Request/Response classes | `openapi.yaml` | `components.schemas` |
| Zod schema (`z.object(...)`) | `openapi.yaml` | `components.schemas` |
| Model/Entity with typed fields | `{domain}.back.md` | Section 2 — Data Model |
| Repository class | `{domain}.back.md` | Section 2 — Data Access Layer |
| Service/UseCase with business logic | `{domain}.spec.md` | Section 3 — Use Cases (UC-NN) |
| Validator/Guard/Pipe | `{domain}.back.md` | Section 3 — Business Rules (BR-NN) |
| Status/state enum | `{domain}.back.md` | Section 4 — State Machine (ST-NN) |
| Event emitter/listener/handler | `{domain}.back.md` | Section 5 — Domain Events (EV-NN) |
| throw/HttpException with status >= 400 | `_global/error-codes.md` | Global catalog |
| Entity relationships (FK, refs) | `{domain}.back.md` | Section 2 — Relationships |
| External integration (HTTP client, SDK) | `{domain}.back.md` | Section 6 — External Integrations |
| Auth middleware (JWT, session, RBAC) | `{domain}.spec.md` | Section 2 — Actors and permissions |

### Frontend

| Code Artifact | Spec Artifact | Target Section |
|---------------|--------------|----------------|
| Page/Screen component | `{feature}.feature.spec.md` | Full feature spec |
| Router config / file-based routes | `{flow}.flow.md` | Section 1 — Screens Involved |
| API call (fetch/axios/useQuery) | `{feature}.feature.spec.md` | §4 Requests, Order, and Cache — include `Params / Headers` column with effective params/headers extracted from call site |
| State store (zustand/redux/pinia) | `{feature}.feature.spec.md` | §4 Requests, Order, and Cache |
| Error boundary / catch handler | `{feature}.feature.spec.md` | §6 API Error → UI Mapping |
| Form with validation | `{feature}.feature.spec.md` | §5 Input Validations |
| Loading/Skeleton/Spinner | `{feature}.feature.spec.md` | §2 Feature States (loading) |
| Empty state component | `{feature}.feature.spec.md` | §2 Feature States (empty) |
| Navigation guards / redirects | `{flow}.flow.md` | Section 4 — Navigation Rules (FL-NN) |
| Link/navigate between pages | `{flow}.flow.md` | Section 2 — Happy Path |

---

## Generation Rules

### 0.5 Design System Legacy Detection

Before generating any frontend spec, check for `{SPECS_DIR}/front/design-system.md` as a **single file** (pre-3.0 format).

If found:
- Preserve the file as-is during this migration run.
- Add to its header: `<!-- TODO: migrate to design-system/ directory format via /u-spec -->`
- Do NOT create a `design-system/` directory — that conversion requires the Front Spec writing flow with full project context.
- Record the migration need in `{SPECS_DIR}/log-reverse-spec.md` under Identified Gaps: `design-system.md must be migrated to directory format before next /u-spec run`.

If `{SPECS_DIR}/front/design-system/` directory already exists: proceed normally, no action needed.

---

### 1. Templates

Use exactly the same templates from `.claude/skills/u-spec-templates/`:
- `TEMPLATE.spec.md` for `.spec.md`
- `TEMPLATE.back.md` for `.back.md`
- `TEMPLATE.feature.spec.md` for `.feature.spec.md`
- `TEMPLATE.flow.md` for `.flow.md`

### 2. Conventions

Follow all conventions from `.claude/skills/u-spec-globals/conventions.md`:
- Prefixes: UC-NN, BR-NN, ST-NN, EV-NN, UI-NN, FL-NN
- Sequential numbering by type within the domain
- kebab-case naming for files and folders
- Mandatory changelog with `Reverse Spec Writer` as author

### 3. Status

All generated artifacts must have:
- `Status: draft`
- Header note: `Generated by reverse engineering -- requires review via /u-spec`

### 4. OpenAPI

Generate `openapi.yaml` following the checklist from `.claude/skills/u-spec-writing/SKILL.md`:
- `openapi: "3.0.3"`
- `operationId` in camelCase derived from the method/function name
- Schemas derived from the code’s DTOs/models
- Error responses with standard `ErrorResponse` schema
- Examples derived from default values or fixtures found in the code

### 5. Use Cases

For each main endpoint/route, derive a UC:
- **Actor:** derive from the auth middleware (role/permission)
- **Precondition:** derive from guards/middleware
- **Postcondition:** derive from what the service/handler does
- **Main flow:** derive from the handler/service logic
- **Alternative flows:** derive from `catch/throw/if-error`

### 6. Business Rules (BR)

For each validation found in the service/domain layer:
- Name as BR-NN
- Reference the related UC
- Indicate where to validate (controller/service/middleware)
- Indicate the returned error (HTTP status + error.code)

### 7. State Machine (ST)

If an entity has a status enum field:
- List all enum values as states
- Search the code for where transitions occur (field assignments)
- Build transition table: From -> To + event/condition

### 8. Domain Events (EV)

For each emit/dispatch/publish found:
- Event name
- Payload (emitted fields)
- Where it is fired (condition)
- Who consumes it (search for listeners/handlers/subscribers)

### 9. Screens (UI) — Frontend

For each page/screen:
- Minimum states: idle, loading, success, error. Add `empty` only if the code contains an explicit empty state component or conditional rendering for a zero-record collection response. Never add it for forms or single-resource views
- Consumed domains: derive from API calls
- Validations: derive from forms
- Error mapping: derive from catch/error handlers

### 10. Flows (FL) — Frontend

For each navigation sequence:
- Screens involved with routes
- Happy path: navigation sequence without errors
- Guards/redirects = navigation rules (FL-NN)
- Deep links: every route must have direct access handling

---

## Quality Criteria

Before delivering the generated specs, the Writer must validate:

- [ ] Every endpoint found in the code has a corresponding path in openapi.yaml
- [ ] Every model/entity has a schema in openapi.yaml and a table in .back.md
- [ ] Every error throw/catch has an error.code in the catalog
- [ ] Every UC has at least 1 alternative flow
- [ ] Every screen has idle, loading, success, error states; `empty` present only when a zero-record collection path exists in the code
- [ ] Every flow has at least 1 alternative flow
- [ ] UC/BR/ST/EV/UI/FL prefixes follow conventions
- [ ] Changelog filled with date and author "Reverse Spec Writer"
- [ ] No field uses vague terms: "adequate", "generally", "etc."

---

## Known Limitations

Reverse engineering CANNOT reliably extract:
- **Business intent** — why the rule exists (only what it does)
- **Complete actors** — if there is no auth middleware, actors will be generic
- **Out of scope** — what was decided not to implement (it’s not in the code)
- **Future requirements** — TODOs in the code are hints, not specs
- **Business glossary** — domain terms may need human input

These gaps must be marked with `<!-- TO CONFIRM: ... -->` for human review.
