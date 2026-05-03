---
name: u-spec-writing
description: Specification writing skill - OpenAPI 3.0, domain modeling, use cases, and error mapping.
user-invocable: false
---

# SKILL: Specification Writing

## Purpose
Provide the Spec Writer with the knowledge needed to produce high-quality specs.

## OpenAPI 3.0 -- Quality Checklist

### Mandatory structure
- `openapi: "3.0.3"`
- `info.title`, `info.version`, `info.description`
- `servers` with at least a dev environment
- `paths` with all domain endpoints
- `components.schemas` with all models
- `components.securitySchemes` if authentication exists
- `tags` grouping endpoints by context

### Endpoint rules
- Correct HTTP verbs: GET (read), POST (create), PUT (replace), PATCH (partial), DELETE (remove)
- `operationId` in camelCase, globally unique: `listTasks`, `createTask`, `getTaskById`
- Every response must have a `description`
- Error responses with standard schema:

```yaml
ErrorResponse:
  type: object
  required: [error]
  properties:
    error:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
          example: "RESOURCE_NOT_FOUND"
        message:
          type: string
          example: "Task with id 123 not found"
        details:
          type: object
```

### Schema rules
- `required` fields always explicit
- `format` for typed strings: `date-time`, `email`, `uuid`
- `example` on every schema and property
- `enum` for fields with finite values
- `$ref` to reuse schemas -- never duplicate

## Domain Modeling

### Identify
1. **Entities** -- objects with identity and lifecycle (e.g., User, Task, Order)
2. **Value Objects** -- objects without own identity (e.g., Address, Money)
3. **Aggregates** -- grouping of entities with a root (e.g., Order + OrderItems)
4. **Events** -- facts that occurred in the domain (e.g., TaskCompleted, OrderShipped)

### Rules
- Each domain has at most 1-3 root entities
- Relationships between domains are via ID, never nested objects
- Invariants must be listed explicitly

## Use Cases

### Mandatory structure
1. **Actor** -- who initiates
2. **Precondition** -- what must be true before
3. **Postcondition** -- what changes after
4. **Main flow** -- numbered steps of the happy path
5. **Alternative flows** -- deviations (format `Na` where N is the step)
6. **Related endpoint** -- corresponding operationId

### Best practices
- One UC = one actor intent
- Alternative flows must cover ALL endpoint errors
- Each UC must have at least 1 alternative flow

## Error Mapping

### Process
1. List all HTTP status >= 400 for each endpoint
2. For each, define an `error.code`
3. Check the global catalog to see if it already exists
4. If new, register in the catalog BEFORE using it
5. Include in the "Error Behaviors" section of .spec.md

---

## AI-First Principle

Specs are consumed by both humans and AI implementation agents.

An AI agent that finds silence in a spec will invent a value.
An AI agent that finds ambiguity will choose an interpretation.

For every implementation detail an agent would need to guess, the spec is incomplete. The following are mandatory when known:

- Numeric thresholds and derived formulas (`clamp(8, x × 0.4, 12)`, not "adaptive font")
- CSS tokens used directly (`bg-data` / `text-data`, not "highlight color")
- Regex and format rules (`^[A-Z0-9]+$`, not "letters and numbers only")
- User-visible messages (verbatim text, not "appropriate error message")
- Cache invalidation keys (literal array `["groups", id]`, not "invalidate groups")
- Prop and field defaults (`decimal_places=2`, `is_active=true`)
- Parent-to-component contract ("parent filters by period; component does not filter")

**Completeness test:** if two independent AI agents, reading only this spec, produce different implementations for any detail, the spec is incomplete at that point.

---

## Feature Spec (feature.spec.md)

### Design System: single-file to directory migration

When starting a spec run and `{SPECS_DIR}/front/design-system.md` exists as a **single file** (pre-3.0 format):

1. Read the file entirely before proceeding.
2. Create `{SPECS_DIR}/front/design-system/` directory.
3. Distribute content into the 5 target files: `_index.md`, `tokens.md`, `composition.md`, `components.md`, `implementation.md`.
4. Delete `design-system.md` after confirming all content was migrated.
5. Update all cross-references in `front.md` and feature specs from `design-system.md` → `design-system/_index.md` (or the correct sub-file).

If `design-system/` directory already exists: proceed normally.

---

### Granularity rule
1 feature = 1 URL/route. A feature is bounded by its route — when the URL changes, a new feature begins.

| Situation | Model |
|-----------|-------|
| Multi-step wizard with different URLs per step | Multiple feature specs + 1 flow.md connecting them |
| Modal or drawer that does NOT change the URL | State inside the same feature spec (§2) |
| Tabs on the same route | States inside the same feature spec (§2) |

### Section-by-section guidance

**§1 Consumed Endpoints:** three columns only — Domain, operationId, Purpose. Extract operationIds from approved `openapi.yaml`. Never invent operationIds. Never copy Method+Path or Auth — those are in `openapi.yaml` and drift as the API evolves. If an endpoint does not exist yet, record it in `tc-XX-backend-pending-items.md` — do not add it to the spec as if it exists.

**§2 Feature States:** mandatory minimum: idle, loading, success, error. Add `empty` only when the feature displays a collection (list, table, search result, feed) that can return zero records. Drop entirely for forms, auth flows, and single-resource views. Never fill a state with "not applicable" — omit the block. Name additional states as `{noun}-{condition}` — e.g., `form-editing`, `confirm-dialog`, `search-active`. Never use generic names like `state1` or `open`.

**§3 State Transition Table:** the Side Effect column is mandatory when the transition implies any of the following: query cache invalidation (verbatim key — e.g., `["groups"]`, `["measurement_units", "active"]`), local state reset (e.g., reset modal state), programmatic navigation (e.g., `→ /login`), dispatched toast, or write to sessionStorage/localStorage. Use `—` only when no side effect is provably absent.

**§5 Input Validations:** two columns only — User message and When to validate. Technical constraints (required, minLength, maxLength, pattern, enum) are already in the `requestBody` schema of `openapi.yaml` — do NOT duplicate them in §5; they drift when the backend changes. §5 specifies only what the user sees and when: `blur` for per-field feedback, `submit` for full-form validation, `change` for real-time (use sparingly — password strength and similar only).

**§4 Requests, Order and Cache:** the `Params / Headers` column records only parameters and headers this feature effectively uses — not everything the endpoint accepts. `openapi.yaml` declares what is possible; §4 declares what is used. Always record `Prefer: return=representation` when a mutation requires the returned object.

**§4 Response transforms:** fill the "Response transforms" sub-section only when the API response requires transformation before UI consumption — field rename, type cast, derive, flatten, filter. Omit the sub-section entirely if not applicable. The "Composed models" sub-section is for UI models that merge data from 2+ endpoints; omit if not applicable.

**§7 Component adapters:** fill the "Component adapters" sub-section only when the API response shape differs from the component's Props Contract (§2 of component.spec.md) and an explicit prop-level mapping is needed. Omit if API fields map directly to props.

**§7 Shared Components Used:** list only components from `src/components/` (global reusable). Never list feature-local components here. If a listed component has no `component.spec.md`, add it to §10 with `Action: create`.

**§9 BDD Scenarios:** these are feature invariants — they must be true regardless of which Task Contract implements them. Ask: "what must always be true when the user is on this feature?" Write at minimum: (1) the complete happy path as a single scenario, (2) the most critical error scenario. Do not duplicate Task Contract-level acceptance criteria here.

**§10 Components to Create / Update:** fill this during spec writing, not after. The Planner reads this section to create Spec Task Contracts before implementation begins. Criterion for `create`: component will appear in §7 of 2+ features. Criterion for `update`: existing component needs new props or states to support this feature.

---

## Component Spec (component.spec.md)

### When to create
Create a `component.spec.md` when the component meets at least one criterion:
- Used in 2+ distinct features (appears in §7 of 2+ feature specs)
- Has non-trivial internal logic: own state + side effects + data transformations

Single-use components with no internal complexity → specify inline in the feature spec.

### Section-by-section guidance

**§1 Purpose and Responsibilities:** state what the component does AND what it explicitly does not do. The "out of scope" line prevents scope creep across features.

**§2 Props Contract:** use TypeScript types from the project — never invent types in the spec. Mark all optional props with `?` and include defaults. This is the binding contract: changing it without a spec CR is a breaking change. When any prop's type originates from a project module (not a primitive or shadcn/ui intrinsic), include the TypeScript import block above the props table with the exact `@/` alias path — this is required so a dev agent knows the import source without guessing. Omit the block if all types are primitives or framework intrinsics.

**§3 Component States:** document only states the component manages internally (own `useState`, `useReducer`). States that come entirely from external props belong in §2, not §3. External-facing visual state (hover, focus) belongs in the design system, not here.

**§4 Events Emitted:** if the component has no callback props (pure display), omit §5 entirely — do not generate it with "None" or "N/A". When callback props exist, document the exact TypeScript payload type for each. If the callback has no payload, type it as `() => void`. Vague payloads like `(data: any) => void` are rejected.

**§5 Variants:** if the component has no variants, write `N/A`. Do not add hypothetical future variants.

**§7 BDD Scenarios:** minimum 3 scenarios covering: (1) default render with required props, (2) error state or disabled state, (3) keyboard navigation through the component. These become the component's isolation test baseline.

### Dense technical content preservation

```yaml
applies_to:
  - new-spec
  - migration
  - reverse-spec
  - spec-review
```

The template defines minimum structure, not depth limit. An agent MUST NOT omit known technical content because no named section exists for it.

**Mandatory content — include when known:**

| Content type | Preferred section | Fallback |
|-------------|------------------|---------|
| Numeric thresholds or derived formulas for adaptive behavior | §4 Transition parameters table | §4.X |
| Cross-prop join rules (field A from prop X references field B from prop Y) | §3.1 Data Contract | §3.X |
| CSS tokens used directly by the component (colors, spacing, typography) | §6 Variants or §10 Internal Dependencies | nearest section + `####` sub-heading |
| User-visible text structures (tooltips, empty states, labels, error messages) | §4 Component States (Visual change column) | §4.X |
| Parent-to-component contract (what the parent must guarantee before passing data) | §3 Props Contract or §3.1 | §3.X |

**Fallback rule:** After filling all applicable template sections, if known technical content has no adequate section, create `§N.X` as a sub-section of the semantically nearest section. Use `####` heading. Never omit.

**Violation condition:** A spec is non-compliant if a known formula, threshold, join rule, or user-visible text structure exists in source material and is absent from the output.

---

## Decisions Log (decisions.md)

### When to write an entry
Write a DEC-NN entry when:
- A decision affects 2+ spec files
- A previously established pattern is being intentionally changed
- A trade-off was made consciously between valid alternatives
- The Orchestrator approves a spec divergence in Improve mode

### What NOT to record
- Implementation choices already covered by SKILL.md (e.g., "use kebab-case for files")
- Decisions documented in backlog Task Contracts or delivery files (those are session-scoped)
- Obvious choices with no real alternative

### Writing guidance
**Alternatives considered:** always list at least 2 alternatives, even if they were quickly discarded. The purpose is to prevent future sessions from reverting the decision without awareness of the context.

**Impact on specs:** list the exact files that were changed or must change as a result. This is the field the Orchestrator checks when determining which features are affected by a prop contract change or a pattern update.

**Supersession rule:** never edit a past decision entry. When a decision is reversed or updated, create a new DEC-NN with `Status: Active` and set the old entry's Status to `Superseded by DEC-XX`.
